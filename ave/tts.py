"""TTS 配音：把 ASR 文本合成为语音，并调语速贴合画面时长。

用户 2026-08-14 决定：**调语速让配音贴合画面**。画面时长不动，
用 TTS 的语速参数把配音压/拉到与画面一致，超出范围时用 atempo 微调。

后端可换。当前两个：
  StubBackend   —— 产出等时长静音。**没有凭证也能跑通整条 pipeline**，
                   用来验证组合/字幕/渲染，不用等运营开通火山引擎
  VolcanoBackend —— 火山引擎大模型语音合成。**2026-08-16 起已实测出片**，
                   全量 39 条实跑过（2026-08-17）。网络抖动会读超时，故带重试

音色说明：「小姐姐」不在火山引擎公开音色表里（那是剪映 App 内部显示名）。
音色 ID 形如 zh_female_shuangkuaisisi_moon_bigtts，需运营从控制台取。
"""

import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass

# 火山引擎 speed_ratio 的合理区间。超出会明显失真。
SPEED_MIN, SPEED_MAX = 0.8, 1.3
# atempo 微调容差 —— ±10% 内人耳听不出
ATEMPO_TOLERANCE = 0.10

# ---------------- 固定语速模式（用户 2026-08-26 定） ----------------
#
# 原来 `synth_fit()` 是**每段各自算语速去贴合自己的时长**：
#     want = natural / target_dur; speed = clamp(want, 0.8, 1.3)
# 文本相对时长越短，语速被压得越慢。实测后果：
#     真人口播 3.84~10.64 字/秒（差 2.8 倍），AI 文案只有 2.17~2.85
# 用户实听反馈「有的念得快有的慢」「AI 那段明显听得出来」，就是这个。
#
# 现在改成**固定语速合成，让画面倍速去适配配音**（用户 2026-08-26 定）：
#     配音按 FIXED_SPEED 合成 → 量出真实时长 → 画面倍速 = 原时长/配音时长
# 这样全片语速绝对一致，且口播说完不会留白（画面同步收紧）。
FIXED_SPEED = 1.0

# 画面倍速的安全区间。超出就不再让画面适配，回落到补静音/压配音 ——
# 画面快过 1.8 倍像快进、慢于 0.9 倍会看出卡顿。
CLIP_SPEED_MIN, CLIP_SPEED_MAX = 0.9, 1.8


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


def _explain_tts_error(code, detail):
    """把服务端错误翻成运营看得懂的一句话，后面附原文。

    运营看不懂 `AccountOverdueError` 和一串英文 —— 直接说该去做什么。
    原文保留在后面，排查时还是要它。
    """
    hints = [
        ("AccountOverdueError", "账户欠费，去火山引擎控制台结清后重试"),
        ("overdue", "账户欠费，去火山引擎控制台结清后重试"),
        # ⚠️ 这条字面是「资源未授权」，**但实测多半是欠费**：
        # 2026-08-28 欠费期间报的就是它（resource_id=volc.seedtts.default），
        # 结清后同一套凭证、同一个音色原样就通了。
        # 所以提示**先让人查余额**，别一上来就去翻音色授权列表。
        ("not granted", "账户欠费或服务被停（实测欠费也报这个）。"
                        "先去控制台查余额结清；余额正常再看语音合成服务"
                        "是否开通、VOLCANO_VOICE 是否在已授权音色里"),
        ("Quota", "额度用尽或超配额，去控制台查用量"),
        ("authenticate", "凭证无效，检查 credentials.json 的 "
                         "VOLCANO_APPID / VOLCANO_TOKEN"),
        ("Forbidden", "凭证无权限或账户异常（欠费/未开通），"
                      "去火山引擎控制台确认"),
    ]
    for needle, msg in hints:
        if needle.lower() in (detail or "").lower():
            return f"{msg}。原文: {detail[:300]}"
    if code == 403:
        return ("账户异常或凭证无权限（常见是欠费/未开通），"
                f"去火山引擎控制台确认。原文: {detail[:300]}")
    return detail[:400] or f"HTTP {code}，无错误详情"


class VolcanoBackend:
    """火山引擎大模型语音合成。

    **接口未实测** —— 需要运营提供 appid / access_token / 音色 ID 后验证。
    调研得到的接口形态：HTTP/WebSocket，鉴权用 appid + access_token，
    参数含 voice_type、speed_ratio、volume_ratio、pitch_ratio，
    且支持返回逐字时间戳（对字幕对齐有用，当前未用到）。
    """

    name = "volcano"
    ENDPOINT = "https://openspeech.bytedance.com/api/v1/tts"
    TIMEOUT = 30
    RETRIES = 3
    BACKOFF = 1.5  # 秒，指数退避：1.5 → 3.0

    def __init__(self, appid, access_token, voice_type, cluster="volcano_tts"):
        self.appid = appid
        self.access_token = access_token
        self.voice_type = voice_type
        self.cluster = cluster

    def synth(self, text, out_path, speed=1.0, target=None):
        import base64
        import urllib.error
        import urllib.request

        def build_req():
            # reqid 每次重试都换新的。服务端若按 reqid 做幂等去重，
            # 复用同一个可能直接拿回上次的失败结果，重试就白做了。
            payload = {
                "app": {"appid": self.appid, "token": self.access_token,
                        "cluster": self.cluster},
                "user": {"uid": "ave-remix"},
                "audio": {"voice_type": self.voice_type, "encoding": "mp3",
                          "speed_ratio": round(speed, 3)},
                "request": {"reqid": str(uuid.uuid4()), "text": text,
                            "operation": "query"},
            }
            return urllib.request.Request(
                self.ENDPOINT,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer;{self.access_token}"},
            )

        # 一条片子要调 5~6 次，全量 39 条约 270 次。实测 0.4% 会读超时
        # （2026-08-17 全量跑 #6 挂在 read timeout），不重试就是整条出片失败。
        last = None
        for attempt in range(self.RETRIES):
            try:
                with urllib.request.urlopen(
                        build_req(), timeout=self.TIMEOUT) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                # ⚠️ **这个 except 必须排在 URLError 前面** ——
                # `HTTPError` 是 `URLError` 的子类，写反了永远进不来，
                # 403 会被当成网络抖动白重试 3 次（等 4.5 秒退避），
                # 且服务端错误原文被吞掉，用户只看到「调用失败」
                # 看不出真因【2026-08-28 实测：欠费 403 就是这样被埋掉的】。
                detail = ""
                try:
                    detail = e.read().decode("utf-8", "replace")[:600]
                except OSError:
                    pass
                if 400 <= e.code < 500:
                    raise RuntimeError(
                        f"火山引擎 TTS 返回 {e.code}: "
                        f"{_explain_tts_error(e.code, detail)}") from e
                last = RuntimeError(f"火山引擎 TTS {e.code}: {detail}")
            except (urllib.error.URLError, ValueError, OSError) as e:
                last = e
            if attempt + 1 < self.RETRIES:
                time.sleep(self.BACKOFF * (2 ** attempt))
        else:
            raise RuntimeError(
                f"火山引擎 TTS 调用失败（重试 {self.RETRIES} 次）: {last}"
            ) from last

        data = body.get("data")
        if not data:
            raise RuntimeError(f"火山引擎 TTS 无音频返回: {body.get('message')}")
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(data))
        return True


def synth_fixed(backend, text, out_path, ffmpeg, work_dir, speed=FIXED_SPEED):
    """固定语速合成，不贴合目标时长。

    返回 (out_path, 实际时长)。
    成功返回时 out_path 保证存在且可读；失败抛 RuntimeError。

    **不做任何 atempo/apad**。调用方量出实际时长后，由**画面倍速**去适配
    （用户 2026-08-26 定）—— 这样全片语速绝对一致，口播说完画面同步收紧。
    """
    os.makedirs(work_dir, exist_ok=True)
    tmp = os.path.join(work_dir, "_fixed.mp3")
    if not backend.synth(text, tmp, speed=speed, target=None):
        raise RuntimeError("TTS 合成失败")
    dur = probe_duration(tmp, ffmpeg)
    if dur <= 0:
        raise RuntimeError("无法测量 TTS 输出时长")
    if tmp != out_path:
        with open(tmp, "rb") as s, open(out_path, "wb") as d:
            d.write(s.read())
    return out_path, dur


def synth_fit(backend, text, target_dur, out_path, ffmpeg, work_dir):
    """合成配音并贴合 target_dur。

    ⚠️ **已废弃** —— 用户 2026-08-26 反馈「各段语速差太大」后，
    改用 synth_fixed() + 画面倍速适配。这里保留只是怕别的地方还在调。

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
