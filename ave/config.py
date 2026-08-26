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

# BGM 分两层（用户 2026-08-26 定，为接入羽刃做准备）：
#   内置层  应用目录 `bgm/`（打包落 `_internal/bgm`）—— 我们维护，随应用更新替换
#   自定义层 用户数据目录 `bgm/` —— 各公司业务人员自己加，更新应用不碰
# 抽 BGM 时两层合并成一个候选池，随机挑一首。只有自定义层可增删。
# `BGM_DIR` 仍指自定义层，保持既有引用（health/JobReq.bgm_dir）语义不变。
BGM_BUILTIN_DIR = _resource("bgm")
BGM_DIR = _first_existing(
    [os.path.join(_USER_DIR, "bgm"), os.path.join(_ROOT, "bgm")],
    os.path.join(_USER_DIR, "bgm"))

# 认作 BGM 的扩展名。原先散在 pipeline 和 server 两处各写一遍，收拢到这里。
BGM_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".flac")


def bgm_layers(custom=None):
    """BGM 两层，返回 [(绝对路径, 'builtin'|'custom'), ...]。

    custom 传了就覆盖自定义层。

    去重且标签不错位：源码态两层可能解析到同一路径（没建用户目录时
    `BGM_DIR` 会回落到应用目录），不去重那批曲子会被算两遍、抽中概率翻倍。
    撞上时保留 `builtin` —— 宁可让界面拒绝删除，也不能把随包授权的曲子
    当成用户自己加的删掉。
    """
    layers, seen = [], set()
    for d, tag in ((BGM_BUILTIN_DIR, "builtin"), (custom or BGM_DIR, "custom")):
        p = os.path.realpath(d)
        if p in seen:
            continue
        seen.add(p)
        layers.append((p, tag))
    return layers


def bgm_dirs(custom=None):
    """只要目录列表时用这个。"""
    return [d for d, _tag in bgm_layers(custom)]


def list_bgm(custom=None):
    """列出两层里的 BGM 文件，返回 [(路径, 'builtin'|'custom'), ...]。"""
    tracks = []
    for d, tag in bgm_layers(custom):
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if os.path.splitext(f)[1].lower() in BGM_EXTS:
                tracks.append((os.path.join(d, f), tag))
    return tracks

# ---------------- 组合规则 ----------------

POINT_COUNT = 5      # 每条成品用几个卖点
HOOK_USE_LIMIT = 3   # 每个钩子用满几次即废弃
RANDOM_SEED = None   # 固定成整数可复现同一批组合

# ---------------- 播放倍速 ----------------

# 画面倍速（用户 2026-08-26 定 1.2，界面可调）。
# 语义是**画面加速、成品变短**：33s 的成品变 27s。
# 口播本来就是按画面时长合成的，所以画面变短，配音自动说得更紧 ——
# 不是渲完再整体变速（那会同时拉高音调）。
# 时间轴基准在 pipeline 侧换成 dur/speed，渲染侧逐路 setpts=PTS/speed。
PLAYBACK_SPEED = 1.2

# ---------------- 字幕样式 ----------------

SUBTITLE_SIZE = 12       # 剪映字号刻度，需求要求 10-15
SUBTITLE_SHADOW = True   # 需求要求带阴影

# ---------------- 配音 ----------------

# 后端：'stub' 产出等时长静音（无凭证时验证全流程用）
#      'volcano' 走火山引擎，需三项凭证
# 三项齐了自动切 volcano，不用手动改开关（见下方 _tts_backend()）。
#
# ⚠️ **凭证不写在这个文件里**，读用户数据目录的 credentials.json：
#
#     %LOCALAPPDATA%\Ave\credentials.json
#
# 为什么不写在这：① 本文件进版本库，写这里会被 git 记录；
# ② PyInstaller 把整个 `ave` 包打进 exe，写这里等于**谁拿到 exe 都能提取出
# 你的 token**。放用户数据目录两条都避开了（和模型/缓存/BGM 同一套逻辑）。
#
# 换机器：单独拷那个 json 过去，别提交。
# 也支持环境变量覆盖（优先级更高）：AVE_VOLCANO_APPID / TOKEN / VOICE。
# Cluster 不用去控制台找 —— `volcano_tts` 是标准默认值。

CREDENTIALS_FILE = os.path.join(_USER_DIR, "credentials.json")


def _load_credentials():
    """读用户数据目录的凭证。文件不存在或坏了都返回空表，不抛异常 ——
    没凭证只是回落 stub 静音，不该让 import config 就崩。"""
    try:
        import json
        with open(CREDENTIALS_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


_CRED = _load_credentials()


def _cred(key, default=""):
    """环境变量优先，其次 credentials.json，最后默认值。"""
    return os.environ.get(f"AVE_{key}") or _CRED.get(key) or default


VOLCANO_APPID = _cred("VOLCANO_APPID")
VOLCANO_TOKEN = _cred("VOLCANO_TOKEN")
VOLCANO_CLUSTER = _cred("VOLCANO_CLUSTER", "volcano_tts")
# 音色 ID。「小姐姐」是剪映内部显示名，火山引擎公开音色表里没有同名条目，
# 需运营在控制台试听后提供最接近的 ID。
VOLCANO_VOICE = _cred("VOLCANO_VOICE")


def _tts_backend():
    """三项凭证齐了就用 volcano，缺任一项回落 stub（静音占位）。

    自动判断而不是让人再改一个开关 —— 否则「填了凭证但忘了改 TTS_BACKEND」
    会静默产出 39 条静音成品，跑完才发现。
    """
    if VOLCANO_APPID and VOLCANO_TOKEN and VOLCANO_VOICE:
        return "volcano"
    return "stub"


TTS_BACKEND = _tts_backend()

# ---------------- 视觉理解（给无口播片段写口播文案） ----------------
#
# ⚠️ **这是独立于 TTS 的另一套凭证**。TTS 那三项（appid / token / 音色）
# 不能用于视觉模型，方舟走 API Key 鉴权。同样放 credentials.json：
#
#     %LOCALAPPDATA%\Ave\credentials.json
#     { "ARK_API_KEY": "...", "ARK_VISION_MODEL": "doubao-seed-2-0-mini-260428" }
#
# `ARK_VISION_MODEL` 可省，省则用下面的默认值。开通步骤见
# docs/资源需求清单.md。环境变量 AVE_ARK_API_KEY / AVE_ARK_VISION_MODEL 优先。
#
# 模型 ID 会随方舟上线新版本变动，所以做成可配 —— 界面的
# 「测试视觉接口」按钮会把方舟的错误原文显示出来，改这里不用改代码。
#
# **默认选 `doubao-seed-evolving`**（2026-08-26 实探后定：本账号已开通且实测出文案）。
#   ⚠️ 它是**滚动别名** —— 实测解析到 `doubao-seed-evolving-latest-version`，
#   方舟会持续换后面那个真实版本。好处是不用跟着改，坏处是效果可能悄悄漂移，
#   文案质量突然变化时先怀疑这里。
#
# ⚠️ **换模型前先确认账号开通了**。实探 23 个 ID，在售的 `doubao-seed-2-*`
#   全部返回 `ModelNotOpen`（ID 对但没开通）。两种 404 含义不同：
#     ModelNotOpen                     ID 正确、模型存在，账号没开通 → 去开通页
#     InvalidEndpointOrModel.NotFound  ID 压根解析不了（别名或已退役）→ 换 ID
#
# ⚠️ **除 evolving 外都必须带日期后缀**。不带日期的别名
#   （`doubao-seed-2-0-mini`）一律 `NotFound`；带日期的（`-260428`）才被识别。
#
# ⚠️ **不要用 `doubao-seed-1-6`** —— 它和 `1-6-flash` / `1-6-vision` / `1-8` /
#   `1-5-vision-pro` 官方标 `Retiring`，实探全部 `NotFound`。曾拿它当默认，是错的。
#
# 开通后可选的在售视觉档（元/百万 token，输入/输出）：
#   2-0-mini-260428 0.2/2.0 · 2-0-lite-260428 0.6/3.6 · 2-1-turbo-260628 3.0/15
#   2-0-pro-260215 3.2/16 · 2-1-pro-260628 6.0/30
#
# ⚠️ **Seedance / Seedream / seed3d 不能用** —— 那些是**生成**模型
#   （文生视频 / 图片生成），Seedance 正是产出我们素材的那个。
#   我们要的是反方向：看图输出文字。
#
# `GET /api/v3/models` 能列出账号可见模型（带 status 字段），比翻控制台快。

ARK_API_KEY = _cred("ARK_API_KEY")
ARK_VISION_MODEL = _cred("ARK_VISION_MODEL", "doubao-seed-evolving")


def _vision_backend():
    """有 Key 就用方舟，没有回落 stub（=保持「无口播就静音占位」旧行为）。"""
    return "ark" if ARK_API_KEY else "stub"


VISION_BACKEND = _vision_backend()

# AI 口播文案缓存。和 ASR 缓存同一个目录 —— 都是「按源片段算一次、
# 反复复用」的东西，且都该跟着用户数据目录走（更新应用不冲掉）。
COPY_CACHE = os.path.join(CACHE_DIR, "copy.json")

# 默认开。关掉即回落到「无口播片段塞静音、不配字幕」的旧行为。
AI_COPY = True
