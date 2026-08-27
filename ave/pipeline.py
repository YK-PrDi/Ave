"""主流程：扫素材 → 组合 → 识别 → 配音 → 渲染 → 导出。

一条命令跑完全部：
    python -m ave.pipeline              # 全量
    python -m ave.pipeline --limit 2    # 只跑 2 条，验证用
    python -m ave.pipeline --dry-run    # 只看组合方案，不渲染
"""

import argparse
import json
import os
import random
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import combo  # noqa: E402
from ave import asr, config, render, subtitle, tts, vision  # noqa: E402


def build_theme_map(pools, dedup=True):
    """算卖点语义簇。返回 (label->簇号, 说明文字)。

    dedup=False 时返回空表 —— 抽样退化成只去变体不去语义，
    等于接受同主题重复（界面上的开关走这条路）。
    """
    if not dedup:
        return {}, "已关闭语义去重，同一条里可能出现多个卖点讲同一件事"
    texts, from_asr, from_ai = point_texts(pools)
    tm = combo.auto_cluster(texts)
    n = len(set(tm.values()))
    fallback = len(texts) - from_asr - from_ai
    note = (f"语义聚类：{len(texts)} 个卖点组 → {n} 个主题"
            f"（{from_asr} 组用 ASR 原文")
    if from_ai:
        note += f"，{from_ai} 组用 AI 文案"
    note += f"，{fallback} 组回落用标签）"
    return tm, note


def make_tts_backend():
    if config.TTS_BACKEND == "volcano":
        missing = [n for n, v in [
            ("VOLCANO_APPID", config.VOLCANO_APPID),
            ("VOLCANO_TOKEN", config.VOLCANO_TOKEN),
            ("VOLCANO_VOICE", config.VOLCANO_VOICE)] if not v]
        if missing:
            raise RuntimeError(
                f"火山引擎配音缺少凭证: {', '.join(missing)}。"
                f"见 docs/资源需求清单.md，或把 TTS_BACKEND 改回 'stub'。")
        return tts.VolcanoBackend(config.VOLCANO_APPID, config.VOLCANO_TOKEN,
                                  config.VOLCANO_VOICE, config.VOLCANO_CLUSTER)
    return tts.StubBackend(config.FFMPEG)


def pick_bgm(rng, bgm_dir=None):
    """从 BGM 两层（内置 + 自定义）合并的候选池里随机挑一首。

    两层都空则返回 None。bgm_dir 传了就覆盖自定义层，语义与旧签名兼容。
    """
    tracks = [p for p, _tag in config.list_bgm(bgm_dir)]
    return rng.choice(tracks) if tracks else None


def scan(source=None):
    """扫描素材，返回 (pools, 统计字典)。供界面展示素材盘点用。"""
    source = source or config.SOURCE_DIR
    pools = combo.scan_product(source)
    groups = {
        "hooks": len(combo.group_variants(pools.hooks)),
        "points": len(combo.group_variants(pools.points)),
        "endings": len(combo.group_variants(pools.endings)),
    }
    return pools, {
        "source": source,
        "hooks": len(pools.hooks),
        "points": len(pools.points),
        "endings": len(pools.endings),
        "groups": groups,
        "unparsed": [os.path.basename(u) for u in pools.unparsed],
        # 产量 = 钩子组数 x 每钩子使用次数
        "expected": groups["hooks"] * config.HOOK_USE_LIMIT,
    }


# ---------------- 成品清单 ----------------
# 渲染时把实际用的组合落盘，界面据此显示每条成品的真实构成。
# 不用内存里存 job 记录：CLI 跑出来的覆盖不到，且服务重启即失。
MANIFEST_NAME = ".ave-manifest.json"


def manifest_path(out_dir=None):
    return os.path.join(out_dir or config.OUTPUT_DIR, MANIFEST_NAME)


def read_manifest(out_dir=None):
    """读成品清单，返回 {文件名: 记录}。文件不存在或坏了都返回空。"""
    try:
        with open(manifest_path(out_dir), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    items = data.get("items")
    return items if isinstance(items, dict) else {}


def record_manifest(out_dir, filename, cb, seed):
    """追加一条记录。同名重渲直接覆盖，避免换 seed 后留下旧构成。"""
    items = read_manifest(out_dir)
    items[filename] = {
        "index": cb.index,
        "seed": seed,
        "hook": cb.hook.label,
        "points": [p.label for p in cb.points],
        "ending": cb.ending.label,
        "at": int(time.time()),
    }
    p = manifest_path(out_dir)
    tmp = p + ".tmp"
    # 先写临时文件再原子替换：中途崩掉不会留下半截 JSON 把清单读废
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "items": items}, f,
                  ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def prune_manifest(out_dir, filename):
    """删成品时同步清掉记录，不留孤儿条目。"""
    items = read_manifest(out_dir)
    if items.pop(filename, None) is None:
        return
    p = manifest_path(out_dir)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "items": items}, f,
                  ensure_ascii=False, indent=1)
    os.replace(tmp, p)


# ---------------- AI 口播文案 ----------------


class CopyStore:
    """AI 写的口播文案缓存。放这里是因为 pipeline 和 server 都要用。

    键复用 `asr._cache_key()`（路径 + mtime + 大小）—— 与 ASR 缓存同一套，
    素材换了自动失效，不另造一套键。

    值 `{'text','source','role','label','at'}`。`source` 是关键：
      'ai'      模型生成的，重新生成会覆盖
      'edited'  人工改过的，**除非显式 force 否则不覆盖** ——
                否则用户改完一批，下次跑全量就被模型悄悄冲掉了
    """

    def __init__(self, path=None):
        self.path = path or config.COPY_CACHE
        self._data = self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return {}
        items = d.get("items")
        return items if isinstance(items, dict) else {}

    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        # 临时文件 + 原子替换，与 record_manifest() 同形：
        # 中途崩掉不会留下半截 JSON 把缓存读废
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "items": self._data}, f,
                      ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    @staticmethod
    def key(path):
        return asr._cache_key(path)

    def get(self, path):
        """返回该片段的记录，没有则 None。"""
        try:
            return self._data.get(self.key(path))
        except OSError:
            return None

    def text(self, path):
        r = self.get(path) or {}
        return (r.get("text") or "").strip()

    def put(self, path, text, source="ai", role="", label=""):
        self._data[self.key(path)] = {
            "text": text, "source": source, "role": role, "label": label,
            "at": int(time.time()),
        }

    def make(self, clip, duration, backend, force=False):
        """取或生成一个片段的文案。返回 (文本, 是否新生成)。

        人工改过的（source='edited'）不重生成，除非 force。
        """
        cur = self.get(clip.path)
        if cur and not force:
            return (cur.get("text") or "").strip(), False
        if cur and cur.get("source") == "edited" and force:
            # force 也不覆盖人工修改 —— force 的意思是「重跑模型」，
            # 不是「丢掉我改的东西」。要丢得先在界面上清空那条。
            return (cur.get("text") or "").strip(), False

        frames = vision.extract_frames(
            clip.path, os.path.join(config.WORK_DIR, "frames"),
            config.FFMPEG, dur=None)
        lo, hi = vision.char_range_for(duration)
        txt = backend.write_copy(
            frames, role=clip.role, desc=clip.desc,
            max_chars=hi, min_chars=lo)
        for f in frames:
            try:
                os.remove(f)
            except OSError:
                pass
        if not txt:
            return "", False
        self.put(clip.path, txt, source="ai", role=clip.role,
                 label=clip.label)
        self.save()
        return txt, True


def warm_point_text(pools, recognizer, work, copy_store=None,
                    vision_backend=None, on_event=None, should_stop=None):
    """先识别每个卖点变体组的代表片段，让语义聚类能读到 ASR 原文。
    顺带给无口播的那几个补上 AI 文案，让它们也有真实文本可聚类。

    为什么需要：`build_theme_map()` 跑在 `run()` 开头，**早于任何识别**，
    而 `point_texts()` 只读缓存。全新安装的 exe 用户目录里没缓存，
    33 组就全部回落用文件名标签 —— 标签聚出 14 簇、原文聚出 10 簇，
    去重强度不同，首批成品质量弱一档【实测：exe 首跑就是这样】。

    **不增加识别总量**：这些片段本来在渲染时也要识别一遍，
    这里只是把时间点提前。缓存命中直接返回（见 `asr.Recognizer.recognize`）。
    AI 文案同理，渲染时也要生成，且同样有缓存。

    返回 (已识别数, 出声的组数, 补了文案的组数)。
    """
    groups = combo.group_variants(pools.points)
    reps = [g[0] for g in groups]
    total = len(reps)
    done = voiced = made = 0
    for i, c in enumerate(reps, 1):
        if should_stop and should_stop():
            break
        err = None
        try:
            res = recognizer.recognize(c.path, work)
            if res.get("segments"):
                voiced += 1
            elif copy_store is not None and vision_backend is not None:
                # 无口播的才生成。33 组里实测只有 2 组，几次 API 调用。
                dur = tts.probe_duration(c.path, config.FFMPEG)
                if dur > 0:
                    txt, _fresh = copy_store.make(
                        c, dur / config.PLAYBACK_SPEED, vision_backend)
                    if txt:
                        made += 1
            done += 1
        except (RuntimeError, OSError) as e:
            # 单个片段失败不该拖垮整批 —— 聚类会回落用它的标签
            err = str(e)[:200]
        ev = {"type": "prewarm", "done": i, "total": total, "file": c.name}
        if err:
            ev["error"] = err
        if on_event:
            on_event(ev)
    return done, voiced, made


def point_texts(pools):
    """每个卖点变体组的代表文本，用于语义聚类。

    取文本顺序：**ASR 原文 → AI 口播文案 → 文件名标签**。
    ASR 原文是观众真正听到的内容，最优先；无口播片段现在有 AI 文案，
    那也是成品里真会念出来的内容，比人写的文件名概括更贴近实际
    （用户 2026-08-26 定：AI 文案参与聚类）；两者都没有才回落用标签。

    读缓存而不现场识别/生成：识别 33 个片段要几十秒，而 `--limit 2` 这种
    快速验证只需要几秒。缓存跑满后自动切到原文，聚类质量随之提升。
    """
    cache = {}
    if os.path.isfile(config.ASR_CACHE):
        try:
            with open(config.ASR_CACHE, encoding="utf-8") as f:
                cache = json.load(f)
        except (OSError, ValueError):
            cache = {}
    copies = CopyStore()

    texts, from_asr, from_ai = {}, 0, 0
    for g in combo.group_variants(pools.points):
        c = g[0]
        t = ""
        try:
            r = cache.get(asr._cache_key(c.path)) or {}
            t = " ".join(s["text"] for s in r.get("segments", [])).strip()
        except OSError:
            pass
        if t:
            from_asr += 1
        else:
            t = copies.text(c.path)
            if t:
                from_ai += 1
        texts[c.label] = t or c.desc
    return texts, from_asr, from_ai


def build_one(cb, recognizer, backend, rng, work, encoder,
              out_dir=None, bgm_dir=None, sub_size=None, speed=None,
              copy_store=None, vision_backend=None, bgm_volume=None):
    """渲染一条成品。返回 (输出路径, 提示列表)。

    speed 参数废弃但保留接口兼容 —— 现在配音按固定语速合成，
    画面倍速逐段计算（用户 2026-08-26 定，消除各段快慢不一的问题）。
    """
    notes = []
    clip_dir = os.path.join(work, f"c{cb.index:03d}")
    os.makedirs(clip_dir, exist_ok=True)

    voice_parts, subs, timeline, clip_speeds = [], [], 0.0, []

    for i, clip in enumerate(cb.clips):
        dur = tts.probe_duration(clip.path, config.FFMPEG)
        if dur <= 0:
            raise RuntimeError(f"无法读取时长: {clip.path}")

        res = recognizer.recognize(clip.path, work)
        segments = res["segments"]
        text = " ".join(s["text"] for s in segments).strip()

        # 无口播且开了 AI 补文案：让模型看画面写一段，走同一条 TTS + 字幕链路。
        # 构造**单段伪 segment** 后下游一行不用改 —— n==1 的分支本来就是
        # 「起点 timeline、终点 timeline+eff」，切块/分摊时长/渲 PNG 全照常。
        if not text and copy_store is not None and vision_backend is not None:
            try:
                # max_chars_for() 用的那个 eff 已经没了（按固定语速合成不再需要），
                # 传个粗估值进去 —— 占位，模型输出会超就超。下游消化得了。
                guess_eff = dur / 1.2
                ai_text, fresh = copy_store.make(clip, guess_eff, vision_backend)
            except (RuntimeError, OSError) as e:
                # 单个片段生成失败不该拖垮整批，回落静音占位
                ai_text, fresh = "", False
                notes.append(f"{clip.name}: AI 文案生成失败（{str(e)[:120]}）")
            if ai_text:
                text = ai_text
                # 构造的伪 segment 时间戳直接写死 0~dur（还没定倍速）
                segments = [{"start": 0.0, "end": dur, "text": ai_text}]
                src = "新生成" if fresh else "取自缓存"
                notes.append(f"{clip.name}: 无口播，已用 AI 文案配音（{src}）")

        vpath = os.path.join(clip_dir, f"v{i}.mp3")
        if text:
            # 固定语速合成，返回实际时长。
            # 画面倍速 = dur / voice_dur —— 配音短就加速画面、长就放慢画面。
            vpath, voice_dur = tts.synth_fixed(backend, text, vpath,
                                               config.FFMPEG, clip_dir)
            if voice_dur <= 0:
                raise RuntimeError(f"TTS 输出时长为 0: {clip.name}")

            # 画面倍速夹在安全区间内，超出时回落补静音/atempo 压配音。
            # 典型：配音明显偏短（比如 2 字）→ 倍速会 >1.8，不让画面太快，
            # 改成补静音；配音明显偏长 → 倍速 <0.9，不让画面卡顿，改成压配音。
            cs = max(tts.CLIP_SPEED_MIN,
                     min(dur / voice_dur, tts.CLIP_SPEED_MAX))
            eff = dur / cs  # 画面在该倍速下的实际占用时长

            # ⚠️ 这两个分支的方向容易搞反，推导记在这：
            # 理想倍速 raw = dur / voice_dur，cs 是把它夹进 [0.9, 1.8] 的结果。
            #   raw < 0.9（配音**比画面长**）→ cs 被**抬到** 0.9，故 cs > raw
            #     此时 eff = dur/0.9 仍短于 voice_dur → 要 atempo 压配音
            #   raw > 1.8（配音**比画面短**）→ cs 被**压到** 1.8，故 cs < raw
            #     此时 eff = dur/1.8 仍长于 voice_dur → 要补静音
            # 第一版写反了，实测报「补静音失败」（gap 是负数）【2026-08-26】。
            raw = dur / voice_dur
            if cs > raw + 0.01:
                # 配音比画面长，画面已放慢到下限仍不够 —— atempo 压配音
                want_tempo = voice_dur / eff
                vpath_adj = os.path.join(clip_dir, f"v{i}_adj.mp3")
                if tts.apply_atempo(vpath, vpath_adj, want_tempo, config.FFMPEG):
                    vpath = vpath_adj
                    voice_dur = tts.probe_duration(vpath, config.FFMPEG)
                    notes.append(
                        f"{clip.name}: 配音比画面长 {(want_tempo - 1) * 100:.0f}%，"
                        f"已加速压缩（画面倍速已夹到下限 {cs:.2f}）")
                else:
                    notes.append(f"{clip.name}: atempo 失败，配音可能明显不对")
            elif cs < raw - 0.01:
                # 配音比画面短，画面已加速到上限仍有余 —— 补静音
                gap = eff - voice_dur
                vpath_pad = os.path.join(clip_dir, f"v{i}_pad.mp3")
                if tts.pad_to(vpath, vpath_pad, eff, config.FFMPEG, voice_dur):
                    vpath = vpath_pad
                    notes.append(
                        f"{clip.name}: 配音比画面短 {gap:.2f}s，已补静音"
                        f"（画面倍速已夹到上限 {cs:.2f}）")
                else:
                    notes.append(f"{clip.name}: 补静音失败，时长可能不对")

            # 字幕按句摆位，时间平分该片段。
            # ASR 时间戳是原速的，倍速后要同比压缩；AI 文案是单段伪 segment，
            # 走 n==1 分支不受影响。
            n = len(segments)
            for k, s in enumerate(segments):
                st = timeline + (s["start"] / cs if n > 1 else 0.0)
                en = timeline + (s["end"] / cs if n > 1 else eff)
                en = min(en, timeline + eff)
                # 一句再切成 ~8 字的小块先后显示（用户 2026-08-17）。
                # 块时长按**字数比例**分摊该句时长 —— 不等分。
                blocks = subtitle.split_blocks(s["text"])
                if not blocks:
                    continue
                chars = sum(len(b) for b in blocks)
                span = max(en - st, 0.0)
                at = st
                for j, btext in enumerate(blocks):
                    png = subtitle.render_png(
                        btext, os.path.join(clip_dir, f"s{i}_{k}_{j}.png"),
                        config.FONT_PATH,
                        sub_size if sub_size is not None
                        else config.SUBTITLE_SIZE,
                        shadow=config.SUBTITLE_SHADOW)
                    # 末块直接收到句尾，避免累加误差留下缝隙
                    bend = en if j == len(blocks) - 1 else \
                        at + span * len(btext) / chars
                    if png:
                        subs.append((png, at, bend))
                    at = bend
            clip_speeds.append(cs)
        else:
            # 无口播：静音占位，画面倍速 1.0。不配字幕（用户 2026-08-14 决定）
            backend_stub = tts.StubBackend(config.FFMPEG)
            eff = dur  # 没配音不用倍速，按原长
            backend_stub.synth("", vpath, target=eff)
            clip_speeds.append(1.0)
            if res["note"]:
                notes.append(f"{clip.name}: {res['note']}")

        voice_parts.append(vpath)
        timeline += eff

    voice = render.concat_audio(voice_parts,
                                 os.path.join(clip_dir, "voice.mp3"),
                                 config.FFMPEG)
    vol = config.BGM_VOLUME if bgm_volume is None else bgm_volume
    bgm = pick_bgm(rng, bgm_dir) if vol > 0 else None
    if bgm is None and vol > 0:
        notes.append("无 BGM（两层 bgm 目录都为空，见 docs/资源需求清单.md）")

    out_dir = out_dir or config.OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"混剪_{cb.index:03d}.mp4")
    render.render([c.path for c in cb.clips], voice, subs, out, config.FFMPEG,
                  bgm=bgm, total_dur=timeline, encoder=encoder,
                  clip_speeds=clip_speeds, bgm_volume=vol)
    return out, notes


def run(source=None, points=None, hook_limit=None, limit=0, seed=None,
        out_dir=None, bgm_dir=None, sub_size=None, dedup=True, speed=None,
        ai_copy=None, on_event=None, should_stop=None, bgm_volume=None):
    """跑一批混剪。命令行和 HTTP 层都走这里。

    on_event(dict)  —— 进度回调。事件形如
                       {'type':'start'|'item'|'done', ...}
    should_stop()   —— 返回 True 则在下一条开始前停止
    """
    def emit(**ev):
        if on_event:
            on_event(ev)

    speed = speed or config.PLAYBACK_SPEED
    # 0 是合法值（不加 BGM），所以不能用 `or`
    bgm_volume = config.BGM_VOLUME if bgm_volume is None else bgm_volume
    ai_copy = config.AI_COPY if ai_copy is None else ai_copy
    pools, stats = scan(source)

    # recognizer 提到聚类之前 —— 聚类要读 ASR 原文，得先有原文。
    # 构造本身不加载模型（`Recognizer.model` 是懒加载的 property），
    # 所以不预热时这行的代价仍然接近零。
    recognizer = asr.Recognizer(config.MODEL_DIR, config.FFMPEG,
                                config.ASR_CACHE)
    os.makedirs(config.WORK_DIR, exist_ok=True)

    copy_store = CopyStore() if ai_copy else None
    vision_backend = vision.make_backend() if ai_copy else None

    # 预热只在「全量 + 开去重」时做。
    # 限量跑不预热：`--limit 2` 现在几秒出片，冷缓存下预热 33 个片段要两分钟，
    # 会毁掉这条快速验证路径（CLAUDE.md 要求改 Python 必须跑 --limit 2）。
    warm_note = ""
    if dedup and not limit:
        n, voiced, made = warm_point_text(
            pools, recognizer, config.WORK_DIR,
            copy_store=copy_store, vision_backend=vision_backend,
            on_event=on_event, should_stop=should_stop)
        warm_note = f"；已预热 {n} 个卖点代表片段（{voiced} 个有口播"
        warm_note += f"，{made} 个补了 AI 文案）" if made else "）"
        # 预热要两分钟，中途停止得当场收手，不能接着渲一整批
        if should_stop and should_stop():
            emit(type="stopped", done=0, total=0)
            return {"ok": 0, "total": 0, "failed": [], "notes": [],
                    "seconds": 0.0, "out_dir": out_dir or config.OUTPUT_DIR}
    elif dedup and limit:
        warm_note = "；限量跑跳过 ASR 预热，聚类可能回落用文件名标签"

    theme_map, theme_note = build_theme_map(pools, dedup)
    theme_note += warm_note
    combos = combo.build_combos(
        pools,
        point_count=points if points is not None else config.POINT_COUNT,
        hook_limit=hook_limit if hook_limit is not None
        else config.HOOK_USE_LIMIT,
        seed=seed, theme_map=theme_map)
    if limit:
        combos = combos[:limit]

    encoder = render.pick_encoder(config.FFMPEG)
    out_dir = out_dir or config.OUTPUT_DIR
    emit(type="start", total=len(combos), encoder=encoder,
         backend=config.TTS_BACKEND, out_dir=out_dir, stats=stats,
         dedup=dedup, theme_note=theme_note, speed=speed,
         ai_copy=ai_copy, bgm_volume=bgm_volume,
         vision_backend=vision_backend.name if vision_backend else "off")

    backend = make_tts_backend()
    rng = random.Random(seed)

    ok, failed, all_notes = 0, [], []
    t0 = time.time()
    for cb in combos:
        if should_stop and should_stop():
            emit(type="stopped", done=ok, total=len(combos))
            break
        t = time.time()
        try:
            out, notes = build_one(cb, recognizer, backend, rng,
                                   config.WORK_DIR, encoder,
                                   out_dir=out_dir, bgm_dir=bgm_dir,
                                   sub_size=sub_size, speed=speed,
                                   copy_store=copy_store,
                                   vision_backend=vision_backend,
                                   bgm_volume=bgm_volume)
            record_manifest(out_dir, os.path.basename(out), cb, seed)
            ok += 1
            all_notes.extend(notes)
            emit(type="item", index=cb.index, total=len(combos), ok=True,
                 file=os.path.basename(out),
                 size_mb=round(os.path.getsize(out) / 1e6, 1),
                 seconds=round(time.time() - t, 1), notes=notes)
        except (RuntimeError, OSError) as e:
            failed.append({"index": cb.index, "error": str(e)[:300]})
            emit(type="item", index=cb.index, total=len(combos), ok=False,
                 error=str(e)[:300], seconds=round(time.time() - t, 1))

    shutil.rmtree(config.WORK_DIR, ignore_errors=True)
    result = {"ok": ok, "total": len(combos), "failed": failed,
              "notes": sorted(set(all_notes)),
              "seconds": round(time.time() - t0, 1), "out_dir": out_dir}
    emit(type="done", **result)
    return result


def main():
    # Windows 控制台/管道默认 GBK，编不了 ⚠ ✓ ✗ 这些字符，
    # 输出重定向到文件时会直接 UnicodeEncodeError 崩掉【实测】。
    # errors='replace' 兜底：字体缺字最多显示成 ?，不会中断渲染。
    #
    # line_buffering=True：不加的话输出重定向到文件时 Python 块缓冲，
    # 全量跑（40 分钟）的日志会长时间是 0 字节，看起来像卡死
    # 【实测 2026-08-26 全量跑时被骗过一次，只能靠数输出目录的成品才确认在跑】。
    # 双击 exe 走真实控制台不受影响（tty 自动行缓冲）。
    # `launcher.py` 早就加了这个参数，这里当初漏了。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace",
                               line_buffering=True)

    ap = argparse.ArgumentParser(description="分镜自动化混剪")
    ap.add_argument("--source", default=config.SOURCE_DIR, help="分镜根目录")
    ap.add_argument("--points", type=int, default=config.POINT_COUNT,
                    help="每条用几个卖点")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条")
    ap.add_argument("--speed", type=float, default=config.PLAYBACK_SPEED,
                    help="画面倍速，1.0 = 原速（默认 %(default)s）")
    ap.add_argument("--seed", type=int, default=None, help="固定随机种子")
    ap.add_argument("--no-dedup", action="store_true",
                    help="关闭卖点语义去重，接受同一条里出现近义卖点")
    ap.add_argument("--no-ai-copy", action="store_true",
                    help="关闭 AI 补口播文案，无口播片段回落静音占位")
    ap.add_argument("--bgm-volume", type=float, default=config.BGM_VOLUME,
                    help="BGM 音量百分比，0 = 不加 BGM（默认 %(default)s）")
    ap.add_argument("--dry-run", action="store_true", help="只看组合不渲染")
    args = ap.parse_args()

    pools, stats = scan(args.source)
    print(f"素材: {pools.summary()}")
    if stats["unparsed"]:
        print(f"⚠ 无法解析 {len(stats['unparsed'])} 个文件（命名不合规范）:")
        for u in stats["unparsed"][:5]:
            print(f"    {u}")

    if args.dry_run:
        theme_map, note = build_theme_map(pools, not args.no_dedup)
        print(note)
        combos = combo.build_combos(pools, point_count=args.points,
                                    hook_limit=config.HOOK_USE_LIMIT,
                                    seed=args.seed, theme_map=theme_map)
        if args.limit:
            combos = combos[:args.limit]
        print(f"组合方案: {len(combos)} 条\n")
        for cb in combos:
            print(cb.describe())
        return

    def on_event(ev):
        t = ev["type"]
        if t == "start":
            print(f"组合方案: {ev['total']} 条\n")
            print(ev["theme_note"])
            print(f"编码器: {ev['encoder']}")
            # 不再打「画面倍速」—— 用户 2026-08-26 定：配音按固定语速合成、
            # 画面逐段去适配，所以没有单一倍速值可报。
            # 前端那个倍速滑块是**播放/导出时**的后处理，与渲染无关。
            print("语速: 固定（画面逐段适配配音时长）")
            print(f"BGM 音量: {ev['bgm_volume']}%"
                  + ("（不加 BGM）" if ev["bgm_volume"] <= 0 else ""))
            print(f"配音后端: {ev['backend']}"
                  + ("  ⚠ 静音占位，等火山引擎凭证"
                     if ev["backend"] == "stub" else ""))
            if not ev["ai_copy"]:
                print("AI 补口播: 已关闭")
            elif ev["vision_backend"] == "stub":
                print("AI 补口播: ⚠ 未配置 ARK_API_KEY，无口播片段仍走静音占位")
            else:
                print(f"AI 补口播: {ev['vision_backend']}")
            print(f"输出目录: {ev['out_dir']}\n")
        elif t == "item":
            if ev["ok"]:
                print(f"[{ev['index']:3d}/{ev['total']}] ✓ {ev['file']}  "
                      f"{ev['size_mb']}MB  {ev['seconds']}s")
            else:
                print(f"[{ev['index']:3d}/{ev['total']}] ✗ 失败: "
                      f"{ev['error'][:120]}")

    r = run(source=args.source, points=args.points, limit=args.limit,
            seed=args.seed, dedup=not args.no_dedup, speed=args.speed,
            ai_copy=not args.no_ai_copy, bgm_volume=args.bgm_volume,
            on_event=on_event)

    print(f"\n完成 {r['ok']}/{r['total']} 条，用时 {r['seconds']:.0f}s")
    print(f"输出: {r['out_dir']}")

    if r["failed"]:
        print(f"\n失败 {len(r['failed'])} 条:")
        for f in r["failed"]:
            print(f"  #{f['index']}: {f['error']}")

    if r["notes"]:
        print(f"\n提示 ({len(r['notes'])} 项):")
        for n in r["notes"][:15]:
            print(f"  - {n}")


if __name__ == "__main__":
    main()
