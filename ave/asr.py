"""语音识别：把分镜口播转成带时间轴的字幕，结果缓存。

设计要点：
- **按源片段缓存**。55 个片段在 39 条成品里反复出现，识别一次就够。
  缓存键用文件路径 + mtime + 大小，素材换了会自动失效。
- **VAD 语音占比做幻觉闸门**。实测 Whisper 对无人声音频会吐出训练数据里的
  字幕组水印（「字幕by索兰娅」「请不吝点赞订阅转发」「Amara.org」），
  语音占比过低就判为无口播，直接返回空，不让幻觉进成品。
- **繁体转简体**。实测 16/55 个片段识别结果混入繁体字（檯面/後面/乾），
  有 opencc 就转，没装则用内置常见字映射兜底。
"""

import hashlib
import json
import os
import re
import subprocess

# 语音占比低于此值判为无口播。实测有效片段均 >=73%，废片 <=23%，闸门开在中间。
MIN_SPEECH_RATIO = 0.50

# Whisper 幻觉出来的水印文本。命中就整段丢弃。
HALLUCINATION_PATTERNS = [
    r"字幕\s*by", r"Amara\.org", r"请不吝", r"点赞.*订阅", r"订阅.*转发",
    r"打赏支持", r"明镜与点点", r"关注我的频道", r"感谢观看", r"下集再见",
    r"^\s*(谢谢|感谢)大家\s*$",
]

# opencc 缺席时的兜底映射，覆盖实测出现过的繁体字
FALLBACK_T2S = str.maketrans({
    "檯": "台", "後": "后", "乾": "干", "來": "来", "這": "这", "裏": "里",
    "麵": "面", "發": "发", "豐": "丰", "體": "体", "幹": "干", "製": "制",
    "於": "于", "個": "个", "們": "们", "與": "与", "時": "时", "會": "会",
    "點": "点", "無": "无", "還": "还", "開": "开", "關": "关", "現": "现",
    "東": "东", "西": "西", "們": "们", "個": "个", "說": "说", "讓": "让",
    "電": "电", "點": "点", "潔": "洁", "節": "节", "綿": "绵", "順": "顺",
    "麼": "么", "樣": "样", "頭": "头", "習": "习", "點": "点", "麗": "丽",
})


def _to_simplified(text):
    try:
        from opencc import OpenCC
        return OpenCC("t2s").convert(text)
    except ImportError:
        return text.translate(FALLBACK_T2S)


# 人工纠正表（用户 2026-08-26 要求）。Whisper 同音误识里
# **领域词表救不回来的**那些，在这里逐条替换。
#
# 与 `DOMAIN_PROMPT` 的分工：词表是**事前**引导（喂 initial_prompt，
# 让模型倾向于输出这些词），这张表是**事后**修正 —— 有些错就算喂了词表
# 也照错，比如「拿哪块」→「哪哪块」（“哪”本身在词表覆盖不到的位置）。
#
# ⚠️ 只放**确认听错**的，别放「我觉得这么说更好」的改写 ——
# 字幕要忠实于口播实际说的话，不然字幕和人声对不上更糟。
#
# ⚠️ 改这张表后要**清 ASR 缓存对应条目**才生效，或用 force=True 重识别。
# 缓存里存的是修正后的文本（在 recognize() 里就替换掉了）。
CORRECTIONS = {
    # 用户 2026-08-26 在混剪_002 第 13 秒听出来的
    "哪哪块": "拿哪块",
    # 以下是按同音词对扫描 52 段全文找出来的（2026-08-26）
    "股巢味": "股潮味",          # 同一句话在别的文件夹里识别对了，比对得出
    "压海绵": "百洁绵",
    # ⚠️ 短词要带上下文，"身手"/"低进" 单独替换会误伤
    # （「身手不凡」「低进度」之类），虽然本产品语境里不太可能出现，
    # 但纠正表是全局生效的，宁可写长一点。
    "几样身手就有": "几样伸手就有",
    "重力低进": "重力滴进",
}


def _apply_corrections(text):
    """套用人工纠正表。"""
    for wrong, right in CORRECTIONS.items():
        if wrong in text:
            text = text.replace(wrong, right)
    return text


def _is_hallucination(text):
    t = text.strip()
    if not t:
        return True
    for p in HALLUCINATION_PATTERNS:
        if re.search(p, t, re.I):
            return True
    return False


def _cache_key(path):
    st = os.stat(path)
    raw = f"{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def extract_wav(video, wav_path, ffmpeg):
    """抽 16k 单声道 wav —— Whisper 的输入格式。"""
    subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", video,
         "-vn", "-ar", "16000", "-ac", "1", wav_path],
        capture_output=True, check=False,
    )
    return os.path.isfile(wav_path)


def speech_ratio(wav_path):
    """VAD 测语音占比。用来判断有没有真人在说话。"""
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    audio = decode_audio(wav_path, sampling_rate=16000)
    total = len(audio) / 16000
    if total <= 0:
        return 0.0
    stamps = get_speech_timestamps(audio, VadOptions())
    speech = sum(s["end"] - s["start"] for s in stamps) / 16000
    return speech / total


# 领域词表。喂给 Whisper 的 initial_prompt，纠正同音误识。
# 实测未加时的错误：抹布→师妈不/妈不、湿物→失误、镂空篮→楼空栏、
# 悬空→玄空、洗碗布→石马布。这些词在厨房沥水架场景里高频出现。
DOMAIN_PROMPT = (
    "厨房沥水收纳架产品介绍，简体中文。常用词：抹布、湿抹布、洗碗布、"
    "百洁布、海绵、清洁刷、洗洁精、沥水、悬空、湿物、错层、镂空篮、"
    "接水盘、底盘、水槽、台面、收纳、通风、承重、晾干、"
    "高低杆、两层杆、错层杆、挂杆。"
)


class Recognizer:
    """带缓存的语音识别器。"""

    def __init__(self, model_dir, ffmpeg, cache_path,
                 compute_type="int8", device="cpu", prompt=DOMAIN_PROMPT):
        self.model_dir = model_dir
        self.ffmpeg = ffmpeg
        self.cache_path = cache_path
        self.compute_type = compute_type
        self.device = device
        self.prompt = prompt
        self._model = None
        self._cache = self._load_cache()

    def _load_cache(self):
        if os.path.isfile(self.cache_path):
            try:
                with open(self.cache_path, encoding="utf-8") as f:
                    return json.load(f)
            except (ValueError, OSError):
                pass
        return {}

    def _save_cache(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.cache_path)),
                    exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=1)

    @property
    def model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self.model_dir, device=self.device,
                                       compute_type=self.compute_type)
        return self._model

    def recognize(self, video, work_dir, force=False):
        """识别一个片段，返回 {'segments': [...], 'speech_ratio': x, 'note': ''}。

        segments 里每项是 {'start','end','text'}，时间相对该片段起点。
        无口播时 segments 为空列表，note 说明原因。
        """
        key = _cache_key(video)
        if not force and key in self._cache:
            return self._cache[key]

        os.makedirs(work_dir, exist_ok=True)
        wav = os.path.join(work_dir, f"asr_{key}.wav")
        if not extract_wav(video, wav, self.ffmpeg):
            result = {"segments": [], "speech_ratio": 0.0,
                      "note": "无法抽取音频"}
            self._cache[key] = result
            self._save_cache()
            return result

        ratio = speech_ratio(wav)
        if ratio < MIN_SPEECH_RATIO:
            result = {"segments": [], "speech_ratio": round(ratio, 3),
                      "note": f"语音占比 {ratio:.0%}，判为无口播，跳过字幕与配音"}
            self._cache[key] = result
            self._save_cache()
            os.remove(wav)
            return result

        segs, _info = self.model.transcribe(
            wav, language="zh", vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=self.prompt,
        )
        out, dropped = [], 0
        for s in segs:
            # 顺序有意义：先转简体再套纠正表 —— 表里的键写的是简体，
            # 反过来会漏掉繁体形态的同一个错。
            txt = _apply_corrections(_to_simplified(s.text.strip()))
            if _is_hallucination(txt):
                dropped += 1
                continue
            out.append({"start": round(s.start, 3), "end": round(s.end, 3),
                        "text": txt})

        note = ""
        if dropped:
            note = f"丢弃 {dropped} 段疑似幻觉文本"
        if not out:
            note = (note + "；") if note else ""
            note += "识别结果全部为幻觉，判为无口播"

        result = {"segments": out, "speech_ratio": round(ratio, 3),
                  "note": note}
        self._cache[key] = result
        self._save_cache()
        os.remove(wav)
        return result
