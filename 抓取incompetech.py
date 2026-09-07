"""从 incompetech 官方曲目页筛「轻快 / 上扬 / 放克」并下载，产出溯源边车。

用法：
    python 抓取incompetech.py --dry-run          # 只看筛出哪些，不下载
    python 抓取incompetech.py -o D:\\bgm-incompetech
    python 抓取incompetech.py -o D:\\bgm-incompetech --limit 3   # 先验 3 首

**元数据只从官方页面来**（`docs/BGM授权决策.md` 第六节）：
`ave/incompetech-allpieces.json` 是从 `music.html` 那一页的 `allPieces`
数组原样落盘的 —— 那一页就是官方下载页，title / isrc / feel / genre / filename
全在里面，下载按钮的 URL 也由它生成。所以**不读 ID3、不碰搜索摘要**。
`ave/incompetech-isrc-list.json` 是 `full_list.php`（官方 ISRC 总表）的独立副本，
用来交叉核对 ISRC ↔ 曲名对不对得上，对不上的**直接丢弃**，不猜。

授权（2026-09-06 从 FAQ 原文核实，与文档记载一致）：
CC-BY 4.0，可商用、可货币化、可再分发、可改编，**必须署名且用真实曲名**。

产出：
    <out>/*.mp3          音频
    <out>/来源.json      每首的官方元数据（给 `生成清单.py --meta` 用）
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# 铁律 2：CLI 入口必须 reconfigure 成 UTF-8。曲名里有 ' 和重音字符，
# Windows 控制台 GBK 直接 UnicodeEncodeError 崩，下到一半挂掉比不跑更烦。
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

_HERE = os.path.dirname(os.path.abspath(__file__))
ALLPIECES = os.path.join(_HERE, "ave", "incompetech-allpieces.json")
ISRC_LIST = os.path.join(_HERE, "ave", "incompetech-isrc-list.json")

LIST_PAGE = "https://incompetech.com/music/royalty-free/music.html"
DL_BASE = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"
ARTIST = "Kevin MacLeod"
LICENSE = "CC-BY-4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"

# 官方 Feel 标签。**不自己定义「轻快」** —— 用他们自己的标注，
# 免得靠曲名或印象猜（那正是文档第六节禁的那类来源）。
# 「轻快 / 上扬」的硬信号。
KEEP = ("Bright", "Bouncy", "Uplifting")
# ⚠️ **`Grooving` 不能单独作为入选依据** —— 它只表示「有律动」，
# 实测把华尔兹和 `Adeste Fideles`（圣诞颂歌，标 `Relaxed, Calm, Grooving`）
# 全放进来了，`Grand Dark Waltz` 连标题都带 Dark。
# 只在它与 KEEP 之一同现、或本身就是放克时才算。
GROOVE = "Grooving"
# 排除项设得狠是有意的：一首同时标 Bright 和 Dark 的曲子，
# 垫在带货口播底下不合适。宁可少而准。
DROP = ("Dark", "Eerie", "Unnerving", "Somber", "Mysterious",
        "Suspenseful", "Aggressive", "Intense", "Mystical", "Horror")
FUNK_GENRE_ID = "8"        # genre 表里 Funk 的 id，放克全量捞

# 风格对但**场景不对**的 genre，整类排掉。产出是带货推广视频：
#   Holiday    圣诞颂歌，非节日期间用很怪
#   Silent Film Score / Polka / Musical  年代感或舞台感太强
#   Horror     不解释
DROP_GENRES = {"9": "Holiday", "20": "Silent Film Score",
               "15": "Polka", "10": "Horror", "14": "Musical"}

MIN_SEC, MAX_SEC = 60, 420
TIMEOUT = 60
RETRIES = 3
BACKOFF = 1.5
WORKERS = 3                # 别开大 —— 人家免费给曲子，不该把带宽打满


def clean(s):
    """官方数据里有字段带 \\r\\n 尾巴（`Dentaneosuchus Hunt\\r\\n\\r\\n`），
    直接拿去当文件名或写进清单会留脏字符。"""
    return " ".join((s or "").split())


def secs(hms):
    """`00:04:07` → 247。量不出返回 0，让它进不了时长闸。"""
    try:
        h, m, s = (int(x) for x in (hms or "").split(":"))
        return h * 3600 + m * 60 + s
    except ValueError:
        return 0


def feels(p):
    return [x.strip() for x in (p.get("feel") or "").split(",") if x.strip()]


def _read_json(path):
    """读落盘的官方副本。

    ⚠️ **可能是双重编码的**：抓取时用的 `browser_evaluate` 会把返回值再
    JSON 序列化一次，而我们返回的已经是字符串，于是文件里躺着的是
    `"{\\"pieces\\":...}"`。解一次得到 str 就再解一次 —— 不这么兜的话
    报的是 `'str' object has no attribute 'get'`，离真因很远。
    """
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if isinstance(d, str):
        d = json.loads(d)
    return d


def load():
    """读两份官方副本，返回 (pieces, genre 名表, isrc→曲名)。"""
    d = _read_json(ALLPIECES)
    gmap = {str(g["id"]): g["genre"] for g in d.get("genres") or []}
    official = {r["isrc"]: clean(r["title"])
                for r in _read_json(ISRC_LIST).get("rows") or []}
    return d["pieces"], gmap, official


def select(pieces, official):
    """筛曲子。返回 (入选, 丢弃原因计数)。

    ⚠️ **ISRC 对不上就丢**。文档第四节那条教训：授权是真的但
    「这首曲子是哪一首」是猜的 —— 一样不能用。这里两份官方数据
    互校一次，成本几乎为零，能挡住 `uuid` 字段混进曲名的那类脏数据
    （实测第一条 `The Britons` 的 uuid 是 `61123837`，第二条却是 ISRC 本身，
    说明这个字段不可靠，只信 `isrc`）。
    """
    out, why = [], {}
    def bump(k):
        why[k] = why.get(k, 0) + 1

    for p in pieces:
        title, isrc = clean(p.get("title")), clean(p.get("isrc"))
        fname, f = clean(p.get("filename")), feels(p)
        dur = secs(p.get("length"))

        if not (title and isrc and fname):
            bump("缺 title/isrc/filename")
            continue
        if isrc not in official:
            bump("ISRC 不在官方总表里")
            continue
        if official[isrc].lower() != title.lower():
            bump(f"ISRC↔曲名 两表不一致")
            continue
        if not (MIN_SEC <= dur <= MAX_SEC):
            bump("时长超出 1~7 分钟")
            continue
        if any(x in f for x in DROP):
            bump("带排除标签")
            continue
        gid = str(p.get("genre"))
        if gid in DROP_GENRES:
            bump(f"genre 不适合带货视频（{DROP_GENRES[gid]}）")
            continue
        is_funk = gid == FUNK_GENRE_ID
        hit = any(x in f for x in KEEP)
        # Grooving 只在与 KEEP 同现、或本身是放克时才算（见 GROOVE 注释）
        if not (hit or is_funk or (GROOVE in f and hit)):
            bump("无入选标签且非放克")
            continue
        out.append({"piece": p, "title": title, "isrc": isrc,
                    "filename": fname, "dur": dur, "feel": f})
    return out, why


def dl_url(filename):
    """官方下载直链。空格要转 %20 —— 页面上的 data-url 就是这么拼的。"""
    return DL_BASE + urllib.parse.quote(filename)


def download(url, dest):
    """下载到 dest。先写 `.part` 再 rename。

    ⚠️ **`except HTTPError` 必须排在 `URLError` 前**（铁律 16）——
    前者是后者的子类，写反了 404 会被当网络抖动白重试 3 次。
    返回 True=下成了，False=4xx 放弃（曲名可能改过，重试无意义）。
    """
    tmp = dest + ".part"
    last = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Ave-BGM/1.0"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r, \
                    open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            if os.path.getsize(tmp) < 10000:
                raise RuntimeError(f"文件太小（{os.path.getsize(tmp)} 字节），"
                                   "可能下到的是错误页")
            os.replace(tmp, dest)
            return True, ""
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                return False, f"HTTP {e.code}（地址错，不重试）"
            last = f"HTTP {e.code}"
        except (urllib.error.URLError, OSError, RuntimeError) as e:
            last = str(e)[:120]
        if attempt + 1 < RETRIES:
            time.sleep(BACKOFF * (2 ** attempt))
    try:
        os.remove(tmp)
    except OSError:
        pass
    return False, f"重试 {RETRIES} 次仍失败: {last}"


def meta_of(sel, today):
    """一首曲子的溯源记录。字段按文档第六节的形态。

    `source_url` 指官方曲目列表页 —— incompetech **没有每首一页**，
    那一页就是官方下载页（举证规格是「打印显示该曲子的页面」，
    附上 ISRC 即可定位到具体哪一首）。
    """
    return {
        "title": sel["title"],
        "artist": ARTIST,
        "license": LICENSE,
        "license_url": LICENSE_URL,
        "source_url": LIST_PAGE,
        "download_url": dl_url(sel["filename"]),
        "isrc": sel["isrc"],
        "feel": ", ".join(sel["feel"]),
        "bpm": clean(sel["piece"].get("bpm")),
        "verified_at": today,
        # 照抄官方生成器 `renderCC()` 的输出（licenses/ 页点
        # 「Use Creative Commons」那个）。**不要按 FAQ 那版拼** ——
        # 两版措辞不同：这版曲名带引号且单独一行、链接是 http。
        # 生成器是他们让人复制粘贴的官方输出，以它为准。
        "attribution": (f'"{sel["title"]}"\n'
                        f"{ARTIST} (incompetech.com)\n"
                        "Licensed under Creative Commons: By Attribution 4.0\n"
                        "http://creativecommons.org/licenses/by/4.0/"),
    }


def main():
    ap = argparse.ArgumentParser(description="抓 incompetech 轻快风格曲子")
    ap.add_argument("-o", "--out", default="", help="下载到哪个文件夹")
    ap.add_argument("--dry-run", action="store_true", help="只筛不下")
    ap.add_argument("--limit", type=int, default=0, help="只下前 N 首（验直链用）")
    args = ap.parse_args()

    import datetime
    today = datetime.date.today().isoformat()

    pieces, gmap, official = load()
    sel, why = select(pieces, official)
    print(f"官方数据 {len(pieces)} 首 · ISRC 总表 {len(official)} 条")
    print(f"筛出 {len(sel)} 首\n")
    print("丢弃原因：")
    for k, v in sorted(why.items(), key=lambda x: -x[1]):
        print(f"  {v:5d}  {k}")

    by_genre = {}
    for s in sel:
        g = gmap.get(str(s["piece"].get("genre")), "?")
        by_genre[g] = by_genre.get(g, 0) + 1
    print("\n入选按 genre 分布：")
    for k, v in sorted(by_genre.items(), key=lambda x: -x[1]):
        print(f"  {v:5d}  {k}")
    total_min = sum(s["dur"] for s in sel) / 60
    print(f"\n合计时长 {total_min:.0f} 分钟，预估 ~{total_min * 1.4:.0f} MB")

    if args.dry_run:
        print("\n前 25 首示例：")
        for s in sel[:25]:
            print(f"  {s['title']}  [{', '.join(s['feel'])}]  "
                  f"{s['dur'] // 60}:{s['dur'] % 60:02d}  {s['isrc']}")
        print("\n（--dry-run，未下载）")
        return 0

    if not args.out:
        print("\n✗ 要下载得给 -o 指定文件夹（或加 --dry-run 只看筛选结果）")
        return 2
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    todo = sel[:args.limit] if args.limit else sel
    print(f"\n下载 {len(todo)} 首到 {out}\n")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def one(s):
        dest = os.path.join(out, s["filename"])
        if os.path.exists(dest) and os.path.getsize(dest) > 10000:
            return s, True, "已存在，跳过"
        ok, err = download(dl_url(s["filename"]), dest)
        return s, ok, err

    done, fails = [], []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = [pool.submit(one, s) for s in todo]
        for i, fut in enumerate(as_completed(futs), 1):
            s, ok, note = fut.result()
            if ok:
                done.append(s)
                print(f"  [{i:3d}/{len(todo)}] ✓ {s['title']}"
                      + (f"  ({note})" if note else ""))
            else:
                fails.append(f"{s['title']}: {note}")
                print(f"  [{i:3d}/{len(todo)}] ✗ {s['title']}  {note}")

    # 边车：只记下成了的那些。**不记没下成的** ——
    # 清单里躺着本地没有的曲子，渲染时才发现缺文件。
    side = os.path.join(out, "来源.json")
    existing = {}
    if os.path.exists(side):
        try:
            with open(side, encoding="utf-8") as f:
                existing = json.load(f).get("tracks") or {}
        except (OSError, ValueError):
            existing = {}
    for s in done:
        existing[s["filename"]] = meta_of(s, today)
    with open(side, "w", encoding="utf-8") as f:
        json.dump({"source": "incompetech.com (Kevin MacLeod)",
                   "license": LICENSE, "license_url": LICENSE_URL,
                   "source_page": LIST_PAGE, "verified_at": today,
                   "tracks": existing}, f, ensure_ascii=False, indent=1)

    print(f"\n成功 {len(done)} 首，失败 {len(fails)} 首")
    for m in fails[:15]:
        print(f"  ✗ {m}")
    print(f"溯源边车已写: {side}（累计 {len(existing)} 首）")
    print("\n下一步：python 生成清单.py "
          f'"{out}" --meta "{side}" --base <你的云目录URL>')
    return 0


if __name__ == "__main__":
    sys.exit(main())
