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
from ave import asr, config, render, subtitle, tts  # noqa: E402


def build_theme_map(pools, dedup=True):
    """算卖点语义簇。返回 (label->簇号, 说明文字)。

    dedup=False 时返回空表 —— 抽样退化成只去变体不去语义，
    等于接受同主题重复（界面上的开关走这条路）。
    """
    if not dedup:
        return {}, "已关闭语义去重，同一条里可能出现多个卖点讲同一件事"
    texts, from_asr = point_texts(pools)
    tm = combo.auto_cluster(texts)
    n = len(set(tm.values()))
    note = (f"语义聚类：{len(texts)} 个卖点组 → {n} 个主题"
            f"（{from_asr} 组用 ASR 原文，{len(texts) - from_asr} 组回落用标签）")
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
    """从 BGM 目录随机挑一首。目录不存在或为空则返回 None。"""
    bgm_dir = bgm_dir or config.BGM_DIR
    if not os.path.isdir(bgm_dir):
        return None
    tracks = [os.path.join(bgm_dir, f)
              for f in sorted(os.listdir(bgm_dir))
              if os.path.splitext(f)[1].lower() in
              (".mp3", ".wav", ".m4a", ".aac", ".flac")]
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


def warm_point_asr(pools, recognizer, work, on_event=None, should_stop=None):
    """先识别每个卖点变体组的代表片段，让语义聚类能读到 ASR 原文。

    为什么需要：`build_theme_map()` 跑在 `run()` 开头，**早于任何识别**，
    而 `point_texts()` 只读缓存。全新安装的 exe 用户目录里没缓存，
    33 组就全部回落用文件名标签 —— 标签聚出 14 簇、原文聚出 10 簇，
    去重强度不同，首批成品质量弱一档【实测：exe 首跑就是这样】。

    **不增加识别总量**：这些片段本来在渲染时也要识别一遍，
    这里只是把时间点提前。缓存命中直接返回（见 `asr.Recognizer.recognize`）。

    返回 (已识别数, 出声的组数)。
    """
    groups = combo.group_variants(pools.points)
    reps = [g[0] for g in groups]
    total = len(reps)
    done = voiced = 0
    for i, c in enumerate(reps, 1):
        if should_stop and should_stop():
            break
        try:
            res = recognizer.recognize(c.path, work)
            if res.get("segments"):
                voiced += 1
            done += 1
        except (RuntimeError, OSError) as e:
            # 单个片段识别失败不该拖垮整批 —— 聚类会回落用它的标签
            if on_event:
                on_event({"type": "prewarm", "done": i, "total": total,
                          "file": c.name, "error": str(e)[:200]})
            continue
        if on_event:
            on_event({"type": "prewarm", "done": i, "total": total,
                      "file": c.name})
    return done, voiced


def point_texts(pools):
    """每个卖点变体组的代表文本，用于语义聚类。

    优先用 ASR 缓存里的口播原文 —— 那是观众真正听到的内容，
    文件名标签只是人写的概括，可能有偏差。缓存里没有（还没识别过、
    或被幻觉闸门判为无口播）就回落用标签的内容概括。

    读缓存而不现场识别：识别 33 个片段要几十秒，而 `--limit 2` 这种
    快速验证只需要几秒。缓存跑满后自动切到原文，聚类质量随之提升。
    """
    cache = {}
    if os.path.isfile(config.ASR_CACHE):
        try:
            with open(config.ASR_CACHE, encoding="utf-8") as f:
                cache = json.load(f)
        except (OSError, ValueError):
            cache = {}

    texts, from_asr = {}, 0
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
        texts[c.label] = t or c.desc
    return texts, from_asr


def build_one(cb, recognizer, backend, rng, work, encoder,
              out_dir=None, bgm_dir=None, sub_size=None):
    """渲染一条成品。返回 (输出路径, 提示列表)。"""
    notes = []
    clip_dir = os.path.join(work, f"c{cb.index:03d}")
    os.makedirs(clip_dir, exist_ok=True)

    voice_parts, subs, timeline = [], [], 0.0

    for i, clip in enumerate(cb.clips):
        dur = tts.probe_duration(clip.path, config.FFMPEG)
        if dur <= 0:
            raise RuntimeError(f"无法读取时长: {clip.path}")

        res = recognizer.recognize(clip.path, work)
        text = " ".join(s["text"] for s in res["segments"]).strip()

        vpath = os.path.join(clip_dir, f"v{i}.mp3")
        if text:
            # 有口播：TTS 合成并贴合画面时长
            v = tts.synth_fit(backend, text, dur, vpath, config.FFMPEG,
                              clip_dir)
            if v.note:
                notes.append(f"{clip.name}: {v.note}")
            # 字幕按句摆位，时间平分该片段
            n = len(res["segments"])
            for k, s in enumerate(res["segments"]):
                png = subtitle.render_png(
                    s["text"], os.path.join(clip_dir, f"s{i}_{k}.png"),
                    config.FONT_PATH,
                    sub_size if sub_size is not None else config.SUBTITLE_SIZE,
                    shadow=config.SUBTITLE_SHADOW)
                if png:
                    st = timeline + (s["start"] if n > 1 else 0.0)
                    en = timeline + (s["end"] if n > 1 else dur)
                    subs.append((png, st, min(en, timeline + dur)))
        else:
            # 无口播：静音占位，不配字幕（用户 2026-08-14 决定：保留画面）
            backend_stub = tts.StubBackend(config.FFMPEG)
            backend_stub.synth("", vpath, target=dur)
            if res["note"]:
                notes.append(f"{clip.name}: {res['note']}")

        voice_parts.append(vpath)
        timeline += dur

    voice = render.concat_audio(voice_parts,
                               os.path.join(clip_dir, "voice.mp3"),
                               config.FFMPEG)
    bgm = pick_bgm(rng, bgm_dir)
    if bgm is None:
        notes.append("无 BGM（bgm 目录为空，见 docs/资源需求清单.md）")

    out_dir = out_dir or config.OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"混剪_{cb.index:03d}.mp4")
    render.render([c.path for c in cb.clips], voice, subs, out, config.FFMPEG,
                  bgm=bgm, total_dur=timeline, encoder=encoder)
    return out, notes


def run(source=None, points=None, hook_limit=None, limit=0, seed=None,
        out_dir=None, bgm_dir=None, sub_size=None, dedup=True,
        on_event=None, should_stop=None):
    """跑一批混剪。命令行和 HTTP 层都走这里。

    on_event(dict)  —— 进度回调。事件形如
                       {'type':'start'|'item'|'done', ...}
    should_stop()   —— 返回 True 则在下一条开始前停止
    """
    def emit(**ev):
        if on_event:
            on_event(ev)

    pools, stats = scan(source)

    # recognizer 提到聚类之前 —— 聚类要读 ASR 原文，得先有原文。
    # 构造本身不加载模型（`Recognizer.model` 是懒加载的 property），
    # 所以不预热时这行的代价仍然接近零。
    recognizer = asr.Recognizer(config.MODEL_DIR, config.FFMPEG,
                                config.ASR_CACHE)
    os.makedirs(config.WORK_DIR, exist_ok=True)

    # 预热只在「全量 + 开去重」时做。
    # 限量跑不预热：`--limit 2` 现在几秒出片，冷缓存下预热 33 个片段要两分钟，
    # 会毁掉这条快速验证路径（CLAUDE.md 要求改 Python 必须跑 --limit 2）。
    warm_note = ""
    if dedup and not limit:
        n, voiced = warm_point_asr(pools, recognizer, config.WORK_DIR,
                                   on_event=on_event,
                                   should_stop=should_stop)
        warm_note = f"；已预热 {n} 个卖点代表片段（{voiced} 个有口播）"
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
         dedup=dedup, theme_note=theme_note)

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
                                   sub_size=sub_size)
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
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="分镜自动化混剪")
    ap.add_argument("--source", default=config.SOURCE_DIR, help="分镜根目录")
    ap.add_argument("--points", type=int, default=config.POINT_COUNT,
                    help="每条用几个卖点")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条")
    ap.add_argument("--seed", type=int, default=None, help="固定随机种子")
    ap.add_argument("--no-dedup", action="store_true",
                    help="关闭卖点语义去重，接受同一条里出现近义卖点")
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
            print(f"配音后端: {ev['backend']}"
                  + ("  ⚠ 静音占位，等火山引擎凭证"
                     if ev["backend"] == "stub" else ""))
            print(f"输出目录: {ev['out_dir']}\n")
        elif t == "item":
            if ev["ok"]:
                print(f"[{ev['index']:3d}/{ev['total']}] ✓ {ev['file']}  "
                      f"{ev['size_mb']}MB  {ev['seconds']}s")
            else:
                print(f"[{ev['index']:3d}/{ev['total']}] ✗ 失败: "
                      f"{ev['error'][:120]}")

    r = run(source=args.source, points=args.points, limit=args.limit,
            seed=args.seed, dedup=not args.no_dedup, on_event=on_event)

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
