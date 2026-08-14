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


def pick_bgm(rng):
    """从 BGM 目录随机挑一首。目录不存在或为空则返回 None。"""
    if not os.path.isdir(config.BGM_DIR):
        return None
    tracks = [os.path.join(config.BGM_DIR, f)
              for f in sorted(os.listdir(config.BGM_DIR))
              if os.path.splitext(f)[1].lower() in
              (".mp3", ".wav", ".m4a", ".aac", ".flac")]
    return rng.choice(tracks) if tracks else None


def build_one(cb, recognizer, backend, rng, work, encoder):
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
                    config.FONT_PATH, config.SUBTITLE_SIZE,
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
    bgm = pick_bgm(rng)
    if bgm is None:
        notes.append("无 BGM（bgm 目录为空，见 docs/资源需求清单.md）")

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    out = os.path.join(config.OUTPUT_DIR, f"混剪_{cb.index:03d}.mp4")
    render.render([c.path for c in cb.clips], voice, subs, out, config.FFMPEG,
                  bgm=bgm, total_dur=timeline, encoder=encoder)
    return out, notes


def main():
    ap = argparse.ArgumentParser(description="分镜自动化混剪")
    ap.add_argument("--source", default=config.SOURCE_DIR, help="分镜根目录")
    ap.add_argument("--points", type=int, default=config.POINT_COUNT,
                    help="每条用几个卖点")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条")
    ap.add_argument("--seed", type=int, default=None, help="固定随机种子")
    ap.add_argument("--dry-run", action="store_true", help="只看组合不渲染")
    args = ap.parse_args()

    pools = combo.scan_product(args.source)
    print(f"素材: {pools.summary()}")
    if pools.unparsed:
        print(f"⚠ 无法解析 {len(pools.unparsed)} 个文件（命名不合规范）:")
        for u in pools.unparsed[:5]:
            print(f"    {os.path.basename(u)}")

    combos = combo.build_combos(pools, point_count=args.points,
                               hook_limit=config.HOOK_USE_LIMIT,
                               seed=args.seed)
    if args.limit:
        combos = combos[:args.limit]
    print(f"组合方案: {len(combos)} 条\n")

    if args.dry_run:
        for cb in combos:
            print(cb.describe())
        return

    encoder = render.pick_encoder(config.FFMPEG)
    print(f"编码器: {encoder}")
    print(f"配音后端: {config.TTS_BACKEND}"
          + ("  ⚠ 静音占位，等火山引擎凭证"
             if config.TTS_BACKEND == "stub" else ""))
    print(f"输出目录: {config.OUTPUT_DIR}\n")

    recognizer = asr.Recognizer(config.MODEL_DIR, config.FFMPEG,
                                config.ASR_CACHE)
    backend = make_tts_backend()
    rng = random.Random(args.seed)
    os.makedirs(config.WORK_DIR, exist_ok=True)

    ok, failed, all_notes = 0, [], []
    t0 = time.time()
    for cb in combos:
        t = time.time()
        try:
            out, notes = build_one(cb, recognizer, backend, rng,
                                   config.WORK_DIR, encoder)
            ok += 1
            size = os.path.getsize(out) / 1e6
            print(f"[{cb.index:3d}/{len(combos)}] ✓ "
                  f"{os.path.basename(out)}  {size:.1f}MB  "
                  f"{time.time() - t:.1f}s")
            all_notes.extend(notes)
        except (RuntimeError, OSError) as e:
            failed.append((cb.index, str(e)[:200]))
            print(f"[{cb.index:3d}/{len(combos)}] ✗ 失败: {str(e)[:120]}")

    print(f"\n完成 {ok}/{len(combos)} 条，用时 {time.time() - t0:.0f}s")
    print(f"输出: {config.OUTPUT_DIR}")

    if failed:
        print(f"\n失败 {len(failed)} 条:")
        for i, e in failed:
            print(f"  #{i}: {e}")

    uniq = sorted(set(all_notes))
    if uniq:
        print(f"\n提示 ({len(uniq)} 项):")
        for n in uniq[:15]:
            print(f"  - {n}")

    shutil.rmtree(config.WORK_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
