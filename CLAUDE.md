# Ave — 分镜自动化混剪工具 · 顶层总纲

> 本文件是架构铁律与导航，内容稳定。**进度和待办看 `docs/进度与待办.md`**（唯一真相源）。
> `docs/ARCHITECTURE.md`（219 行）不必每次全读：**碰架构决策或踩到怪问题时**去看它的实测事实与踩坑清单。
> `docs/资源需求清单.md` 是给运营的交付清单。
> 同时遵守 `C:\Users\20739\.claude\CLAUDE.md` 的全局规则（MCP 路由、任务分流、交付门禁、省 token）。

## 这是什么项目

把分镜素材按排列组合混剪成多条竖版短视频，自动加字幕、配音、BGM，导出到桌面 `VEDIO抖音`。

**不接剪映**（2026-08-14 改版）—— 做独立工具，效果尽量对齐剪映。后续接入「羽刃」项目作为一个新功能模式。
素材是 Seedance 2.0 文生视频产出的 AI 视频，无真人口型要对，所以 TTS 可自由替换音频。

技术栈：Python 3.11 + FastAPI + Vue3 + TypeScript + ffmpeg + faster-whisper。

## 模块地图

| 模块 | 职责 | 端口 | 绝不允许 |
|---|---|---|---|
| `combo.py` | 分镜解析 + 排列组合抽样 | — | 任何 IO、ffmpeg 调用、网络请求 |
| `ave/config.py` | 配置与路径集中处，凭证填这里 | — | 业务逻辑 |
| `ave/asr.py` | 语音识别 + 缓存 + 幻觉闸门 | — | 删闸门、动 `SPEECH_RATIO` 阈值 |
| `ave/subtitle.py` | Pillow 渲字幕 PNG | — | 改用 ffmpeg drawtext |
| `ave/tts.py` | 配音合成 + 时长贴合 | — | 用慢放代替补静音 |
| `ave/render.py` | ffmpeg 拼接 / 叠字幕 / 混音 | — | `apad=whole_dur` |
| `ave/pipeline.py` | 主流程，CLI 与 HTTP 共用 | — | 绕过 `run()` 另写一套流程 |
| `ave/server.py` | 本地 HTTP 服务，只听 127.0.0.1 | 8756 | 对外监听；把路由加在 StaticFiles 挂载之后 |
| `frontend/` | Vue3 界面 | 5173 | 直接读本地文件路径（浏览器拿不到，须走后端） |

## 架构铁律（违反 = 改爆）

1. **批处理必须存 GBK**。`启动.bat` / `停止.bat` 存 UTF-8 会中文乱码、`if`/`goto` 流程断裂【实测】。
   改完转回去：`io.open(f,'w',encoding='gbk',newline='\r\n').write(s)`
2. **CLI 入口必须 reconfigure stdout/stderr 为 UTF-8**。Windows 控制台/管道是 GBK，
   print `⚠ ✓ ✗` 直接 `UnicodeEncodeError` 崩，全量跑不完【实测】。
3. **字幕走 Pillow 渲 PNG + ffmpeg overlay**，不用 `drawtext`。现方案已端到端验证，
   `subtitle.py` 处理好了中文折行与孤立标点合并，换过去要重做转义和字体加载且无收益。
4. **界面预览组合必须传 seed**。不传则每次重新随机，与已渲成品对不上；
   且钩子会假装正确（遍历顺序确定），只有卖点和结尾在漂【实测】。
5. **ASR 幻觉闸门不准删**。VAD 语音占比 <50% + 水印正则双闸。有效片段实测 ≥73%、废片 ≤23%。
   Whisper 对无人声音频会吐训练数据里的字幕组水印。
6. **模型 / ASR 缓存 / BGM 放用户数据目录，不进应用目录**。否则更新应用会冲掉 1.5G 模型。
7. **Whisper 必须喂 `initial_prompt` 领域词表**。不喂实测错：抹布→师妈不、镂空篮→楼空栏、悬空→玄空。
8. **`atempo` 只接受 0.5~100**，超出静默失败。配音比画面短时补静音，不准慢放（念稿会拖腔）。

## 改动分级

- **大**（碰 `combo.py` 抽样规则、`pipeline.run()` 签名、新增 HTTP 接口）→ 讨论方案 → 计划 → 实现 → `/qa` → 独立 review
- **中**（单模块内新增/改函数、前端新组件）→ 短计划 → 实现 → `/browse` 验证
- **轻**（改配置值、文案、补小测试）→ 直接做 + 定向验证

## 验证要求

- 改 Python：`python -m ave.pipeline --limit 2 --seed 7` 必须出片
- 改前端：`cd frontend && npx vue-tsc -b --noEmit` 必须过，再走 `/browse` 实跑
- **`/browse` 是唯一浏览器入口**，`headless=false` 跑通并截图存盘到 `.probe/`
- **验视频真在播不能只看截图**：探 `video.readyState`（应为 4）、`currentTime` 是否递增、
  seek 后网络层有无 `206`。截图只是留证，判断靠探针
- 没有验证证据不得声称完成。禁止虚构命令输出

## 素材命名规范

```
钩子-内容概括-N        卖点M-内容概括-N        结尾促单-内容概括-N
```

`M`=卖点顺序，`N`=变体号。**内容概括缺失时不归组**（每文件自成一组）——
没有它无从判断两文件是否同源，按不同素材处理更安全。当前 13 个钩子组 → 产出 39 条。

产量公式：**钩子组数 × `HOOK_USE_LIMIT`**。
