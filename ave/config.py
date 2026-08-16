"""配置。所有可调项集中在这里，运营给的凭证也填这里。

**应用目录 / 用户数据目录分离**（打包用）：
  应用目录（`_ROOT`）      更新时整体替换 —— exe、ffmpeg、字体、前端产物
  用户数据（`_USER_DIR`）  更新不碰 —— 1.5G 模型、ASR 缓存、BGM

模型和缓存用「查找顺序」而非写死一个位置：先看用户数据目录，
再看应用目录（共享盘手动拷模型也支持），都没有才用用户数据目录作为下载目标。
这样源码态能继续用项目里已有的 1.5G 模型和 55 条缓存，不会白下一遍、
也不会因为缓存空了让卖点语义聚类静默退化成全部回落标签。
"""

import os
import sys

# ---------------- 路径 ----------------

FROZEN = getattr(sys, "frozen", False)


def _app_root():
    """应用目录。冻结态是 exe 所在目录，源码态是项目根。"""
    if FROZEN:
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bundle_root():
    """随包资源目录。

    PyInstaller 6 的 onedir 把 datas 放进 `_internal/`（即 `sys._MEIPASS`），
    **不是** exe 同目录【实测：不处理这个，冻结后找不到 ffmpeg/字体/前端】。
    两个位置都要找：`_internal/` 是打包进去的，exe 同目录是人手动拷的。
    """
    return getattr(sys, "_MEIPASS", None) or _app_root()


def _user_root():
    """用户数据目录。`%LOCALAPPDATA%\\Ave`，拿不到就回落 `~/.ave`。"""
    base = os.environ.get("LOCALAPPDATA")
    if base and os.path.isdir(base):
        return os.path.join(base, "Ave")
    return os.path.join(os.path.expanduser("~"), ".ave")


def _first_existing(candidates, default):
    """返回第一个存在的路径，都不存在则返回 default（新数据的落点）。"""
    for p in candidates:
        if os.path.exists(p):
            return p
    return default

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

_ROOT = _app_root()
_BUNDLE = _bundle_root()
_USER_DIR = _user_root()


def _resource(*parts):
    """随包资源查找：exe 同目录（手动拷的优先）→ `_internal/`（打包进去的）。"""
    return _first_existing(
        [os.path.join(_ROOT, *parts), os.path.join(_BUNDLE, *parts)],
        os.path.join(_ROOT, *parts))

# ffmpeg 查找顺序：随包带的（exe 同目录）→ 系统 PATH → 剪映（开发期兜底）。
# 随包带 GPL full build：剪映那份是裁剪版（无 drawtext/libx264），
# 且动态链接 7 个 DLL 不能单独拷走，办公机上没有【实测】。
def find_ffmpeg():
    import shutil
    bundled = _resource("ffmpeg.exe")
    if os.path.isfile(bundled):
        return bundled
    sys_ff = shutil.which("ffmpeg")
    if sys_ff:
        return sys_ff
    jianying = r"D:\Tool\JianyingPro\11.2.0.14339\ffmpeg.exe"
    if os.path.isfile(jianying):
        return jianying
    raise RuntimeError(
        "找不到 ffmpeg。应在 exe 同目录放 ffmpeg.exe，"
        "或安装 ffmpeg 到 PATH。")


FFMPEG = find_ffmpeg()

# 字幕字体。切这个开关换字体，两种都随包带。
#   新青年体   ⚠️ 内部名标注 Non-Commercial Use，商用授权风险已知
#              （用户 2026-08-14 决定先用着）
#   思源黑体   SIL OFL，可商用，无风险
SUBTITLE_FONT = "新青年体"

FONT_FILES = {
    "新青年体": "新青年体.ttf",
    "思源黑体": "SourceHanSansSC-Bold.otf",
}


def find_font(name=None):
    """字体查找顺序：随包的 `fonts/` → 剪映字体目录（开发期兜底）。"""
    fname = FONT_FILES.get(name or SUBTITLE_FONT, FONT_FILES["新青年体"])
    bundled = _resource("fonts", fname)
    if os.path.isfile(bundled):
        return bundled
    jianying = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "JianyingPro", "User Data", "Resources", "Font", fname)
    return jianying   # 不存在也返回 —— /api/health 会报字体缺失，不在导入期崩


FONT_PATH = find_font()

# 工作目录放用户数据目录：冻结态应用目录可能不可写（Program Files），
# 且这是每次跑完就删的临时文件，不该混在「更新时整体替换」的应用目录里。
WORK_DIR = os.path.join(_USER_DIR, ".work")

# ASR 缓存。项目里已有的优先 —— 换到空缓存会让 55 个片段重新识别，
# 且卖点语义聚类会因为读不到原文而全部回落用标签，去重质量静默变差。
CACHE_DIR = _first_existing(
    [os.path.join(_USER_DIR, "cache"), os.path.join(_ROOT, ".cache")],
    os.path.join(_USER_DIR, "cache"))
ASR_CACHE = os.path.join(CACHE_DIR, "asr.json")

# 语音识别模型。medium 比 small 明显准：small 把「抹布」听成「妈不」、
# 「悬空」听成「玄空」、「洗碗布」听成「石马布」，medium 实测都对【实测】。
# 代价是 1.5G vs 484M，单片段 CPU 约 4s vs 1.6s。
# 办公机分发时若嫌大可换回 fw_small，牺牲专业词准确度。
MODEL_NAME = "fw_medium"
MODEL_DIR = _first_existing(
    [os.path.join(_USER_DIR, "models", MODEL_NAME),
     os.path.join(_ROOT, "models", MODEL_NAME)],
    os.path.join(_USER_DIR, "models", MODEL_NAME))

# BGM 目录。运营把买好授权的轻快 BGM 放进来（见 docs/资源需求清单.md）
BGM_DIR = _first_existing(
    [os.path.join(_USER_DIR, "bgm"), os.path.join(_ROOT, "bgm")],
    os.path.join(_USER_DIR, "bgm"))

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
