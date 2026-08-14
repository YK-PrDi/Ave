"""TTS 配音：把 ASR 文本合成为语音，并调语速贴合画面时长。

用户 2026-08-14 决定：**调语速让配音贴合画面**。画面时长不动，
用 TTS 的语速参数把配音压/拉到与画面一致，超出范围时用 atempo 微调。

后端可换。当前两个：
  StubBackend   —— 产出等时长静音。**没有凭证也能跑通整条 pipeline**，
                   用来验证组合/字幕/渲染，不用等运营开通火山引擎
  VolcanoBackend —— 火山引擎大模型语音合成。**接口未实测**，
                   凭证和音色 ID 到位后需验证

音色说明：「小姐姐」不在火山引擎公开音色表里（那是剪映 App 内部显示名）。
音色 ID 形如 zh_female_shuangkuaisisi_moon_bigtts，需运营从控制台取。
"""

import json
import os
import subprocess
import uuid
from dataclasses import dataclass

# 火山引擎 speed_ratio 的合理区间。超出会明显失真。
SPEED_MIN, SPEED_MAX = 0.8, 1.3
# atempo 微调容差 —— ±10% 内人耳听不出
ATEMPO_TOLERANCE = 0.10


@dataclass
class Voiced:
    """一段配音的结果。"""
    path: str
    duration: float
    speed_used: float = 1.0
    atempo_used: float = 1.0
    note: str = ""


def probe_duration(path, ffmpeg):
    """用 ffmpeg -i 解析时长。剪映自带的 ffmpeg 是 --disable-ffprobe 的，
    所以不能用 ffprobe。"""
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", path],
                       capture_output=True, text=True, errors="ignore")
    for line in r.stderr.splitlines():
        if "Duration:" in line:
            t = line.split("Duration:")[1].split(",")[0].strip()
            try:
                h, m, s = t.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
            except ValueError:
                return 0.0
    return 0.0


def apply_atempo(src, dst, tempo, ffmpeg):
    """用 atempo 调时长。tempo > 1 变快变短。

    atempo 只接受 0.5~100，超出会静默失败，所以先夹紧。
    """
    tempo = min(max(tempo, 0.5), 100.0)
    subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
         "-filter:a", f"atempo={tempo:.4f}", dst],
        capture_output=True, check=False,
    )
    return os.path.isfile(dst) and os.path.getsize(dst) > 0


def pad_to(src, dst, total_dur, ffmpeg, cur_dur):
    """在音频尾部补静音，把总时长拉到 total_dur。

    比慢放自然：口播说完留白是正常的，拖腔不是。

    不用 apad —— 剪映自带的裁剪版 ffmpeg 上 `apad=whole_dur` 不按语义工作
    （实测要 5s 只给 2.88s）。显式拼一段静音，行为确定。
    """
    gap = total_dur - cur_dur
    if gap <= 0:
        return False
    subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
         "-i", src,
         "-f", "lavfi", "-t", f"{gap:.3f}", "-i", "anullsrc=r=32000:cl=stereo",
         "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[o]", "-map", "[o]",
         dst],
        capture_output=True, check=False,
    )
    return os.path.isfile(dst) and os.path.getsize(dst) > 0


class StubBackend:
    """产出等时长静音。用于在没有 TTS 凭证时验证整条 pipeline。

    这不是占位敷衍 —— 它让组合、字幕、渲染三个环节现在就能测，
    等火山引擎开通了只换后端，其余不动。
    """

    name = "stub"

    def __init__(self, ffmpeg):
        self.ffmpeg = ffmpeg

    def synth(self, text, out_path, speed=1.0, target=None):
        dur = target or max(1.0, len(text) * 0.22)  # 中文约 4.5 字/秒
        subprocess.run(
            [self.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "anullsrc=r=32000:cl=stereo",
             "-t", f"{dur:.3f}", out_path],
            capture_output=True, check=False,
        )
        return os.path.isfile(out_path)


class VolcanoBackend:
    """火山引擎大模型语音合成。

    **接口未实测** —— 需要运营提供 appid / access_token / 音色 ID 后验证。
    调研得到的接口形态：HTTP/WebSocket，鉴权用 appid + access_token，
    参数含 voice_type、speed_ratio、volume_ratio、pitch_ratio，
    且支持返回逐字时间戳（对字幕对齐有用，当前未用到）。
    """

    name = "volcano"
    ENDPOINT = "https://openspeech.bytedance.com/api/v1/tts"

    def __init__(self, appid, access_token, voice_type, cluster="volcano_tts"):
        self.appid = appid
        self.access_token = access_token
        self.voice_type = voice_type
        self.cluster = cluster

    def synth(self, text, out_path, speed=1.0, target=None):
        import base64
        import urllib.error
        import urllib.request

        payload = {
            "app": {"appid": self.appid, "token": self.access_token,
                    "cluster": self.cluster},
            "user": {"uid": "ave-remix"},
            "audio": {"voice_type": self.voice_type, "encoding": "mp3",
                      "speed_ratio": round(speed, 3)},
            "request": {"reqid": str(uuid.uuid4()), "text": text,
                        "operation": "query"},
        }
        req = urllib.request.Request(
            self.ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer;{self.access_token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, ValueError, OSError) as e:
            raise RuntimeError(f"火山引擎 TTS 调用失败: {e}") from e

        data = body.get("data")
        if not data:
            raise RuntimeError(f"火山引擎 TTS 无音频返回: {body.get('message')}")
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(data))
        return True


def synth_fit(backend, text, target_dur, out_path, ffmpeg, work_dir):
    """合成配音并贴合 target_dur。

    两步走：先按 1.0 语速试合成、量实际时长算出所需语速；
    语速在 [SPEED_MIN, SPEED_MAX] 内就重新合成，超出则夹到边界，
    残余误差用 atempo 补。
    """
    os.makedirs(work_dir, exist_ok=True)
    probe = os.path.join(work_dir, "_probe.mp3")

    if not backend.synth(text, probe, speed=1.0, target=target_dur):
        raise RuntimeError("TTS 合成失败")
    natural = probe_duration(probe, ffmpeg)
    if natural <= 0:
        raise RuntimeError("无法测量 TTS 输出时长")

    # 需要的语速倍率：自然时长 / 目标时长。>1 表示要说快点。
    want = natural / target_dur
    speed = min(max(want, SPEED_MIN), SPEED_MAX)

    if abs(speed - 1.0) < 0.01:
        final, used_speed = probe, 1.0
    else:
        adj = os.path.join(work_dir, "_adj.mp3")
        if not backend.synth(text, adj, speed=speed, target=target_dur):
            raise RuntimeError("TTS 变速合成失败")
        final, used_speed = adj, speed

    cur = probe_duration(final, ffmpeg)
    tempo, note = 1.0, ""

    if cur > 0:
        need = cur / target_dur
        if need > 1.0 + 0.01:
            # 配音比画面长 —— 只能加速。atempo 上限很高，安全。
            tempo = need
            if need > 1.0 + ATEMPO_TOLERANCE:
                note = f"配音比画面长 {(need - 1) * 100:.0f}%，已加速压缩，可能听出变速"
            if apply_atempo(final, out_path, tempo, ffmpeg):
                return Voiced(out_path, probe_duration(out_path, ffmpeg),
                              used_speed, tempo, note)
        elif need < 1.0 - 0.01:
            # 配音比画面短 —— 补静音，不做慢放。
            # 慢放念稿会明显拖腔；口播后留白反而自然。
            gap = target_dur - cur
            if pad_to(final, out_path, target_dur, ffmpeg, cur):
                return Voiced(out_path, probe_duration(out_path, ffmpeg),
                              used_speed, 1.0,
                              f"配音比画面短 {gap:.2f}s，已补静音")

    # 已经贴合，直接搬过去
    if final != out_path:
        with open(final, "rb") as s, open(out_path, "wb") as d:
            d.write(s.read())
    return Voiced(out_path, probe_duration(out_path, ffmpeg), used_speed,
                  1.0, note)
