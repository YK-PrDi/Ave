# 源码获取说明（Written Offer for Source Code）

Ave 随包分发的 `ffmpeg.exe` 是一份 **GPL version 3 or later** 构建
（二进制自报，见 `BUILD-INFO.txt` 里 `ffmpeg -L` 原文）。
它启用了 `libx264` 与 `libx265`，二者自身为 **GPLv2 or later**。

GPL 要求：向他人交付二进制副本时，必须同时提供或书面承诺提供
**对应源码（Corresponding Source）**。本文件就是那份承诺。

---

## 一、精确的版本标识

拿源码之前先对上版本 —— 给错版本的源码不算履行义务。

| 项 | 值 |
|---|---|
| ffmpeg 版本 | `n8.1.2-44-g7c533d0f86-20260815` |
| FFmpeg 上游 commit | `7c533d0f86f13a06ec93968f6194349665b3536a` |
| 构建者 | BtbN/FFmpeg-Builds（GitHub Actions） |
| Release tag | `autobuild-2026-08-15-13-02` |
| 二进制资产 | `ffmpeg-n8.1.2-44-g7c533d0f86-win64-gpl-8.1.zip` |
| 资产 SHA256 | `0e7829b6e1ba867e37bbad17153de258bd3bffaa3b745626a6424df0ea113970` |
| 随包 `ffmpeg.exe` SHA256 | `5d5e06fbb900fd7a45a82eb0529e67f905853432139f673ac90aff45930504d8` |

`configure` 全文见 `BUILD-INFO.txt`。复现构建需要它 ——
Corresponding Source 包含「控制编译与安装的脚本」，不只是 ffmpeg 本体源码。

> ⚠️ **不要引用 BtbN 的 `latest` tag。** 那个 tag 是滚动的：实测同名资产
> `ffmpeg-n8.1-latest-win64-gpl-8.1.zip` 会被原地重新上传
> （release `published_at` 与资产 `updated_at` 同在 2026-08-15T13:26 一线）。
> 过段时间从 `latest` 下回来的已经不是我们分发的这一份，
> 那样等于没提供对应源码。上表那个 `autobuild-` tag 是钉死的。

---

## 二、怎么拿到源码

### 方式 A：我们的归档 —— GitHub Releases（与分发的二进制一一对应）

**归档位置已定（2026-08-16）：本项目的 GitHub Releases**
`https://github.com/YK-PrDi/Ave/releases`

在发布 exe 的那个 release 里一并上传下面两个资产：

| 内容 | 资产名 | SHA256 |
|---|---|---|
| FFmpeg 源码 | `ffmpeg-src-7c533d0f86.tar.gz` | `6439e4277bccdb3224a64db06f0dd39b5272d8a1aab9b1a6a80c794e44e21860` |
| 构建脚本快照（BtbN/FFmpeg-Builds） | `ffmpeg-builds-snapshot.tar.gz` | `3d59554604274dd229806133b0b67e9936687ac420975742f8a0da4e46140223` |
| 上游 `checksums.sha256` | 本目录已存副本 | — |

索取源码：在 `https://github.com/YK-PrDi/Ave/issues` 开 issue，
或联系仓库所有者。本承诺自交付副本之日起 **至少三年内有效**。

**两份归档已于 2026-08-27 上传到 release `v0.1.0`**
（`https://github.com/YK-PrDi/Ave/releases/tag/v0.1.0`）：16.9MB + 102KB。
本机 `dist-src/` 仍留副本（不进版本库）。

**SHA256 已验证到端**：匿名下载回 release 上的两个资产，哈希与上表一致、
且与本机 `dist-src/` 逐字节相同（`cmp` 通过）。
⚠ 但**别用本地 `tar czf` 重新打包** —— gzip 会把时间戳写进字节流，
同一份源码打两次哈希不同，那样上表就对不上了。

> ⚠️ **下载大文件会被截断**【实测 2026-08-27】：头一次 `curl` 拿
> `ffmpeg-src` 只收到 16,706,432 字节（少 195,495），哈希自然对不上。
> **别据此判断上传坏了** —— 加 `--retry 5 --retry-all-errors -C -`
> 续传补齐后哈希完全正确。校验前先比字节数。

**GPL 义务已履行**（自 2026-08-27 起至少三年）：别删这两个资产、
别把 release 改成 draft 或撤下。

**为什么选 GitHub Releases**：源码 zip 不该进 git 仓库本体（几十 MB 且每次
更新存全量），但 Releases 的资产不占仓库历史，又和 exe 放在同一个地方 ——
拿二进制的人顺手就能看到源码，不用另找。

### 方式 B：上游直接拿（我们无法保证长期可用，仅作补充）

```bash
# FFmpeg 源码，按 commit 精确取
curl -L -o ffmpeg-src.tar.gz \
  https://github.com/FFmpeg/FFmpeg/archive/7c533d0f86f13a06ec93968f6194349665b3536a.tar.gz

# 构建脚本
git clone https://github.com/BtbN/FFmpeg-Builds.git

# 二进制与校验和（钉死的 tag）
curl -L -O https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-08-15-13-02/checksums.sha256
```

x264 / x265 源码：

```bash
git clone https://code.videolan.org/videolan/x264.git
git clone https://bitbucket.org/multicoreware/x265_git.git
```

上游第三方仓库随时可能变动或下线，所以**方式 A 才是我们的正式承诺**。

---

## 三、还有一处 GPL 代码：`av.libs` 里的 x264/x265

**这一条容易被漏掉，因为我们从没主动要过它。**

`_internal/av.libs/` 下有：

```
libx264-165-f3a909470ddc2d85ed21eda3d0fb7954.dll
libx265-efe48a158520a59ef99c0a0b3eb835ae.dll
```

来路：`faster-whisper` → `av`（PyAV 18.1.0）的预编译 wheel 自带。
PyAV 只用来解码音频（`faster_whisper/audio.py` 第 15 行 `import av`），
我们从不用它编 H.264 —— 编码走独立的 `ffmpeg.exe` 进程。

### 实测结论：删不掉，只能保留并声明

试过把这两个 DLL 移走，`avcodec` **直接加载失败**：

```
Could not find module 'avcodec-62-....dll' (or one of its dependencies)
```

解析 `avcodec` 的 PE 导入表确认原因：这两个 DLL 在 **load-time import
（`.idata`）** 里，不是 delay-load，19 个导入项里就有它们。
所以 `avcodec` 起不来 → PyAV 起不来 → 语音识别整条链断掉。
把它们放回去立刻恢复正常（对照实验已做）。

结论：**保留，并在许可清单里如实列出。** 已放 `../x264/COPYING`
与 `../x265/COPYING`（均为 GPLv2 全文）。

### 与 `ffmpeg.exe` 的性质差别

- `ffmpeg.exe` —— 我们用 `subprocess.run()` 起的**独立进程**
  （`ave/render.py`、`ave/asr.py`），隔着进程边界调用
- `av.libs/*.dll` —— **加载进 Ave 自己的进程**，同一地址空间

这两者在 GPL 传染性上的处境不同。我不是律师，此处不给法律结论，
只把机制和实测事实写清楚。若要彻底移除进程内的 GPL 代码，
唯一的路是**自行编译一份不带 x264/x265 的 PyAV**（或换掉音频解码依赖）——
当前未做，因为要维护一份 PyAV 构建，成本远高于收益。

`avcodec` 自报 `LGPL version 3 or later`（`avcodec_license()` 实测），
但它的 configure 里带 `--enable-libx264 --enable-libx265`，
而这两个在 FFmpeg 的 `EXTERNAL_LIBRARY_GPL_LIST` 里是 GPL-only 库。
自报值与实际链接内容不一致，**按 x264/x265 的 GPLv2 走是安全假设**。

---

## 四、归档怎么做（给要对外分发的人）

**归档位置已定（2026-08-16 用户决定）：GitHub Releases。**

**三步都已做完（第 1、2 步 2026-08-17，第 3 步 2026-08-27）**：
两份归档在本机 `dist-src/`，SHA256 已填进第二节，
并已上传到 release `v0.1.0`。当时用的命令：

```bash
# 3. 连同 exe 一起传到发布 release（gh CLI）
cd dist-src
gh release upload <tag> ffmpeg-src-7c533d0f86.tar.gz ffmpeg-builds-snapshot.tar.gz
```

⚠ `gh` 的 device-code 登录端点（`github.com/login/device/code`）在本机连不上
【实测 2026-08-27，`api.github.com` 与 `github.com` 都通，只有它超时】。
备选：`gh auth login --with-token`，或直接在网页
`releases/new` 手工建、拖文件上传（本次走的这条）。

⚠ **传的必须是 `dist-src/` 里那两个文件**，别重新下载 —— 第二节的哈希是
按它们算的。若归档丢了要重建，用下面的命令（**不是 `git clone` + `tar czf`**，
后者的 gzip 时间戳会让哈希对不上）：

```bash
# FFmpeg 源码：codeload 直下，字节确定性已实测
curl -L -o ffmpeg-src-7c533d0f86.tar.gz \
  https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/7c533d0f86f13a06ec93968f6194349665b3536a

# 构建脚本：按钉死的 commit 直下，不是 clone master
curl -L -o ffmpeg-builds-snapshot.tar.gz \
  https://codeload.github.com/BtbN/FFmpeg-Builds/tar.gz/590a6612d7d961e9258429e501619e0b7d7cbedf

sha256sum ffmpeg-src-7c533d0f86.tar.gz ffmpeg-builds-snapshot.tar.gz  # 应与第二节一致
```

**⚠ 构建脚本必须钉 commit，`clone master` 是错的。** release 的
`target_commitish` 只写着 `master`，拿不到精确 commit。
`590a6612d7d961e9258429e501619e0b7d7cbedf` 是这么定的：它的 committer 时间
`2026-08-13T12:17:18Z` 与该 release 的 `created_at` **完全一致**，
即构建时的 master HEAD。这是依据时间戳的推定，不是 API 直接给的授权答案 ——
但比 clone 今天的 master 准确得多（master 一直在往前走）。

要求：接收方拿到二进制后**三年内**都能下到 —— 所以别删这些资产，
也别把 release 改成 draft 或 pre-release 后又撤下。

**只发给公司内部同事时**：同一法人内部流转一般不构成 GPL 意义上的
「向他人交付」（conveying），此时可以只做归档留底、暂不对外承诺。
但 `licenses/` 目录本身建议一直随包带 —— 成本为零，
而分发范围一旦扩大就不用返工。

---

## 五、本目录文件清单

| 文件 | 内容 |
|---|---|
| `COPYING.GPLv3` | GPLv3 全文，取自 FFmpeg `n8.1` tag |
| `COPYING.LGPLv3` | LGPLv3 全文（`av.libs` 里的 av* DLL 自报此许可） |
| `BUILD-INFO.txt` | 版本、SHA256、`ffmpeg -L` 原文、`configure` 全文。由 `准备素材.py` 生成 |
| `checksums.sha256` | 上游 release 的校验和，可核对我们的二进制来源 |
| `SOURCE-OFFER.md` | 本文件 |
