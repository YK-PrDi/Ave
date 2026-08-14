"""配置。所有可调项集中在这里，运营给的凭证也填这里。"""

import os

# ---------------- 路径 ----------------

# 分镜素材根目录（产品大文件夹，下面是小分镜文件夹）
SOURCE_DIR = r"D:\Download\分镜"

# 成品输出目录：桌面 VEDIO抖音（不存在自动创建）
def desktop_output():
    home = os.path.expanduser("~")
    for name in ("Desktop", "OneDrive/Desktop"):
        d = os.path.join(home, *name.split("/"))
        if os.path.isdir(d):
            return os.path.join(d, "VEDIO抖音")
    return os.path.join(home, "Desktop", "VEDIO抖音")


OUTPUT_DIR = desktop_output()

# ffmpeg。剪映自带的是裁剪版（无 drawtext/subtitles/ass，无 libx264），
# 但有 concat/overlay/amix 和全套硬编码器，够用。
# 若系统 PATH 里有完整 ffmpeg，优先用那个。
def find_ffmpeg():
    import shutil
    sys_ff = shutil.which("ffmpeg")
    if sys_ff:
        return sys_ff
    bundled = r"D:\Tool\JianyingPro\11.2.0.14339\ffmpeg.exe"
    if os.path.isfile(bundled):
        return bundled
    raise RuntimeError("找不到 ffmpeg。请安装 ffmpeg 或确认剪映安装路径。")


FFMPEG = find_ffmpeg()

# 字体。⚠️ 新青年体内部名标注 Non-Commercial Use，商用授权风险已知
# （用户 2026-08-14 决定先用着）。免费商用替代见 docs/资源需求清单.md
FONT_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "JianyingPro", "User Data", "Resources", "Font", "新青年体.ttf")

# 项目内工作目录
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK_DIR = os.path.join(_ROOT, ".work")
CACHE_DIR = os.path.join(_ROOT, ".cache")
ASR_CACHE = os.path.join(CACHE_DIR, "asr.json")
# 语音识别模型。medium 比 small 明显准：small 把「抹布」听成「妈不」、
# 「悬空」听成「玄空」、「洗碗布」听成「石马布」，medium 实测都对【实测】。
# 代价是 1.5G vs 484M，单片段 CPU 约 4s vs 1.6s。
# 办公机分发时若嫌大可换回 fw_small，牺牲专业词准确度。
MODEL_DIR = os.path.join(_ROOT, "models", "fw_medium")

# BGM 目录。运营把买好授权的轻快 BGM 放进来（见 docs/资源需求清单.md）
BGM_DIR = os.path.join(_ROOT, "bgm")

# ---------------- 组合规则 ----------------

POINT_COUNT = 5      # 每条成品用几个卖点
HOOK_USE_LIMIT = 3   # 每个钩子用满几次即废弃
RANDOM_SEED = None   # 固定成整数可复现同一批组合

# ---------------- 字幕样式 ----------------

SUBTITLE_SIZE = 12       # 剪映字号刻度，需求要求 10-15
SUBTITLE_SHADOW = True   # 需求要求带阴影

# ---------------- 配音 ----------------

# 后端：'stub' 产出等时长静音（无凭证时验证全流程用）
#      'volcano' 走火山引擎，需下面三项凭证
TTS_BACKEND = "stub"

VOLCANO_APPID = ""
VOLCANO_TOKEN = ""
VOLCANO_CLUSTER = "volcano_tts"
# 音色 ID。「小姐姐」是剪映内部显示名，火山引擎公开音色表里没有同名条目，
# 需运营在控制台试听后提供最接近的 ID。
VOLCANO_VOICE = ""
