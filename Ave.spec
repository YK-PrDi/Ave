# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。用 `打包.bat` 跑，别直接 pyinstaller Ave.spec ——
前端产物要先 build 到 web/ 才有东西可打。

**onedir 不用 onefile**：onefile 每次启动要把约 150MB 解压到 temp，慢，
且 ctranslate2 的原生 DLL 在解压目录里容易出问题。

已知难点：ctranslate2 是 PyInstaller 老大难，`ctranslate2.dll` 51.6MB
必须落在包目录旁，靠 collect_all 拿全。faster_whisper 的 VAD 模型
（约 18MB）是 data 不是代码，不显式 collect 就会漏 —— 漏了幻觉闸门失效。
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = []
binaries = []
hiddenimports = []

# ctranslate2：DLL + .pyd + 元数据全要
for mod in ("ctranslate2", "av"):
    d, b, h = collect_all(mod)
    datas += d
    binaries += b
    hiddenimports += h

# faster_whisper 的 VAD 模型等资产
datas += collect_data_files("faster_whisper")

# uvicorn 靠字符串动态导入，PyInstaller 静态分析扫不到
hiddenimports += [
    "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan",
    "uvicorn.lifespan.on", "uvicorn.lifespan.off",
    "huggingface_hub",           # ensure_model() 首次下载用
    "tkinter", "tkinter.filedialog",   # --pick-dir 目录选择框
]

# 随包素材。ffmpeg 和字体放包根，config.py 按 exe 同目录去找。
#
# licenses/ 必须随包 —— 随包的 ffmpeg 是 GPLv3 构建，且 PyAV 自带
# libx264/libx265（GPLv2）两个 DLL 加载进本进程，对外分发时要附许可与
# 源码获取说明。详见 licenses/ffmpeg/SOURCE-OFFER.md。
# `打包.bat` 另外把它拷一份进 web/，让界面页脚能直接链过去。
datas += [
    ("ffmpeg.exe", "."),
    ("fonts", "fonts"),
    ("licenses", "licenses"),
    ("web", "web"),
]

# 随包凭证（用户 2026-08-27 定：内部使用，免得每台机器手配）。
# `打包.bat` 打包前从 `%LOCALAPPDATA%\Ave\credentials.json` 拷成这个名字。
#
# 🔴 **明文，拿到 dist\Ave 的人都能提取出 token**。PyInstaller 的 datas 不加密。
#   · 仅限内部分发；对外发布前删掉这行 + 那个文件，回落成每机一份用户凭证
#   · 落包根（`"."` → `_internal/`），**不准放 web/** ——
#     那目录被 StaticFiles 对外挂，会变成 http://127.0.0.1:8756/... 直接可下
#   · 文件名带 `credentials` 是刻意的：.gitignore 有 `credentials*.json` 规则，
#     故意让它落进那条拦截里，防手滑提交
#
# 条件加：文件不在也能正常打包（回落成每机一份用户凭证），不硬失败。
import os as _os

_CRED_BUNDLE = "_bundled_credentials.json"
if _os.path.isfile(_CRED_BUNDLE):
    datas += [(_CRED_BUNDLE, ".")]
    # ⚠ print 只用 ASCII —— spec 是被 PyInstaller exec 的，走 GBK 控制台，
    # 打中文或 ✓ ⚠ 这类字符会 UnicodeEncodeError 直接崩在解析阶段
    # 【实测 2026-08-27，铁律 2 的同一个坑】。
    print("[Ave.spec] bundling credentials -- INTERNAL DISTRIBUTION ONLY")
else:
    print("[Ave.spec] no bundled credentials, using per-machine user dir")

# ⚠️ 别试图从 av.libs 里剔掉 libx264/libx265 来「去掉 GPL 依赖」。
# 实测：这两个 DLL 在 avcodec 的 **load-time import 表**（.idata）里，
# 不是 delay-load。移走后 avcodec 直接加载失败
# （`Could not find module ... or one of its dependencies`），
# PyAV 起不来 → faster_whisper 的音频解码断掉 → 语音识别整条链废掉。
# 放回去立刻恢复（对照实验已做）。只能保留并在 licenses/ 里如实声明。
#
# ⚠️ 但「剔 DLL」不等于「摘掉 PyAV 依赖」—— 后者另有一条路，2026-08-17
# 部分验过：transcribe() 收 numpy waveform，可用随包 ffmpeg.exe 解码替代
# PyAV（实测相关系数 1.0、识别文本逐字相同）。卡点是 av 在
# faster_whisper/__init__.py 第 1 行就导入，连 WhisperModel 都拖着它。
# **接入宿主项目（羽刃）对外发布前必读 docs/进度与待办.md 第六节** ——
# 那里有完整的传染范围分析和决策依据。别只看本注释就下结论。

a = Analysis(
    ["ave/launcher.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # ⚠️ **必须排掉 torch**：不排实测包体 4.5G，其中 torch 占 4.2G。
    # faster-whisper 是 ctranslate2 的重实现，推理走 ctranslate2、
    # VAD 走 onnxruntime，运行时都不碰 torch —— 它是被传递依赖拖进来的。
    # 排掉后需实跑 exe 验证识别和幻觉闸门仍正常，不能只看体积。
    excludes=["torch", "torchvision", "torchaudio",
              "matplotlib", "scipy", "pandas", "pytest", "IPython",
              "notebook", "tensorboard", "transformers"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Ave",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX 压过的原生 DLL 容易加载失败，不用
    console=True,       # 保留控制台：进度和「已启动」那行要能看见
    disable_windowed_traceback=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Ave",
)
