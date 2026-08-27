"""视觉理解：无口播的分镜，让大模型看画面写出口播文案。

为什么需要：`asr.py` 的幻觉闸门会把语音占比 <50% 的片段判为无口播
（实测 33 个卖点组里有 2 组），这些片段过去只能塞等时长静音、不配字幕。
素材是 Seedance 文生视频产出的 AI 视频，没有真人口型要对，
所以给它配一段 AI 写的口播完全可行 —— 走的还是原来那条 TTS + 字幕链路。

和 `tts.py` 一样保持成**纯后端**：只管抽帧和调模型，缓存归调用方
（`pipeline.CopyStore`）管。后端可换，当前两个：
  StubVisionBackend —— 返回空串。没有 API Key 时回落到「静音占位」旧行为，
                       不阻塞出片
  ArkVisionBackend  —— 火山方舟视觉理解。凭证是**独立的 ARK_API_KEY**，
                       与 TTS 那三项（appid/token/音色）不是一套

⚠️ 模型 ID 不靠猜。`server.py` 有 `/api/vision/test` 自检接口，
抽一帧真发一次请求并把方舟返回的错误原文透传出来 —— 模型 ID 不对时
它会直接说该换成什么，改 `credentials.json` 即可，不用改代码。
"""

import base64
import json
import os
import re
import subprocess
import time

from ave import asr, tts

# 抽几帧喂给模型。3 帧够看清「架子 + 环境 + 有没有手在操作」，
# 再多只是线性推高 token 成本（图片 token 占请求的绝大部分）。
DEFAULT_FRAMES = 3
# 帧宽。方舟会把过大的图缩到像素上限内，自己先缩省上传体积。
FRAME_WIDTH = 512

# 中文口播语速，字/秒。**实测值**，不是估的。
#
# ⚠️ 原来写的是 `1.0 / 0.22 = 4.55`，那是抄 `tts.StubBackend` 的 0.22 s/字 ——
# 而 StubBackend 是**产静音占位用的假值**，不代表真人语速。
# 2026-08-26 量了缓存里 52 段真人口播（字数 / 倍速后时长）：
#     范围 3.84 ~ 10.64，中位 5.91，均值 6.21 字/秒
# 用户实听反馈「AI 那段明显比真人慢、听得出是补的」，根因就是这个常数偏低：
# 上限算成 21 字，模型只写 13 字，TTS 为填满窗口把语速压到 2.5 字/秒。
# 改用实测中位数 5.91。
CHARS_PER_SEC = 5.91

# 字数下限占上限的比例。**只给上限不够** —— 实测模型偏保守，
# 给 21 字它只写 13 字（62%）。明确告诉它下限，逼它写够。
MIN_CHARS_RATIO = 0.85

# 模型爱加的包装，生成后剥掉。
_STRIP_PREFIX = re.compile(
    r"^\s*(口播文案|口播|文案|旁白|配音|解说)\s*[:：]\s*", re.I)


def extract_frames(video, out_dir, ffmpeg, n=DEFAULT_FRAMES,
                   width=FRAME_WIDTH, dur=None):
    """均匀抽 n 帧存 jpg，返回路径列表。

    取样点在 `dur*(i+0.5)/n` —— 避开首尾，那里常是黑帧或转场。
    `-ss` 放在 `-i` **之后**是精确 seek（片段只有几秒，代价可忽略）；
    放前面是关键帧对齐的快速 seek，会取到邻近关键帧而不是指定时刻。
    """
    dur = dur if dur and dur > 0 else tts.probe_duration(video, ffmpeg)
    if dur <= 0:
        return []
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(video))[0]
    frames = []
    for i in range(n):
        at = dur * (i + 0.5) / n
        out = os.path.join(out_dir, f"f_{stem}_{i}.jpg")
        subprocess.run(
            [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
             "-i", video, "-ss", f"{at:.3f}", "-frames:v", "1",
             "-vf", f"scale={width}:-2", "-q:v", "3", out],
            capture_output=True, check=False,
        )
        if os.path.isfile(out) and os.path.getsize(out) > 0:
            frames.append(out)
    return frames


def max_chars_for(duration):
    """这段时长最多容得下多少字。留 8% 余量给句末停顿。"""
    return max(6, int(duration * CHARS_PER_SEC * 0.92))


def char_range_for(duration):
    """返回 (下限, 上限)。给下限是为了逼模型写够字数 ——
    只给上限时实测它只写到 62%，配音就得放慢才能填满画面。"""
    hi = max_chars_for(duration)
    lo = max(6, int(hi * MIN_CHARS_RATIO))
    return lo, hi


# 角色决定文案的说话方式。三者在成品里的位置和功能完全不同，
# 用同一套提示词会让钩子写得像卖点、结尾不促单。
ROLE_BRIEF = {
    "hook": "这是视频开头的钩子，要在两三秒内点出一个让人有共鸣的痛点或场景，"
            "引发继续看下去的兴趣。不要在这里介绍产品功能。",
    "point": "这是中间的卖点段，要具体说清画面里正在展示的那一个功能或好处，"
             "只讲一件事，讲透。",
    "ending": "这是结尾促单段，要收束全片并给出行动理由，"
              "语气自然不硬广，不要喊「快来买」这类口号。",
}


def build_prompt(role, desc, max_chars, min_chars=None):
    """拼提示词。

    `desc` 是文件名里人写的内容概括（如「通风悬挂」），
    **是最强的先验**，必须喂 —— 画面能看出「架子挂着抹布」，
    但看不出这一段的叙述重点是通风还是收纳。
    """
    brief = ROLE_BRIEF.get(role, ROLE_BRIEF["point"])
    lines = [
        "你在给一条中文竖版带货短视频写口播。以下是这个片段的几帧画面。",
        brief,
    ]
    if desc:
        lines.append(f"这一段要讲的重点是「{desc}」，务必围绕它写。")
    lines += [
        f"产品背景与常用词：{asr.DOMAIN_PROMPT}",
        # 必须给下限。只给上限时实测模型只写到 62%（21 字上限只写 13 字），
        # 配音为填满画面就得放慢，用户一听就知道是 AI 补的。
        (f"字数**必须落在 {min_chars}~{max_chars} 字之间**，这是硬性要求。"
         f"少于 {min_chars} 字会导致配音过慢、听起来不自然，务必写够。"
         if min_chars else
         f"字数**不超过 {max_chars} 字**，这是硬性要求（口播要贴合画面时长）。"),
        "只输出口播正文本身，简体中文，不要标题、不要引号、不要解释、"
        "不要分镜说明、不要写「口播：」之类的前缀。",
    ]
    return "\n".join(lines)


def clean_copy(text):
    """剥掉模型的包装，转简体。"""
    t = (text or "").strip()
    # 前缀和引号要交替剥：`口播：「…」` 先剥前缀才露出引号，
    # 而 `「口播：…」` 反过来。循环到不再变化为止（最多几轮）。
    for _ in range(4):
        before = t
        t = _STRIP_PREFIX.sub("", t).strip()
        # 整体被引号裹住时脱掉（只脱成对的，句内引号不动）
        for a, b in (('"', '"'), ("“", "”"), ("'", "'"), ("「", "」")):
            if len(t) >= 2 and t.startswith(a) and t.endswith(b):
                t = t[1:-1].strip()
                break
        if t == before:
            break
    # 模型偶尔吐多行（分镜表、要点列表），口播只要连续一段，取最长的一行
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if len(lines) > 1:
        t = max(lines, key=len)
    return asr._to_simplified(t.strip())


class StubVisionBackend:
    """不产文案。没有 ARK_API_KEY 时的回落 —— 调用方拿到空串就走
    原来的「静音占位、不配字幕」分支，出片不受阻塞。"""

    name = "stub"
    note = "未配置 ARK_API_KEY，无法生成 AI 口播文案"

    def write_copy(self, frames, role="point", desc="", max_chars=40,
                   min_chars=None):
        return ""


class ArkVisionBackend:
    """火山方舟视觉理解（Doubao-Seed 系列）。

    走 `chat/completions`，图片以 `data:image/jpeg;base64,...` 内联传入
    （单张 <10MB、请求体 <64MB，我们抽 3 帧 512 宽，量级远低于上限）。
    形态取自方舟官方文档《图片理解》的示例。
    """

    name = "ark"
    ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    TIMEOUT = 60          # 视觉请求比 TTS 慢，给足
    RETRIES = 3
    BACKOFF = 1.5         # 指数退避：1.5s → 3.0s。同 tts.VolcanoBackend

    def __init__(self, api_key, model, endpoint=None):
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint or self.ENDPOINT

    def _payload(self, frames, prompt, max_tokens=400):
        content = []
        for f in frames:
            with open(f, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode("ascii")
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        content.append({"type": "text", "text": prompt})
        return {"model": self.model,
                "messages": [{"role": "user", "content": content}],
                "max_tokens": max_tokens,
                # 关掉深度思考。Doubao-Seed 系列默认会先「思考」，
                # 那些 token **既挤占 max_tokens**（思考完可能没配额输出正文了）
                # **又按最贵的输出价计费**（2.0~30 元/百万，输入才 0.2~6）。
                # 看 3 帧图写 20 字口播不需要推理链。
                # 取值 enabled / disabled / auto（方舟 Chat API 文档）。
                "thinking": {"type": "disabled"}}

    def _post(self, payload):
        """发一次请求，返回 (assistant 文本, 原始响应)。失败抛 RuntimeError。

        重试形态照 `tts.VolcanoBackend`：实测 TTS 有 0.4% 读超时，
        视觉请求体大得多，没有重试同样会让整条出片失败。
        """
        import urllib.error
        import urllib.request

        data = json.dumps(payload).encode("utf-8")
        last = None
        for attempt in range(self.RETRIES):
            req = urllib.request.Request(
                self.endpoint, data=data,
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {self.api_key}"})
            try:
                with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                # 4xx 是凭证/模型 ID/参数错，重试无意义且会浪费一分钟。
                # **把服务端错误原文透传出来** —— 模型 ID 不对时
                # 它会直接说该用什么，这是 /api/vision/test 的价值所在。
                detail = ""
                try:
                    detail = e.read().decode("utf-8", "replace")[:600]
                except OSError:
                    pass
                if 400 <= e.code < 500:
                    raise RuntimeError(
                        f"方舟视觉接口返回 {e.code}: {detail}") from e
                last = RuntimeError(f"方舟视觉接口 {e.code}: {detail}")
            except (urllib.error.URLError, ValueError, OSError) as e:
                last = e
            if attempt + 1 < self.RETRIES:
                time.sleep(self.BACKOFF * (2 ** attempt))
        else:
            raise RuntimeError(
                f"方舟视觉接口调用失败（重试 {self.RETRIES} 次）: {last}"
            ) from last

        choices = body.get("choices") or []
        if not choices:
            raise RuntimeError(
                f"方舟视觉接口无返回内容: {body.get('error') or body}")
        msg = choices[0].get("message") or {}
        txt = msg.get("content")
        # 有些模型把正文放在 reasoning_content 之外的 content 里，
        # 也有返回 list-form content 的形态，两种都收。
        if isinstance(txt, list):
            txt = "".join(p.get("text", "") for p in txt
                          if isinstance(p, dict))
        return (txt or "").strip(), body

    def write_copy(self, frames, role="point", desc="", max_chars=40,
                   min_chars=None):
        """看图写口播。frames 为空则返回空串（调用方回落静音占位）。"""
        if not frames:
            return ""
        prompt = build_prompt(role, desc, max_chars, min_chars)
        txt, _body = self._post(self._payload(frames, prompt))
        out = clean_copy(txt)
        # 超字数不重试 —— 再问一次多半还是超，且贵。TTS 那边本来就会
        # 用 atempo 压（铁律 8 允许加速，只是可能听出变速），交给它。
        return out

    def ping(self, frames=None):
        """连通性自检。返回 {'ok':bool,'model':..,'reply':..,'error':..}。

        真发一次请求 —— 只校验 Key 字符串非空说明不了任何事。
        """
        try:
            if frames:
                txt, body = self._post(
                    self._payload(frames, "用一句话描述这张图里的物品。"),
                    )
            else:
                txt, body = self._post(
                    {"model": self.model,
                     "messages": [{"role": "user", "content": "回复「ok」两个字"}],
                     "max_tokens": 16})
            return {"ok": True, "model": self.model, "reply": txt[:300],
                    "usage": body.get("usage")}
        except RuntimeError as e:
            return {"ok": False, "model": self.model, "error": str(e)[:800]}


def make_backend(api_key=None, model=None):
    """按凭证有无自动选后端。与 `config._tts_backend()` 同一思路 ——
    不让人再改一个开关，否则「填了 Key 但忘了改开关」会静默不生效。"""
    from ave import config
    key = api_key if api_key is not None else config.ARK_API_KEY
    if not key:
        return StubVisionBackend()
    return ArkVisionBackend(key, model or config.ARK_VISION_MODEL)
