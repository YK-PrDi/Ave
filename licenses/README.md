# Ave 开源许可与第三方声明

Ave 随包分发了若干第三方组件。本目录汇总它们的许可条款与源码获取方式。
浏览器里的可读版本是同目录的 `index.html`。

## 一句话摘要

随包的 `ffmpeg.exe` 是 **GPLv3** 构建，另有两个 **GPLv2** 的编码器 DLL
（`libx264` / `libx265`，随 PyAV 而来、实测无法移除）。
对外分发这些二进制时，必须同时提供本目录内容，并履行源码提供义务 ——
见 `ffmpeg/SOURCE-OFFER.md`。其余依赖均为宽松许可。

## 目录

| 组件 | 许可 | 文件 |
|---|---|---|
| **ffmpeg** | GPL v3 or later | `ffmpeg/COPYING.GPLv3`<br>`ffmpeg/BUILD-INFO.txt`（版本 / SHA256 / configure 全文）<br>`ffmpeg/SOURCE-OFFER.md`（**源码获取说明**）<br>`ffmpeg/checksums.sha256`（上游校验和） |
| **x264** | GPL v2 or later | `x264/COPYING` |
| **x265** | GPL v2 or later | `x265/COPYING` |
| FFmpeg 共享库（PyAV 自带） | LGPL v3 or later（自报） | `ffmpeg/COPYING.LGPLv3` |
| **阿里巴巴普惠体 3.0**（默认） | 免费商用，无需授权 | `fonts/阿里巴巴普惠体-授权说明.md` |
| **思源黑体 SC Bold**（回落） | SIL OFL 1.1 | `fonts/SIL-OFL-1.1.txt` |
| **新青年体** | ⚠️ **仅非商用** | `fonts/新青年体-授权说明.md` |
| Python 依赖（约 40 项） | MIT / BSD / Apache / MPL 等 | `third-party/PYTHON-DEPS.md` |

## 对外分发前必做

1. 读 `ffmpeg/SOURCE-OFFER.md`，把里面的 `<待填>` 全部补上
   （源码归档 URL、SHA256、联系方式）。**没补完等于没履行义务**
2. 确认 `licenses/` 整个目录随分发包一起交付
3. 确认字幕字体的选择符合使用场景 —— 见 `fonts/新青年体-授权说明.md`

`python 准备素材.py --check` 会检查第 1 条的占位符是否还在。

## 关于 Ave 自身

Ave 通过 `subprocess` 调用独立的 `ffmpeg.exe` 进程完成转码，
不静态链接 GPL 代码。但 PyAV 的 GPL 编码器 DLL 会加载进 Ave 进程 ——
这两者在传染性上的处境不同，机制与实测证据见
`ffmpeg/SOURCE-OFFER.md` 第三节。本目录只陈述事实，不构成法律意见。
