"""渲染：把一条组合方案渲成 mp4。

流程（一次 ffmpeg 调用完成，不落中间文件）：
  1. 视频轨：N 个片段 concat
  2. 字幕轨：每句一张透明 PNG，按时间窗 overlay 叠上去
  3. 音频轨：配音 concat + BGM 混音（BGM 压低音量、裁到总长）

关键约束【实测】：剪映自带 ffmpeg 是裁剪版，没有 drawtext/subtitles/ass，
所以字幕走 PNG overlay；有 h264_nvenc/amf/qsv/mf，任何 Windows 机器都能硬编码。
"""

import os
import subprocess

# BGM 相对配音压低多少（分贝）。口播要压得住 BGM。
BGM_GAIN_DB = -18.0

# 编码器优先级：硬编码优先，都不可用时报错而不是静默出废片
ENCODER_CANDIDATES = ["h264_nvenc", "h264_qsv", "h264_amf", "h264_mf"]


def pick_encoder(ffmpeg):
    """探测本机可用的 h264 编码器。"""
    r = subprocess.run([ffmpeg, "-hide_banner", "-encoders"],
                       capture_output=True, text=True, errors="ignore")
    avail = r.stdout
    for e in ENCODER_CANDIDATES:
        if e in avail:
            return e
    raise RuntimeError(
        "找不到可用的 h264 编码器。剪映自带 ffmpeg 无 libx264，"
        "需要显卡或 MediaFoundation 支持。")


def build_filter(n_clips, subs, has_bgm, total_dur):
    """拼出 filter_complex。

    subs: [(png_path, start, end), ...] 已按时间排序
    输入顺序约定：
      [0..n-1]      视频片段
      [n]           配音（已按片段拼好的整条音轨）
      [n+1]         BGM（可选）
      之后           字幕 PNG
    """
    parts = []

    # 视频拼接
    vin = "".join(f"[{i}:v]" for i in range(n_clips))
    parts.append(f"{vin}concat=n={n_clips}:v=1:a=0[vcat]")

    # 字幕逐张叠加，用 enable 控制显示时间窗
    png_base = n_clips + (2 if has_bgm else 1)
    cur = "vcat"
    for k, (_png, start, end) in enumerate(subs):
        idx = png_base + k
        out = f"v{k}"
        parts.append(
            f"[{cur}][{idx}:v]overlay=0:0:"
            f"enable='between(t,{start:.3f},{end:.3f})'[{out}]")
        cur = out
    parts.append(f"[{cur}]null[vout]")

    # 音频：配音 + BGM 混音
    if has_bgm:
        bgm = n_clips + 1
        parts.append(f"[{bgm}:a]volume={BGM_GAIN_DB}dB,"
                     f"atrim=0:{total_dur:.3f},asetpts=PTS-STARTPTS[bgmv]")
        parts.append(f"[{n_clips}:a][bgmv]amix=inputs=2:duration=first:"
                     f"dropout_transition=0:normalize=0[aout]")
    else:
        parts.append(f"[{n_clips}:a]anull[aout]")

    return ";".join(parts)


def render(clips, voice_audio, subs, out_path, ffmpeg,
           bgm=None, total_dur=None, encoder=None):
    """渲染一条成品。

    clips:       [视频文件路径, ...] 按拼接顺序
    voice_audio: 整条配音音轨（已按片段拼好）
    subs:        [(png路径, 起, 止), ...]
    bgm:         BGM 文件路径，可为 None
    total_dur:   总时长，用于裁 BGM
    """
    encoder = encoder or pick_encoder(ffmpeg)
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]

    for c in clips:
        cmd += ["-i", c]
    cmd += ["-i", voice_audio]
    if bgm:
        cmd += ["-stream_loop", "-1", "-i", bgm]
    for png, _s, _e in subs:
        cmd += ["-i", png]

    fc = build_filter(len(clips), subs, bool(bgm), total_dur or 0)
    cmd += [
        "-filter_complex", fc,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", encoder, "-b:v", "6M",
        "-c:a", "aac", "-b:a", "128k",
        "-r", "24", "-pix_fmt", "yuv420p",
        "-shortest", out_path,
    ]

    r = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
    if r.returncode != 0 or not os.path.isfile(out_path):
        raise RuntimeError(f"渲染失败:\n{r.stderr[-1500:]}")
    return out_path


def concat_audio(parts, out_path, ffmpeg):
    """把多段配音按顺序拼成一条音轨。"""
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    for p in parts:
        cmd += ["-i", p]
    ain = "".join(f"[{i}:a]" for i in range(len(parts)))
    cmd += ["-filter_complex", f"{ain}concat=n={len(parts)}:v=0:a=1[o]",
            "-map", "[o]", out_path]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
    if r.returncode != 0 or not os.path.isfile(out_path):
        raise RuntimeError(f"配音拼接失败:\n{r.stderr[-800:]}")
    return out_path
