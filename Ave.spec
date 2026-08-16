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
datas += [
    ("ffmpeg.exe", "."),
    ("fonts", "fonts"),
    ("web", "web"),
]

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
