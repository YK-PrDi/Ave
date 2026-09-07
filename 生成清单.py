"""扫本地音频文件夹，生成云端曲库用的 manifest.json。

用法：
    python 生成清单.py D:\\bgm-pixabay
    python 生成清单.py D:\\bgm-pixabay --base https://xxx.oss-cn-hangzhou.aliyuncs.com/bgm/
    python 生成清单.py D:\\bgm-pixabay --license "Pixabay Content License"

产出 `manifest.json` 落在被扫的目录里，连同音频一起上传到 OSS/COS。

⚠️ **`--base` 就是音频在云端的目录 URL**，脚本把它和文件名拼成每首的 url。
不传的话 url 留成文件名，上传后得手工补 —— 建议直接传。

授权字段（`license` / `source` / `downloaded`）是刻意留的：曲库以后要给
外部客户用，被问起「这音乐哪来的、能不能商用」时要拿得出依据。
Pixabay 的条款写明它可以随时改甚至取消已授予的许可，而许可不追溯的前提是
**你能证明下载日期** —— 所以 `downloaded` 别删。
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# CLI 入口必须 reconfigure stdout 为 UTF-8（铁律 2）——
# Windows 控制台/管道是 GBK，print 中文曲名或 ✓ 直接 UnicodeEncodeError 崩，
# 扫到一半挂掉比不跑更烦。
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".flac")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_ffmpeg():
    """找 ffprobe/ffmpeg。项目根那个优先，没有就靠 PATH。"""
    root = os.path.dirname(os.path.abspath(__file__))
    local = os.path.join(root, "ffmpeg.exe")
    return local if os.path.isfile(local) else "ffmpeg"


def probe_duration(path, ffmpeg):
    """量时长（秒）。量不出返回 0 —— 时长只是给界面显示，不阻塞。

    用 ffmpeg 而不是 ffprobe：项目只随包了 ffmpeg.exe，没带 ffprobe。
    """
    try:
        r = subprocess.run(
            [ffmpeg, "-i", path, "-f", "null", "-"],
            capture_output=True, check=False, encoding="utf-8",
            errors="replace", timeout=60)
        # ffmpeg 把时长打在 stderr：`Duration: 00:02:12.53, start: ...`
        for line in (r.stderr or "").splitlines():
            if "Duration:" in line:
                t = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = t.split(":")
                return round(int(h) * 3600 + int(m) * 60 + float(s), 2)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return 0


def track_id(name):
    """从文件名取稳定 ID。

    Pixabay 的命名是 `作者-曲名-数字ID.mp3`，末段那个数字就是它的曲目 ID，
    拿它最稳。取不到就用去扩展名的文件名。

    ⚠️ **ID 必须稳定**：`pipeline.pick_bgm()` 按它排序来保证同一个 seed
    抽到同一批曲子；缓存文件名也用它。改了 ID 等于换一首曲子。
    """
    stem = os.path.splitext(name)[0]
    tail = stem.rsplit("-", 1)[-1]
    if tail.isdigit() and len(tail) >= 4:
        return tail
    # 没有数字尾巴：用文件名本身，滤掉可能进 URL/路径的字符
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)
    return safe[:80] or "track"


def main():
    ap = argparse.ArgumentParser(description="生成云端 BGM 曲库清单")
    ap.add_argument("dir", help="存放音频的本地文件夹")
    ap.add_argument("--base", default="",
                    help="音频在云端的目录 URL，会和文件名拼成每首的 url")
    ap.add_argument("--license", default="Pixabay Content License",
                    help="授权名称，写进每一条")
    ap.add_argument("--source", default="https://pixabay.com/music/",
                    help="来源站点，写进每一条")
    ap.add_argument("--version", default="",
                    help="清单版本，默认用今天日期")
    ap.add_argument("--meta", default="",
                    help="溯源边车 JSON（抓取脚本产出的 来源.json）,"
                         "里面的官方字段会合并进每一条")
    ap.add_argument("--host", default="",
                    help="来源标记 own / pixabay。"
                         "pixabay 的曲子不准进自有 bucket")
    ap.add_argument("-o", "--out", default="",
                    help="输出路径，默认写到被扫目录里的 manifest.json")
    args = ap.parse_args()

    src = os.path.abspath(args.dir)
    if not os.path.isdir(src):
        print(f"✗ 目录不存在: {src}")
        return 2

    import datetime
    today = datetime.date.today().isoformat()
    version = args.version or today

    # 溯源边车：文件名 → 官方元数据。**只从这里取授权字段** ——
    # 不读 ID3（`docs/BGM授权决策.md` 第六节：曲库站生成的标签常为空或
    # 写着上传者昵称，以它为准会让清单看起来准而实际错）。
    meta = {}
    if args.meta:
        try:
            with open(args.meta, encoding="utf-8") as f:
                meta = json.load(f).get("tracks") or {}
            print(f"读到溯源边车 {len(meta)} 条: {args.meta}")
        except (OSError, ValueError) as e:
            print(f"✗ 边车读不了: {e}")
            return 2

    files = sorted(f for f in os.listdir(src)
                   if os.path.splitext(f)[1].lower() in AUDIO_EXTS)
    if not files:
        print(f"✗ {src} 里没有音频文件（认 {'/'.join(AUDIO_EXTS)}）")
        return 2

    ffmpeg = find_ffmpeg()
    base = args.base.rstrip("/") + "/" if args.base else ""

    print(f"扫描 {src}")
    print(f"找到 {len(files)} 个音频文件，开始算校验和与时长…\n")

    tracks, seen, total_size, no_meta = [], {}, 0, []
    for i, name in enumerate(files, 1):
        p = os.path.join(src, name)
        size = os.path.getsize(p)
        tid = track_id(name)

        # ID 撞了就加后缀 —— 撞 ID 会让两首曲子共用一个缓存文件
        if tid in seen:
            seen[tid] += 1
            tid = f"{tid}_{seen[tid]}"
        else:
            seen[tid] = 1

        dur = probe_duration(p, ffmpeg)
        digest = sha256(p)
        total_size += size

        entry = {
            "id": tid,
            "name": name,
            "url": (base + urllib.parse.quote(name)) if base else name,
            "size": size,
            "sha256": digest,
            "duration": dur,
            "license": args.license,
            "source": args.source,
            "downloaded": today,
        }
        # 边车里有这首就用官方字段覆盖 —— 边车是从官方页面抄的，
        # 比命令行那个「一刀切」的 --license 准。
        # `bgm_cloud._valid()` 只校验 id + url，其余原样透传，所以随便加。
        if name in meta:
            entry.update(meta[name])
            # ⚠️ 边车给的是 `source_url`，命令行那个字段叫 `source` ——
            # 不删的话 incompetech 的曲子会顶着 `source: pixabay.com`
            # 留在清单里，**授权对了但来源写错**，以后核查全乱。
            entry.pop("source", None)
        else:
            no_meta.append(name)
        if args.host:
            entry["host"] = args.host
        tracks.append(entry)
        print(f"  [{i:3d}/{len(files)}] {name}"
              f"  {size / 1e6:.1f}MB  {dur:.0f}s  {digest[:12]}…")

    out = args.out or os.path.join(src, "manifest.json")
    data = {"version": version, "tracks": tracks}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    # 边车里没有的曲子会顶着命令行那个 --license 落进清单。
    # **必须说出来** —— 静默按默认值填等于伪造溯源信息（铁律 9 的形状：
    # 不报错、看起来在工作，其实清单里有几条授权是猜的）。
    if meta and no_meta:
        print(f"\n⚠ 有 {len(no_meta)} 首不在边车里，授权字段用的是命令行默认值"
              f"（--license \"{args.license}\"）：")
        for n in no_meta[:10]:
            print(f"    {n}")
        if len(no_meta) > 10:
            print(f"    …另 {len(no_meta) - 10} 首")
        print("  这些曲子的来源没有凭据。混装了不同来源就分开跑，别共用一份边车。")

    print(f"\n清单已写入: {out}")
    print(f"  曲目 {len(tracks)} 首 · 合计 {total_size / 1e6:.0f}MB "
          f"· 版本 {version}")
    if not base:
        print("\n⚠ 没传 --base，每首的 url 只是文件名。")
        print("  上传后要么重跑并带 --base，要么手工把 url 补成完整地址。")
    else:
        print(f"  url 形如: {tracks[0]['url']}")

    print("\n下一步：")
    print(f"  1. 把这 {len(tracks)} 个音频和 manifest.json 一起上传到 "
          "OSS/COS 同一个目录")
    print("  2. 把 manifest.json 的公网地址填进 "
          "%LOCALAPPDATA%\\Ave\\credentials.json 的 BGM_CLOUD_MANIFEST")
    print("  3. 重启服务，界面「背景音乐」区会显示云端曲库")
    return 0


if __name__ == "__main__":
    sys.exit(main())