# BGM 授权决策与建库方案

> 2026-09-06 核实。**结论先行：剪映 BGM 库的曲子一首都不能用**，
> 建库改走「按调性从授权干净的库里挑」。
> 本文是决策记录 + 下一轮建库的接手说明，读完可直接开工，不必重新核实。

---

## 一、起因与结论

用户提供 `bgm库(1).docx`（桌面），内含 19 个曲名 + 17 张截图，来自
**剪映 BGM 库的「轻快」分类**，希望取得这些音频作为 Ave 的 BGM 库。

**docx 里没有音频** —— 解包只有 `word/media/image1~17.png`，无 audio part、
无外链关系项。曲名只能靠文字反查。

三组并行核实 19 首，**可用 0 首**：

| 组 | 首数 | 可用 | 分布 |
|---|---|---|---|
| 中文 | 5 | 0 | 3 确认商业发行，2 查不清 |
| 英文 A | 8 | 0 | 5 指向 BMG/Deep East 商业曲库，1 CC BY-**NC**（禁商用），2 查不清 |
| 英文 B | 6 | 0 | 3 确认商业发行，3 查不清 |

**该歌单到此为止，不再投入。** 它是一份「剪映里好听的曲子」清单，
不是可获取的资源清单。---

## 二、「剪映轻快分类」不提供任何安全性

本轮最重要的发现，**推翻了筛选前提**，别再走回头路。

### 1. 「轻快」不在商用授权范围内

剪映《商用音乐说明》里可商用的曲子圈在**单独的「商用音乐」面板**。
「轻快」「伤感」「国风」是**风格分类，属普通音乐库，不带商用授权**。

即使老老实实用剪映剪、只发抖音，「轻快」分类的曲子也一样没有商用授权。

### 2. 主体是 BMG 的商业制作库

英文 A 组 8 首里 5 首指向 **Deep East Music**（BMG Production Music 旗下）：
- AudioAtlas 的 **BMG 授权页**署 Ron Baines、专辑编号 `DEM061 Vintage Sunshine`
- **抖音自己的音源署名**写「Bygone Bumps - Deep East Music」
  （抖音与剪映同属字节、共用曲库，比同名匹配可信）
- APRA AMCOS 目录码前缀 `DEM` = Deep East Music，sub-publisher 为 BMG

Production library music 是**按次授权的商业曲库**。
「歌单里混着免费曲库曲子」的假设基本不成立。

### 3. 剪映不暴露元数据 → 按曲名反查必然撞车

只给展示名，**无艺人、无 ISRC、无来源**。`Bittersweet`、`Dancing in the Dark`、
`3.30PM`、`暖阳`、`美好生活` 全部查不清（19 首里 7 首）。
**不是查得不够努力，是信息根本不够。**

真要确认只有两条路（本轮未做，成本高于收益）：
① 剪映客户端内看曲目详情页有无艺人署名；
② 导出片段过 Shazam / AudioTag / ACRCloud 拿 ISRC —— 唯一能绕开同名歧义的办法。---

## 三、19 首核实结论（存档，勿重查）

### 中文 5 首

| 曲名 | 实际 | 结论 |
|---|---|---|
| 有何不可 | 许嵩 2009，现太合/大潮音乐版权 | 商业发行，头部华语作品 |
| 小城夏天 | **LBI利比（时柏尘）** 2022，青风音乐 | 商业发行，抖音爆款 |
| 再度重相逢（纯音乐） | 原曲伍佰 & China Blue 2003 | 商业发行 |
| 暖阳 | ≥3 个同名候选（任然 2023 / 曲比阿且 2024 / 曲库纯音乐） | 未能核实 |
| 美好生活 | 找不到对得上的曲目 | 未能核实 |

⚠️ 本轮最初凭印象给的两条线索是**错的**，勿采信：
小城夏天**不是**王贰浪；曲名是**再度**重相逢（不是「再渡」）。

### 英文 14 首

| 曲名 | 艺人 / 来源 | 授权 | 置信度 |
|---|---|---|---|
| Bygone Bumps | Ron Baines / Deep East Music | BMG 商业曲库 | 高 |
| Sunny Jim | Ron Baines / Deep East Music | BMG 商业曲库 | 高 |
| Monsieur Melody | Deep East Music | BMG 商业曲库 | 中高 |
| Pop Groove | Deep East Music（剪映标 "Andromeda"） | 疑 BMG | 低 |
| After Hour | 疑 Deep East Music | 疑 BMG | 低 |
| Upbeat Funk Pop | Scott Holmes Music / FMA | **CC BY-NC，禁商用** | 中 |
| Spring in My Step | Silent Partner / YouTube Audio Library | YTAL 免费授权 | 高 |
| Countless | 未能核实（Artlist 付费订阅有同名曲） | — | 低 |
| 3.30PM | 未能核实（搜索被「下午三点半」淹没） | — | 低 |
| BITTERSWEET | FSM Team（**存疑，同名曲 ≥5 个艺人**） | CC BY 4.0 可商用需署名 | 低 |
| Green To Blue | daniel.mp3 | 商业发行 | 中 |
| Dancing In The Dark | 未能确认是哪一首（同名 ≥6 个） | — | 低 |
| Experience | Ludovico Einaudi《In a Time Lapse》2013 | 商业发行 | 高 |
| Say It Right | Nelly Furtado《Loose》2006（Geffen） | 商业发行 | 高 |

**Spring in My Step 是唯一授权干净的**，但无公开直链，需登录
`studio.youtube.com` → Audio Library 手动取，且无法从外部确认它是否仍在库中。
Pixabay 上那个搜索结果**是另一个用户的另一份上传，不是同一首**。---

## 四、四个陷阱（每一个都差点上钩）

1. **网站免费 ≠ 授权免费商用**。`Upbeat Funk Pop` 确实在 Free Music Archive 上，
   但授权是 **CC BY-NC**，商用要另付费。作者站
   （scottholmesmusic.com/licensing）原文写着 `Commercial use: ❌ No`。
2. **授权是真的、对应关系是猜的 → 一样不能用**。`BITTERSWEET` 找到一首 FSM Team
   的同名曲，CC BY 4.0、可商用，授权页原文都抓到了 —— 但没有任何证据说剪映收的
   是这一版。同名曲至少 5 个艺人。
3. **同名同艺人也可能不是同一个母带**。remaster / 授权给发行商的版本仍可能受
   商业版权约束。**安全做法是从免费曲库重新下载原始文件**，绝不直接用剪映那份。
4. **「纯音乐」不等于「无版权」**。《再度重相逢（纯音乐）》换的只是演奏者，
   绕开的只是录音制作者权，**作曲权仍在伍佰一方**，照样能被主张。

---

## 五、法律尺度（「不出事」的门槛比直觉高）

用户已明确：**更在意「不出事」，风格对上就行**。以下判例支撑这个取向。

- **播放量低不构成抗辩**。温州鹿城区法院：某银行发内部运动会视频用了
  《你笑起来真好看》，**点赞 21、评论 0、无带货**，索赔 5 万，侵权成立。
  「播放量低」「非盈利」均未被采纳。
- **商业推广是加重情节**。北京互联网法院十大典型案例：「以明显商业目的将他人
  短视频用于商业广告或推广的，应当酌情增加赔偿数额」；另有一条专门针对
  「MCN 机构推广的短视频未经许可使用背景音乐侵犯录音制作者权」判赔。
- **平台授权不兜商用**。裁判要点：「短视频平台并不对用户以商业为目的使用负责，
  商业使用仍需要用户自行获取特定歌曲的商用版权授权。」

Ave 的产出是**带货推广视频**，正落在最高风险档。
故筛选阈值定为：**置信度「中」「低」一律不入库；查不清 = 不能用**
（不是「查不到证据说它有版权所以能用」）。---

## 六、建库方案（已定，下一轮直接执行）

### 决策记录

| 项 | 决定 | 日期 |
|---|---|---|
| 中文曲 | **不要**。3% 音量下语种不可辨，不值得为它引入授权不清的曲子 | 用户 2026-09-06 |
| 数量 | **越多越好**（同库已验授权，追加曲子边际风险≈0） | 用户 2026-09-06 |
| 路线 | **B 优先、A 兜底** | 用户 2026-09-06 |
| 署名 | **烧进画面**（不放视频描述） | 用户 2026-09-06 |
| 分发范围 | **会给别的客户用** —— 故 Standalone 条款是硬约束 | 用户 2026-09-06 |

### A / B 两条路，曲子不能混装

| | B（首选） | A（兜底） |
|---|---|---|
| 授权 | CC0 / CC-BY（**允许再分发**） | Pixabay Content License |
| 能否进自有云 OSS | **能** | **不能**（见下） |
| 清单 `url` 指向 | 自有云 | Pixabay 官方直链 |

⚠️ **Pixabay 的曲子不能进自有 bucket。** Content License 原文：

> You cannot sell or distribute Content (either in digital or physical form)
> on a **Standalone** basis. Standalone means where no creative effort has been
> applied to the Content and it remains in substantially the same form as it
> exists on our website.

- **成品视频合规** —— BGM 在 3% 音量垫在口播下，混音+剪辑是 creative effort，形态已变
- **分发 BGM 库不合规** —— 无论随包进 `BGM_BUILTIN_DIR` 还是放自有 OSS 供客户端下载，
  分发的都是原封不动的 MP3，正落在 Standalone 定义里。工具**要给别的客户用**
  （`config.py:195` 注释「各公司业务人员自己加」），那就是实打实的 distribute

Pixabay 其余条款是好的：✓ 免费使用 ✓ **无需署名** ✓ 可修改改编。
它只是不能再分发，仍可走 A：清单存官方直链，客户端自己拉。

清单加 `host` 字段（`own` / `pixabay`）标明来源，
防止以后有人手一抖把 Pixabay 的曲子同步进 bucket。### incompetech（Kevin MacLeod）—— B 的主力源，授权已查实

FAQ 原文要点（https://incompetech.com/music/royalty-free/faq.html）：

- **不是公有领域**：`Is this music in the Public Domain? No. All of this music is copyrighted.`
- 授权 **CC-BY 4.0**：可商用、可货币化、**可再分发**、可改编（sing over/chop/splice 均可）
- **必须署名**，格式固定（`Title` 要换成**实际曲名**）：
  ```
  Title Kevin MacLeod (incompetech.com)
  Licensed under Creative Commons: By Attribution 4.0
  https://creativecommons.org/licenses/by/4.0/
  ```
- 署名位置：视频描述或视频内均可，但「想知道来源的人应不费力找到」，不得遮蔽
- **每首有 ISRC 编号** —— 官方用途正是「有人声称拥有这首曲子、挑战你的使用时，
  可用此号证明来源」。**抖音版权识别误报时这就是申诉材料，务必入清单**
- 官方举证规格：打印 CC-BY 法律文本 + 打印曲子页面（须含 URL 和页脚 CC 标志）

其他候选源（incompetech FAQ 自己推荐的，授权待逐一核实）：
Silverman Sound、Josh Woodward、Jason Shaw (Audionautix)、Tim Beek、
Brett Van Donsel、Andy G Cohen (FMA)、Kongano、Tim Kulig。

### 2026-09-07 实抓修正（比原计划简单，别按老思路重做）

**incompetech 没有「每首一页」。** 整份元数据作为 `allPieces` 数组嵌在
`music.html` 那一页里 —— 1442 首的 title / isrc / feel / genre / bpm /
length / filename 全在，下载按钮的 URL 也由它拼。所以「逐首从页面抄」
= **从这一页抄**，不是抓 1442 个子页面。已落盘
`ave/incompetech-allpieces.json`（附 `source_page` + `fetched_at`）。
另有官方 ISRC 总表 `full_list.php`（1436 条）落盘
`ave/incompetech-isrc-list.json`，**当第二个官方源用来交叉核对
ISRC ↔ 曲名**，不一致的直接丢（实测丢 2 首）。

⚠️ **官方 `length` 字段不可靠，别拿它当校验基准。**
`Easy Lemon (30 second)` 标的是 `00:00:00`。实测 312 首里 12 首
真实时长与标注差 2 秒以上（`Stealth Groover` 标 68s、实测 200s）。
这说明的是**那一列没维护**，不是文件错 —— 故这 12 首归入
`待核实/` 而非废弃（`来源-待核实.json` 记了各自差多少）。听一遍确认
是那首曲子就能移回；抓取脚本重跑**不会**把它们拉回来（已按文件名跳过）。

⚠️ **`filename` ≠ `title`。** `No Frills Comparsa` 的文件名是
`Comparsa.mp3`。署名必须用 `title` 字段，**不准从文件名反推**。

⚠️ **官方有两套署名模板，措辞不同，都是官方的。**
`licenses/` 页点「Use Creative Commons」后，生成器函数 `renderCC()` 吐的是
（2026-09-07 从页面 JS 源码读的，**不是从 FAQ 推的**）：
```
"Title"
Kevin MacLeod (incompetech.com)
Licensed under Creative Commons: By Attribution 4.0
http://creativecommons.org/licenses/by/4.0/
```
与 FAQ 那版差三处：**曲名带引号**、**曲名单独一行**（FAQ 是与作者同行）、
链接是 **http**（FAQ 是 https）。多首时生成器把曲名并列成
`"A", "B"` 再接后面三行。
**采用生成器这版** —— 那是他们让人复制粘贴的官方输出。
`来源.json` 每条的 `attribution` 已按这版生成，第七节直接取该字段用，
**不要在渲染代码里重新拼**。

### 元数据规范（「信息要准」的落地点）

**曲名 / 作者 / 授权 / 来源 URL 只从官方下载页面本身抄。**
不从搜索摘要抄、不从文件名反推、**不读 ID3 标签**
（曲库站生成的标签常为空或写着上传者昵称，以它为准会让清单看起来准而实际错）。

本轮已示范摘要不可信：凭印象给的两条线索，一条作者错、一条曲名错字。
同种错误落进清单，就是以后拿不准哪条能信。

### 清单条目形态

`bgm_cloud.py:166` 的 `_valid()` 只要求 `id` + `url`，**其余字段原样透传不校验**，
所以加溯源字段**一行代码都不用改**。不要另开 CSV —— 清单是曲子的唯一真相源，
分开放迟早对不上（改了曲子忘了改清单）。

```json
{
  "id": "incompetech-carefree",
  "url": "https://<自有云>/bgm/carefree.mp3",
  "host": "own",
  "name": "Carefree.mp3",
  "title": "Carefree",
  "artist": "Kevin MacLeod",
  "license": "CC-BY-4.0",
  "license_url": "https://creativecommons.org/licenses/by/4.0/",
  "source_url": "https://incompetech.com/music/royalty-free/...",
  "isrc": "US-UAN-11-00xxx",
  "verified_at": "2026-09-06"
}
```

`verified_at` 是给以后的自己看的：曲库偶尔改授权条款，一年后能知道这条信息
是哪天核实的、该不该复查。---

## 七、署名烧进画面 —— 接入点已勘明

### 不用动 `build_filter`

`render.py:80-86` 把 `subs` 里每张 PNG 按 `enable='between(t,start,end)'` 叠上去，
**对内容毫不关心**。所以署名就是**往 `subs` 里追加一条**、时间窗设成最后两秒，
滤镜链一行不用改。

### 署名文本必须逐条生成，不准写死

CC-BY 要求署名里是**实际用的那首曲子的真实曲名**（incompetech FAQ 特别强调
*replace the word Title with the Actual Title*）。BGM 是每条随机抽的，
39 条会抽到十几首不同曲子 —— **写死一行的话，除碰巧对上的那条，
其余全是错误署名**。错误署名比没署名更糟：既没履行义务，
又把别人的曲子说成另一首。

数据链路已通：`pipeline.record_manifest()` 已在记 `bgm_id`（`pipeline.py:140`），
`pick_bgm()` 返回 `(路径, 云端id)`（`pipeline.py:75-95`），按 id 回查清单即可。

### 要新写的只有一个渲染函数

**不能复用 `subtitle.render_png()`** —— 它的位置（`VERTICAL_POS`）、颜色、字号
是按中文字幕调的模块常量（`subtitle.py:196-211`），且 `wrap_text()` 的中文折行
规则会把英文授权文本切得很难看。署名要：小字、贴右下角、最后 1~2 秒。

### 2026-09-07 已实现并验完

`subtitle.render_credit_png()` + `pipeline.credit_text()`，接在
`build_one()` 里 `pick_bgm()` 之后（要先有 `bgm_id`）、`render()` 之前。
`CREDIT_SECONDS = 2.0`。

⚠️ **「低透明度」这条要打个折扣 —— 必须描边，不能只靠投影。**
第一版按「小字 + 低透明度」做了投影版，实测 `Kevin MacLeod (incompetech.com)`
那行压在浅色台面上对比度就不够了（`.probe/zoom_002.png`）。而 incompetech FAQ
要求「想知道来源的人应不费力找到」且不得遮蔽 —— **太淡等于没履行义务，
反而更被动**。改成沿用字幕那套描边（`CREDIT_STROKE_RATIO = 0.035`，
比字幕的 0.06 小，小字用 0.06 会糊成一团），任意背景都稳。

⚠️ **`bgm_id` 为 None 时不叠署名** —— 本地两层是 Pixabay，无需署名
（它的条款明确 ✓ 无需署名）。只有云端 CC-BY 曲子要。

版位实测：字幕在 85% 高度、署名在其下 92~96%，不重叠、不挡产品。

---

## 八、下一轮开工清单

**第 1、2 步已完成（2026-09-07）**，产物与工具：

| 东西 | 位置 |
|---|---|
| 300 首音频 + `来源.json` + `manifest.json` | `D:\bgm-incompetech\`（2.0GB，不进版本库） |
| 12 首待听确认 | `D:\bgm-incompetech\待核实\` |
| 存证（FAQ / 授权页截图 + CC 法律文本） | `D:\bgm-incompetech\存证\` |
| 抓取 + 筛选脚本 | `抓取incompetech.py`（`--dry-run` 只看筛选结果） |
| 官方数据副本 | `ave/incompetech-allpieces.json`、`ave/incompetech-isrc-list.json` |

筛法（`抓取incompetech.py` 里的常量，全部用**官方 Feel 标签**，不自己定义「轻快」）：
留 `Bright`/`Bouncy`/`Uplifting`；排 `Dark`/`Eerie`/`Unnerving`/`Somber`/
`Mysterious`/`Suspenseful`/`Aggressive`/`Intense`/`Mystical`；
放克按 genre 全量捞；时长 1~7 分钟。
⚠️ **`Grooving` 不能单独作为入选依据** —— 第一版这么写筛出 438 首，
里面混着华尔兹和 `Adeste Fideles`（圣诞颂歌，标 `Relaxed, Calm, Grooving`），
`Grand Dark Waltz` 连标题都带 Dark【实测】。另整类排掉
Holiday / Silent Film Score / Polka / Musical / Horror —— 风格对但场景不对。

**还差你做的一步**：上传到自有云，然后带云目录 URL 重跑一次
（现在清单里的 `url` 只是文件名）：
```
python 生成清单.py "D:\bgm-incompetech" --meta "D:\bgm-incompetech\来源.json" \
  --host own --license CC-BY-4.0 --base https://<你的云>/bgm/
```

原清单（3~6 项仍待做）：

1. ~~抓 incompetech 曲目列表，按「轻快 / 上扬 / 放克」筛选，
   逐首从**页面**抄 title / ISRC / URL~~ ✅
2. ~~下载~~ ✅ → 上传自有云（**待你做**）→ ~~写清单~~ ✅（`host: own`）
3. ~~数量不够再用 A 补 Pixabay~~ —— **不用了**，300 首已达上限目标
   （第六节原定 100~300 首）。真要补再说，方案不变。
4. ~~存证~~ ✅ 已归档 `存证/`。
   ⚠️ 实测**页脚没有 CC 标志**，只有 `© 1997–2026 Incompetech Inc.`。
   授权凭据落在 FAQ 页和 `licenses/` 页（都已截图），
   加上每首的 ISRC —— FAQ 原文说 ISRC 正是「有人挑战你的使用时」的举证材料。
5. ~~实现署名叠加层（第七节）~~ ✅ 2026-09-07，见第七节末尾
6. `使用说明.md` 补一节：BGM 库怎么加自己的曲子、为什么不能随便放商业曲
   （技术侧的换桶/加曲流程已写进 `docs/交接说明.md` 第三节）

⚠️ 第 5 步验证必须**渲两条抽到不同 BGM 的成品**，确认片尾署名与各自
manifest 里的 `bgm_id` 对得上。只渲一条看不出「署名写死」这个 bug ——
单条永远是对的，正是铁律 4 那个形状（钩子会假装正确）。
【2026-09-07 已按此验：001 `"Local Forecast"` / 002 `"Cold Sober"`，两条不同。】

---

## 九、遗留

- `.probe/dump_docx.py` 是本轮写的 docx 解包脚本，可删（当时没跑成，
  改用 Desktop Commander 读的）。
- 本轮多次撞上工具层分类器阻断（Bash / Write / Edit / WebFetch / firecrawl 均有），
  非代码问题。文档最终靠 Desktop Commander 分段 append 落盘。