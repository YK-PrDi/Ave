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


def _first_usable_model(candidates, default):
    """返回第一个**真能用**的模型目录，判据是 `model.bin` 在不在。

    ⚠ 不能只判目录存在【实测踩过】：下载中断会留下一个有 config.json、
    tokenizer.json 却没有 model.bin 的半截目录。那种目录按「存在」算，
    会**遮挡**后面那个完整的模型，加载时才报
    `Unable to open file 'model.bin'` —— 而且此时聚类已经静默回落用标签了。
    """
    for p in candidates:
        if os.path.isfile(os.path.join(p, "model.bin")):
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

# 字幕字体。切这个开关换字体，都随包带。
#   普惠体     阿里巴巴普惠体 3.0，免费商用无需授权 —— **默认**（用户 2026-08-16 定）
#              Heavy(105) 而不是 Black(115)：115 在 720p 上笔画多的字容易糊成一团，
#              105 字重够又不糊。要更重就把开关改成 "普惠体Black"。
#   思源黑体   SIL OFL，可商用，普惠体缺失时的退路
#   新青年体   ⚠️ 内部名就是 `WenYue XinQingNianTi (Non-Commercial Use)`
#              【Pillow 实测读出】，带货是商用场景。不做默认。
#              风险详情见 licenses/fonts/新青年体-授权说明.md
SUBTITLE_FONT = "普惠体"

FONT_FILES = {
    "普惠体": "AlibabaPuHuiTi-3-105-Heavy.ttf",
    "普惠体Black": "AlibabaPuHuiTi-3-115-Black.ttf",
    "思源黑体": "SourceHanSansSC-Bold.otf",
    "新青年体": "新青年体.ttf",
}

# 字体查找失败时的回落顺序。普惠体要手动下（官方站是 JS 应用、OSS 直链 403、
# GitHub 上全是非官方转载，脚本不敢代下），所以缺它时要能自动退到思源黑体，
# 不能让字幕直接崩。
FONT_FALLBACK = ["普惠体", "思源黑体", "新青年体"]


def _font_candidate(fname):
    """单个字体文件的查找：随包的 `fonts/` → 剪映字体目录（开发期兜底）。"""
    bundled = _resource("fonts", fname)
    if os.path.isfile(bundled):
        return bundled
    jianying = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "JianyingPro", "User Data", "Resources", "Font", fname)
    return jianying if os.path.isfile(jianying) else None


def find_font(name=None):
    """解析字幕字体路径。先试指定的那个，缺了按 FONT_FALLBACK 往下退。

    ⚠ 要能自动回落：普惠体只能手动下载（官方站是 JS 应用、阿里 OSS 直链
    403、GitHub 上 18 个仓库全是非官方转载 —— 从随机镜像下字体二进制
    无法验证是否官方原版，风险和那份 1.44MB 假 OTF 同类）。
    所以缺它时退到思源黑体继续出片，而不是让字幕整条链崩掉。
    """
    want = name or SUBTITLE_FONT
    order = [want] + [f for f in FONT_FALLBACK if f != want]
    for key in order:
        fname = FONT_FILES.get(key)
        if not fname:
            continue
        p = _font_candidate(fname)
        if p:
            return p
    # 全都找不到也要返回路径而不是抛异常 —— 否则 import config 就崩，
    # /api/health 都开不出来。健康检查会把 font 报成 False。
    return _resource("fonts", FONT_FILES.get(want, FONT_FILES["思源黑体"]))


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
MODEL_DIR = _first_usable_model(
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
# 三项凭证填齐后自动切 volcano，不用手动改这行（见下方 _tts_backend()）。
#
# ┌─ 凭证怎么填：两种方式，二选一 ─────────────────────────────┐
# │ A. 环境变量（推荐，不进 git）                              │
# │      setx AVE_VOLCANO_APPID  "你的appid"                   │
# │      setx AVE_VOLCANO_TOKEN  "你的token"                   │
# │      setx AVE_VOLCANO_VOICE  "音色ID"                      │
# │    setx 之后要**重开终端**才生效。                          │
# │                                                            │
# │ B. 直接写下面的字符串（省事，但⚠ 本文件进版本库，          │
# │    凭证会被 git 记录 —— 别推到公开仓库）                    │
# └────────────────────────────────────────────────────────────┘
# Cluster 不用运营去控制台找 —— `volcano_tts` 是标准默认值。

VOLCANO_APPID = os.environ.get("AVE_VOLCANO_APPID", "")
VOLCANO_TOKEN = os.environ.get("AVE_VOLCANO_TOKEN", "")
VOLCANO_CLUSTER = os.environ.get("AVE_VOLCANO_CLUSTER", "volcano_tts")
# 音色 ID。「小姐姐」是剪映内部显示名，火山引擎公开音色表里没有同名条目，
# 需运营在控制台试听后提供最接近的 ID。
VOLCANO_VOICE = os.environ.get("AVE_VOLCANO_VOICE", "")


def _tts_backend():
    """三项凭证齐了就用 volcano，缺任一项回落 stub（静音占位）。

    自动判断而不是让人再改一个开关 —— 否则「填了凭证但忘了改 TTS_BACKEND」
    会静默产出 39 条静音成品，跑完才发现。
    """
    if VOLCANO_APPID and VOLCANO_TOKEN and VOLCANO_VOICE:
        return "volcano"
    return "stub"


TTS_BACKEND = _tts_backend()
