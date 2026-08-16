# Ave · 分镜自动化混剪工具

把分镜素材按排列组合混剪成多条竖版短视频，自动加字幕、配音、BGM，
导出到桌面 `VEDIO抖音` 文件夹。

后续接入「羽刃」项目作为一个新功能模式；前端计划用 Vue3。

## 快速开始

**双击 `启动.bat`** —— 自动装依赖、下模型、起服务、开浏览器。
首次运行要装依赖和下模型（约 5-10 分钟），之后每次几秒就好。
用完双击 `停止.bat`。

需要预装 [Python 3.10+](https://www.python.org/downloads/)（装时勾选
"Add Python to PATH"）和 [Node.js LTS](https://nodejs.org/)。

### 命令行方式

不想用界面就直接跑：

```bash
pip install -r requirements.txt
python 下载模型.py                        # 下载语音识别模型

python -m ave.pipeline --dry-run          # 只看组合方案，不渲染
python -m ave.pipeline --limit 2 --seed 7 # 跑 2 条验证
python -m ave.pipeline                    # 全量
```

### 界面单独启动

```bash
python -m ave.server                      # 后端，8756
cd frontend && npm run dev                # 界面，5173
```

## 工作流程

```
扫描分镜 → 排列组合 → 语音识别 → TTS 配音 → 渲染 → 导出桌面
```

1. **扫描**：按文件名解析角色（钩子 / 卖点 / 结尾促单）
2. **组合**：每条 = 1 钩子 + N 个卖点（默认 5）+ 1 结尾，
   每个钩子用满 3 次即换下一个
3. **识别**：faster-whisper 识别口播，结果按源片段缓存（55 个片段只识别一次）
4. **配音**：TTS 重新生成，并调语速贴合画面时长
5. **渲染**：ffmpeg 拼接 + 字幕 PNG 叠加 + BGM 混音
6. **导出**：落到桌面 `VEDIO抖音`（不存在自动创建）

## 模块

| 文件 | 作用 |
|---|---|
| `combo.py` | 分镜解析 + 排列组合抽样 |
| `ave/config.py` | 配置集中处，凭证填这里 |
| `ave/asr.py` | 语音识别 + 缓存 + 幻觉闸门 |
| `ave/subtitle.py` | Pillow 渲染字幕 PNG |
| `ave/tts.py` | 配音合成 + 时长贴合 |
| `ave/render.py` | ffmpeg 拼接 / 叠字幕 / 混音 |
| `ave/pipeline.py` | 主流程，命令行与 HTTP 共用 |
| `ave/server.py` | FastAPI 本地服务（127.0.0.1:8756）|
| `frontend/` | Vue3 + TypeScript 界面 |
| `启动.bat` / `停止.bat` | 一键起停（GBK 编码，见下方注意）|
| `下载模型.py` | 下载语音识别模型，走国内镜像、支持续传 |

### 给 Java 项目调用

后端是 HTTP 接口，Java 侧不用碰 Python：

| 接口 | 作用 |
|---|---|
| `GET /api/health` | 环境自检 |
| `POST /api/scan` | 扫素材，返回盘点与预计产量 |
| `POST /api/preview` | 预览组合方案 |
| `POST /api/jobs` | 提交渲染任务，返回 job_id |
| `GET /api/jobs/{id}/events` | SSE 实时进度 |
| `POST /api/jobs/{id}/stop` | 停止任务 |

用 `java.net.http.HttpClient` 调即可，SSE 用 `ofLines()` 逐行读。

### 注意：批处理必须存 GBK

`启动.bat` / `停止.bat` 存的是 **GBK**，不是 UTF-8。
中文 Windows 的 cmd 按系统默认编码读批处理文件，
存成 UTF-8 会导致中文乱码、`if`/`goto` 流程被打断（实测踩过）。
改这两个文件后要转回 GBK：

```python
import io
s = io.open('启动.bat', encoding='utf-8').read()
io.open('启动.bat', 'w', encoding='gbk', newline='\r\n').write(s)
```

## 素材命名规范

```
钩子-内容概括-N
卖点M-内容概括-N
结尾促单-内容概括-N
```

- `M` = 卖点顺序（脚本里第几个展示的内容）
- `N` = 变体编号（同一内容生成了多个时用来区分）
- `内容概括` = 这个分镜讲什么（沥水 / 收纳 / 颜值……）

**内容概括不能省** —— 缺了就无法判断两个文件是「同一素材的变体」
还是「两个不同素材」，只能按不同素材处理。

## 模型

语音识别模型不进版本库（1.5G）。下载到 `models/fw_medium/`：

```python
import urllib.request, os
base = 'https://hf-mirror.com/Systran/faster-whisper-medium/resolve/main/'
os.makedirs('models/fw_medium', exist_ok=True)
for f in ['config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt']:
    urllib.request.urlretrieve(base + f, f'models/fw_medium/{f}')
```

`medium` 比 `small` 明显准（专业词：抹布 / 悬空 / 镂空篮 / 高低杆），
代价是 1.5G vs 484M。嫌大可换 `Systran/faster-whisper-small` 并改
`config.MODEL_DIR`。

## 配置

改 `ave/config.py`：

| 项 | 说明 |
|---|---|
| `SOURCE_DIR` | 分镜素材根目录 |
| `POINT_COUNT` | 每条用几个卖点（默认 5）|
| `HOOK_USE_LIMIT` | 每个钩子用几次（默认 3）—— **决定产量** |
| `SUBTITLE_SIZE` | 字号刻度（需求要求 10-15）|
| `TTS_BACKEND` | `stub`（静音占位）/ `volcano`（火山引擎）|
| `BGM_DIR` | BGM 目录，随机挑一首 |

**产量 = 钩子数 × `HOOK_USE_LIMIT`**。当前素材 13 个钩子 → 39 条。

## 换机器怎么准备

`git clone` 下来跑不了打包 —— `ffmpeg.exe`（144MB）和 `fonts/` 不进版本库
（体积大、各有授权，见 `.gitignore` 里的说明）。一条命令补齐：

```bash
python 准备素材.py            # 检查并下载缺的（首次约 250MiB，本机实测约 4MB/min）
python 准备素材.py --check    # 只看缺什么，不下载
python 准备素材.py --force    # 校验不过时重下
```

**⚠ 这只影响「重新打包」。** 给最终用户的 exe 分发包里 ffmpeg 和字体
都已经打进去了（见 `Ave.spec` 的 `datas`），用户不需要准备任何东西。

新青年体只能从装了剪映的机器上拷，脚本下不到 —— 缺了不影响出片，
默认字幕字体是思源黑体。

## 开源许可

随包的 `ffmpeg.exe` 是 **GPLv3** 构建，另有两个 **GPLv2** 的编码器 DLL
（`libx264` / `libx265`，随 PyAV 而来，实测无法移除）。
许可全文、源码获取说明、依赖清单都在 **`licenses/`**，界面页脚也有入口。

**对外分发前必须补齐 `licenses/ffmpeg/SOURCE-OFFER.md` 里的 `<待填>`**
（源码归档地址）。写文档不等于履行义务，得真有个能下载到东西的地方。
`python 准备素材.py --check` 会提醒占位符还在。

字幕默认用思源黑体（SIL OFL，可商用）。新青年体内部名带
`(Non-Commercial Use)`，带货是商用场景 —— 详见
`licenses/fonts/新青年体-授权说明.md`。

## 待补资源

见 `docs/资源需求清单.md`：

1. 火山引擎语音合成凭证 + 音色 ID —— 没有它配音是静音
2. 轻快 BGM 文件夹 —— 没有它成品无背景音乐

## 设计与踩坑记录

见 `docs/ARCHITECTURE.md`。包含已验证的环境事实、ffmpeg 能力边界、
ASR 幻觉闸门、以及一批实测踩过的坑。
