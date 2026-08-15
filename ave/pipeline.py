"""主流程：扫素材 → 组合 → 识别 → 配音 → 渲染 → 导出。

一条命令跑完全部：
    python -m ave.pipeline              # 全量
    python -m ave.pipeline --limit 2    # 只跑 2 条，验证用
    python -m ave.pipeline --dry-run    # 只看组合方案，不渲染
"""

import argparse
import os
import random
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import combo  # noqa: E402
from ave import asr, config, render, subtitle, tts  # noqa: E402


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
        out_dir=None, bgm_dir=None, sub_size=None,
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
    combos = combo.build_combos(
        pools,
        point_count=points if points is not None else config.POINT_COUNT,
        hook_limit=hook_limit if hook_limit is not None
        else config.HOOK_USE_LIMIT,
        seed=seed)
    if limit:
        combos = combos[:limit]

    encoder = render.pick_encoder(config.FFMPEG)
    out_dir = out_dir or config.OUTPUT_DIR
    emit(type="start", total=len(combos), encoder=encoder,
         backend=config.TTS_BACKEND, out_dir=out_dir, stats=stats)

    recognizer = asr.Recognizer(config.MODEL_DIR, config.FFMPEG,
                                config.ASR_CACHE)
    backend = make_tts_backend()
    rng = random.Random(seed)
    os.makedirs(config.WORK_DIR, exist_ok=True)

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
    ap.add_argument("--dry-run", action="store_true", help="只看组合不渲染")
    args = ap.parse_args()

    pools, stats = scan(args.source)
    print(f"素材: {pools.summary()}")
    if stats["unparsed"]:
        print(f"⚠ 无法解析 {len(stats['unparsed'])} 个文件（命名不合规范）:")
        for u in stats["unparsed"][:5]:
            print(f"    {u}")

    if args.dry_run:
        combos = combo.build_combos(pools, point_count=args.points,
                                    hook_limit=config.HOOK_USE_LIMIT,
                                    seed=args.seed)
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
            seed=args.seed, on_event=on_event)

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
