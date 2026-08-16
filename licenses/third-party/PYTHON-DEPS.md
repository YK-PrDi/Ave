# 随包 Python 依赖的许可清单

清单由查询已安装包的元数据（`importlib.metadata`）得到，
不是凭印象列的。换依赖版本后建议重查一遍。

**结论先说**：除下面「需要留意」那两项，随包分发的 Python 依赖
全是宽松许可（MIT / BSD / Apache / PSF / MPL / Unlicense），
不对 Ave 自身的源码产生开源要求。

---

## 需要留意的两项

### 1. `av`（PyAV）自带 GPL 编码器 DLL ⚠️

包本身是 **BSD-3-Clause**，但它的预编译 wheel 里带了
`libx264` / `libx265` 两个 DLL，二者为 **GPLv2 or later**。

- 我们只用 PyAV 解码音频（`faster_whisper/audio.py` 里
  `decode_audio` / `AudioResampler` / `AudioFifo`），从不用它编码
- **实测删不掉**：这两个 DLL 在 `avcodec` 的 load-time import 表里，
  移走后 `avcodec` 直接加载失败，语音识别整条链断掉
- 处置：保留并声明。详细分析与证据见 `../ffmpeg/SOURCE-OFFER.md` 第三节，
  许可全文见 `../x264/COPYING`、`../x265/COPYING`

### 2. `pyinstaller` —— 只在构建时用，不随包分发

`GPL-2.0-or-later WITH Bootloader-exception`（其 `COPYING.txt` 明确写了
SPDX 标识）。**Bootloader Exception** 给出「无限制地把编译好的 bootloader
链接或嵌入到其他程序、并分发这些组合，不受 GPL 限制」的许可 ——
这正是打包场景，所以打出来的 exe 不因 PyInstaller 而被要求开源。

PyInstaller 本体不进分发包（只有它生成的 bootloader 进），
`Ave.spec` 也没把它列进 `datas`。

---

## 随分发包一起交付的依赖

### 有 `dist-info` 的（`dist/Ave/_internal/*.dist-info`，12 个）

| 包 | 版本 | 许可 |
|---|---|---|
| attrs | 26.1.0 | MIT |
| av | 18.1.0 | BSD-3-Clause（⚠ 见上方第 1 条） |
| click | 8.4.2 | BSD-3-Clause |
| cryptography | 46.0.5 | Apache-2.0 OR BSD-3-Clause |
| ctranslate2 | 4.8.1 | MIT |
| itsdangerous | 2.2.0 | BSD |
| MarkupSafe | 3.0.2 | BSD |
| numpy | 2.4.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| pydantic | 2.12.5 | MIT |
| tqdm | 4.67.3 | MPL-2.0 AND MIT |
| websockets | 16.0 | BSD-3-Clause |
| werkzeug | 3.1.7 | BSD-3-Clause |

### 以模块形式打进包的

| 包 | 版本 | 许可 |
|---|---|---|
| faster-whisper | 1.2.1 | MIT |
| Pillow | 12.0.0 | MIT-CMU |
| onnxruntime | 1.28.0 | MIT |
| fastapi | 0.141.1 | MIT |
| uvicorn | 0.52.3 | BSD-3-Clause |
| starlette | 1.6.0 | BSD-3-Clause |
| huggingface-hub | 1.27.0 | Apache-2.0 |
| tokenizers | 0.23.1 | Apache-2.0 |
| requests | 2.32.5 | Apache-2.0 |
| urllib3 | 2.6.3 | MIT |
| certifi | 2026.2.25 | MPL-2.0 |
| charset-normalizer | 3.4.6 | MIT |
| idna | 3.11 | BSD-3-Clause |
| anyio | 4.12.1 | MIT |
| sniffio | 1.3.1 | MIT OR Apache-2.0 |
| h11 | 0.16.0 | MIT |
| httptools | 0.8.0 | MIT |
| watchfiles | 1.2.0 | MIT |
| PyYAML | 6.0.3 | MIT |
| python-dotenv | 1.2.2 | BSD-3-Clause |
| filelock | 3.20.0 | Unlicense |
| fsspec | 2025.12.0 | BSD-3-Clause |
| packaging | 26.0 | Apache-2.0 OR BSD-2-Clause |
| pydantic-core | 2.41.5 | MIT |
| annotated-types | 0.7.0 | MIT |
| typing-extensions | 4.15.0 | PSF-2.0 |
| protobuf | 7.34.1 | BSD-3-Clause |
| flatbuffers | 25.12.19 | Apache-2.0 |
| colorama | 0.4.6 | BSD |
| sympy / mpmath / networkx | — | BSD（onnxruntime 的传递依赖） |

### 运行时环境

- **CPython 3.11**（PSF License）—— PyInstaller 把解释器打进包
- **tkinter / Tcl-Tk**（BSD 风格）—— `--pick-dir` 的目录选择框用它，
  `_internal/_tk_data/license.terms` 已随包

### 已排除的

`Ave.spec` 的 `excludes` 排掉了 `torch` / `torchvision` / `torchaudio` /
`matplotlib` / `scipy` / `pandas` / `pytest` / `IPython` / `notebook` /
`tensorboard` / `transformers`。**不在分发包里，其许可与本项目无关。**
（排 torch 的直接原因是体积：不排实测 4.5G，torch 一个人占 4.2G。）

---

## 非 Python 的随包素材

| 素材 | 许可 | 位置 |
|---|---|---|
| ffmpeg.exe | GPLv3 or later | `../ffmpeg/` |
| libx264 / libx265 DLL | GPLv2 or later | `../x264/`、`../x265/` |
| 思源黑体 SC Bold | SIL OFL 1.1 | `../fonts/SIL-OFL-1.1.txt` |
| 新青年体 | ⚠️ 仅非商用 | `../fonts/新青年体-授权说明.md` |
| faster-whisper medium 模型 | MIT（Systran 转换自 OpenAI Whisper，MIT） | 不随包，首次运行下载到 `%LOCALAPPDATA%\Ave\models\` |
