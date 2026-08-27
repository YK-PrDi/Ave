"""准备随包分发的二进制素材：ffmpeg.exe 和 fonts/。

    python 准备素材.py            # 检查并补齐缺失的素材
    python 准备素材.py --check    # 只报缺什么，不下载
    python 准备素材.py --force    # 重下所有素材（校验失败时用）

为什么需要这个脚本：ffmpeg.exe（144MB）和字体都在 .gitignore 里，
`git clone` 下来是没有的。它们体积大、各有授权，进版本库等于版本库
本身在分发 GPL 二进制和非商用字体，授权面更麻烦。所以换开发机后
要重新准备一次 —— 这个脚本就是那个「一次」。

**注意**：这只影响「重新打包」。给最终用户的 exe 分发包里
ffmpeg 和字体都已打进去了（见 Ave.spec 的 datas），用户不用管这个。

⚠ 这里的 FFMPEG_URL 与 licenses/ffmpeg/SOURCE-OFFER.md 引用的是同一个
钉死的 release —— 合规文档和构建脚本共用一个真相源。改这里要同步改那边，
`--check` 会校验两者一致。
"""

import argparse
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import textwrap
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# 复用下载模型.py 里已经写好的 Range 续传 + 416 处理，别重写一份。
_dl = __import__("下载模型")
download = _dl.download
human = _dl.human

# ---------------- 素材来源（钉死，不用滚动 tag）----------------

# ⚠ 不要改成 BtbN 的 `latest` tag。那个是滚动的 —— 实测同名资产
# ffmpeg-n8.1-latest-win64-gpl-8.1.zip 会被原地重新上传，
# 过段时间下回来的已经不是这一份，GPL 源码承诺会对不上。
FFMPEG_RELEASE = "autobuild-2026-08-15-13-02"
FFMPEG_ASSET = "ffmpeg-n8.1.2-44-g7c533d0f86-win64-gpl-8.1.zip"
FFMPEG_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/"
              f"{FFMPEG_RELEASE}/{FFMPEG_ASSET}")
FFMPEG_ZIP_SHA256 = \
    "0e7829b6e1ba867e37bbad17153de258bd3bffaa3b745626a6424df0ea113970"
FFMPEG_EXE_SHA256 = \
    "5d5e06fbb900fd7a45a82eb0529e67f905853432139f673ac90aff45930504d8"

# 我们自己发布 GPL 源码归档的那个 release。`--check` 会实查它上面有没有资产。
SOURCE_REPO = "YK-PrDi/Ave"
SOURCE_RELEASE_TAG = "v0.1.0"

# 思源黑体。⚠ 必须用 release 里的 zip，不能走 raw.githubusercontent 单文件 ——
# 那个路径下回来只有 1.44MB（正常 17MB），magic 是 OTTO 看着像真 OTF，
# 但 Pillow 加载报 `horizontal metrics (hmtx) table missing`【实测】。
# 字幕走 Pillow 渲 PNG，Pillow 加载不了就等于没有。
HAN_URL = ("https://github.com/adobe-fonts/source-han-sans/releases/download/"
           "2.005R/09_SourceHanSansSC.zip")
HAN_MEMBER = "SubsetOTF/SC/SourceHanSansSC-Bold.otf"
HAN_SHA256 = \
    "df2b90f5bcc6d01dfc964cec5f6d535d6b6aebd26ed7fd79a9c1b3f2112fcb6b"

# 阿里巴巴普惠体 3.0（默认字幕字体，免费商用无需授权）。
# ⚠ **脚本不代下，必须手动**：官方站 www.alibabafonts.com 是 JS 应用（HTML 里没有
# 静态下载链接、无头浏览器访问超时），阿里 OSS 直链全部 403，GitHub 上
# 18 个仓库全是非官方转载（0~25 stars）。从随机镜像下字体二进制无法验证
# 是否官方原版、也无法验证授权文件 —— 与那份 1.44MB 假 OTF 同类风险，
# 只会更隐蔽。所以这里只检查 + 给指引，不下载。
# 缺了不致命：config.FONT_FALLBACK 会自动退到思源黑体。
PUHUI_FILES = {
    "AlibabaPuHuiTi-3-105-Heavy.ttf": "Heavy(105)，当前默认",
    "AlibabaPuHuiTi-3-115-Black.ttf": "Black(115)，可选更重",
}

# 新青年体只能从剪映字体目录拷，没有公开下载。缺了不致命 ——
# 默认字体已是普惠体 / 思源黑体（config.SUBTITLE_FONT）。
XQN_NAME = "新青年体.ttf"
XQN_JIANYING = os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "JianyingPro", "User Data",
    "Resources", "Font", XQN_NAME)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_font(path):
    """用 Pillow 真加载一次。只看体积不够 —— 那个 1.44MB 的假文件
    magic 也是 OTTO，看着像真 OTF，加载才报错【实测】。"""
    try:
        from PIL import ImageFont
        f = ImageFont.truetype(path, 48)
        return True, "/".join(str(x) for x in f.getname())
    except Exception as e:                      # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def fetch_zip_member(url, member, dest, expect_sha=None, label=""):
    """下载 zip、取出其中一个成员、校验。zip 存成 .part 支持续传。"""
    tmp = dest + ".zip"
    if not os.path.isfile(tmp):
        print(f"  下载 {label}（可能要几分钟，支持断点续传）")
        print(f"    {url}")
        # ⚠ 本机实测约 4MB/min。首次给 900s 超时导致 curl exit 28
        # 被自己掐断（ffmpeg 停在 35/160MiB）—— 不是网络断【实测】。
        # download() 内部用 urllib + Range 续传，重跑即接着下。
        for attempt in range(3):
            try:
                download(url, tmp)
                break
            except Exception as e:              # noqa: BLE001
                if attempt == 2:
                    print(f"  下载失败: {e}")
                    print("  已下载部分保留在 "
                          f"{os.path.basename(tmp)}.part，重跑本脚本可续传。")
                    return False
                print(f"    第 {attempt + 1} 次失败，重试…")
    else:
        print(f"  复用已下载的 {os.path.basename(tmp)}")

    try:
        with zipfile.ZipFile(tmp) as z:
            names = z.namelist()
            if member not in names:
                cand = [n for n in names
                        if n.endswith(os.path.basename(member))]
                if not cand:
                    print(f"  ✗ zip 里找不到 {member}")
                    return False
                print(f"  ⚠ {member} 不在，改用 {cand[0]}")
                member = cand[0]
            os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
            with z.open(member) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
    except (zipfile.BadZipFile, OSError) as e:
        print(f"  ✗ 解压失败（zip 可能没下完）: {e}")
        print(f"  删掉 {os.path.basename(tmp)} 后重跑。")
        return False

    if expect_sha:
        got = sha256(dest)
        if got != expect_sha:
            print(f"  ✗ SHA256 不符\n      期望 {expect_sha}\n      实得 {got}")
            return False
        print("  ✓ SHA256 校验通过")
    os.remove(tmp)
    return True


def do_ffmpeg(force=False):
    dest = os.path.join(ROOT, "ffmpeg.exe")
    if os.path.isfile(dest) and not force:
        got = sha256(dest)
        if got == FFMPEG_EXE_SHA256:
            print("ffmpeg.exe  ✓ 已就位，SHA256 相符")
            return True
        print(f"ffmpeg.exe  ⚠ 已存在但 SHA256 不符（{got[:16]}…）")
        print("            换过构建就正常。要重下加 --force")
        return True
    print("ffmpeg.exe  缺失，开始准备")
    if not fetch_zip_member(FFMPEG_URL, "ffmpeg-n8.1.2-44-g7c533d0f86-"
                            "win64-gpl-8.1/bin/ffmpeg.exe", dest,
                            label="ffmpeg GPL full build（约 160MiB）"):
        return False
    r = subprocess.run([dest, "-hide_banner", "-encoders"],
                       capture_output=True, text=True, errors="replace")
    if "libx264" not in r.stdout:
        print("  ✗ 这份 ffmpeg 没有 libx264 —— 软编码兜底会失效")
        return False
    print("  ✓ 含 libx264，软编码兜底可用")
    return True


def do_source_han(force=False):
    dest = os.path.join(ROOT, "fonts", "SourceHanSansSC-Bold.otf")
    if os.path.isfile(dest) and not force:
        ok, name = check_font(dest)
        if ok:
            print(f"思源黑体    ✓ 已就位，Pillow 加载正常（{name}）")
            return True
        print(f"思源黑体    ⚠ 存在但 Pillow 加载失败: {name}")
        print("            重下：--force")
        return False
    print("思源黑体    缺失，开始准备")
    if not fetch_zip_member(HAN_URL, HAN_MEMBER, dest, HAN_SHA256,
                            label="思源黑体 SC（约 90MiB）"):
        return False
    ok, name = check_font(dest)
    print(f"  {'✓' if ok else '✗'} Pillow 加载{'正常' if ok else '失败'}：{name}")
    return ok


def do_puhuiti():
    """只检查 + 给指引，不下载（原因见 PUHUI_FILES 上方注释）。"""
    ok_any = False
    for fname, desc in PUHUI_FILES.items():
        p = os.path.join(ROOT, "fonts", fname)
        if os.path.isfile(p):
            ok, name = check_font(p)
            print(f"普惠体      {'✓' if ok else '✗'} {desc}（{name}）")
            ok_any |= ok
    if ok_any:
        return True
    print("普惠体      ✗ 缺失 —— **需要你手动下一次**")
    print("            默认字幕字体是它，缺了会自动退到思源黑体（仍能出片）")
    print("            官网 https://www.alibabafonts.com 点「字体下载」，取这两个之一：")
    for fname, desc in PUHUI_FILES.items():
        print(f"              {fname}   {desc}")
    print(f"            放进 {os.path.join(ROOT, 'fonts')}\\")
    print("            ⚠ 脚本不代下：官网是 JS 应用、阿里 OSS 直链 403、")
    print("              GitHub 上全是非官方转载，无法验证是否官方原版。")
    return True      # 不当致命错 —— 有回落


def do_xinqingnian():
    dest = os.path.join(ROOT, "fonts", XQN_NAME)
    if os.path.isfile(dest):
        ok, name = check_font(dest)
        print(f"新青年体    {'✓' if ok else '✗'} 已就位（{name}）")
        return True
    if os.path.isfile(XQN_JIANYING):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(XQN_JIANYING, dest)
        ok, name = check_font(dest)
        print(f"新青年体    ✓ 已从剪映字体目录拷入（{name}）")
        return True
    print("新青年体    — 跳过：本机没装剪映，无公开下载渠道")
    print("            不影响出片 —— 默认字体是思源黑体。")
    print("            要用它就从装了剪映的机器拷：")
    print(f"            {XQN_JIANYING}")
    return True


def write_build_info():
    """刷新 licenses/ffmpeg/BUILD-INFO.txt。数据来自实际探测随包 ffmpeg，
    不是手抄 —— 换 ffmpeg 来源后重跑本脚本即同步。"""
    ff = os.path.join(ROOT, "ffmpeg.exe")
    if not os.path.isfile(ff):
        print("BUILD-INFO  — 跳过：ffmpeg.exe 还没准备好")
        return False
    out = subprocess.run([ff, "-hide_banner", "-version"], capture_output=True,
                         text=True, errors="replace").stdout
    ver = out.splitlines()[0]
    cfg = next(l for l in out.splitlines()
               if l.startswith("configuration:"))[len("configuration:"):]
    lic = subprocess.run([ff, "-hide_banner", "-L"], capture_output=True,
                         text=True, errors="replace").stdout.strip()

    dest = os.path.join(ROOT, "licenses", "ffmpeg", "BUILD-INFO.txt")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    body = f"""\
随包 ffmpeg 构建信息
====================

本文件由 `准备素材.py` 生成，数据来自对随包 ffmpeg.exe 的实际探测，
不是手抄的。换 ffmpeg 来源后重跑该脚本刷新本文件。

## 二进制标识

版本字符串   {ver}
文件大小     {os.path.getsize(ff)} 字节
SHA256       {sha256(ff)}

## 许可状态（ffmpeg 自报，`ffmpeg -L` 原文）

{textwrap.indent(lic, "    ")}

configure 里带 --enable-gpl 与 --enable-version3，因此本构建整体按
**GPL version 3 or later** 分发。许可全文见同目录 COPYING.GPLv3。

启用的 GPL-only 外部库（对应 FFmpeg configure 的 EXTERNAL_LIBRARY_GPL_LIST）：
libx264、libx265 —— 二者自身为 GPLv2 or later，全文见 ../x264/ 与 ../x265/。

## 上游来源

构建者      BtbN/FFmpeg-Builds（GitHub Actions 自动构建）
Release     {FFMPEG_RELEASE}
资产名      {FFMPEG_ASSET}
资产 SHA256 {FFMPEG_ZIP_SHA256}
            （取自同 release 的 checksums.sha256，本目录存有副本）
取用文件    压缩包内 bin/ffmpeg.exe

⚠ 不要引用 `latest` 那个 tag。它是滚动的 —— 实测同名资产
  ffmpeg-n8.1-latest-win64-gpl-8.1.zip 会被原地重新上传
  （release published_at 与资产 updated_at 同为 2026-08-15T13:26 一线），
  过段时间下回来的已不是这一份。上面这个 autobuild tag 是钉死的，
  资产文件名也自带精确版本号。

FFmpeg 上游 commit
  7c533d0f86f13a06ec93968f6194349665b3536a
  （2026-08-14T23:17:34Z，已核实存在于 FFmpeg/FFmpeg 上游）

对应源码（Corresponding Source）的获取方式见 SOURCE-OFFER.md。

## configure 全文

{textwrap.indent(textwrap.fill(cfg.strip(), 74), "    ")}
"""
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    print(f"BUILD-INFO  ✓ 已刷新（{os.path.getsize(dest)} 字节）")
    return True


def check_offer_consistency():
    """SOURCE-OFFER.md 必须引用与本脚本同一个 release —— 两处漂了
    就等于承诺的源码和实际分发的二进制对不上。"""
    p = os.path.join(ROOT, "licenses", "ffmpeg", "SOURCE-OFFER.md")
    if not os.path.isfile(p):
        print("SOURCE-OFFER ✗ 缺失，GPL 源码承诺没有落地")
        return False
    txt = io.open(p, encoding="utf-8").read()
    bad = [n for n in (FFMPEG_RELEASE, FFMPEG_ASSET) if n not in txt]
    if bad:
        print(f"SOURCE-OFFER ✗ 没引用 {', '.join(bad)} —— 与本脚本不一致")
        return False
    print("SOURCE-OFFER ✓ 与本脚本引用同一个钉死的 release")
    # 按「尖括号里带『填』字」匹配，不写死具体串。
    # 曾经这里找的是 <待填>，文档后来改成 <发布时填>，这道检查静默失效了
    # —— --check 照样打「素材齐全，可以打包」【2026-08-17 实测】。
    holes = sorted(set(re.findall(r"<[^<>\n]*填[^<>\n]*>", txt)))
    if holes:
        print(f"             ⚠ 还有占位符 {' '.join(holes)} —— "
              "源码归档没上传，仅对外分发前必须补")

    # 归档文件本身在不在。填了 SHA256 不代表义务履行完了 ——
    # 2026-08-17 填完哈希后占位符警告消失，这道提示就成了唯一的信号；
    # 少了它，「还没上传到 release」这件事会彻底静默。
    src = os.path.join(ROOT, "dist-src")
    want = ("ffmpeg-src-7c533d0f86.tar.gz", "ffmpeg-builds-snapshot.tar.gz")
    miss = [n for n in want if not os.path.isfile(os.path.join(src, n))]
    if miss:
        print(f"             ⚠ dist-src/ 缺 {', '.join(miss)} —— "
              "重建命令见 SOURCE-OFFER.md 第四节")
    else:
        print("             ✓ 归档留存 dist-src/")
    check_release_assets(want)
    return True


def check_release_assets(want):
    """实查 GitHub：承诺的源码资产在 release 上吗？

    **不准写死结论。** 2026-08-17 那版把「尚未上传」硬编码在这里，
    2026-08-27 真传上去之后它还在喊没传 —— 而反过来写死「已上传」
    只是换个方向骗人：资产哪天被删了，脚本照样说一切正常。
    所以这里去问 API，让输出跟着事实走。

    离网只降级成「查不了」，不判失败 —— 打包本身不需要联网。
    """
    import json
    import urllib.error
    import urllib.request

    api = (f"https://api.github.com/repos/{SOURCE_REPO}/releases/tags/"
           f"{SOURCE_RELEASE_TAG}")
    try:
        with urllib.request.urlopen(api, timeout=15) as r:
            data = json.load(r)
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"             ℹ 查不到 release（{str(e)[:50]}）—— "
              f"对外分发前手动确认 {SOURCE_RELEASE_TAG} 上有这两个资产")
        return

    got = {a.get("name"): a.get("size", 0) for a in data.get("assets", [])}
    gone = [n for n in want if n not in got]
    if gone:
        print(f"             🔴 release {SOURCE_RELEASE_TAG} 上缺 "
              f"{', '.join(gone)} —— GPL 源码承诺没兑现，别对外分发")
        return
    # 光有文件名不够 —— 上传被截断会留个短文件，名字照样在。
    # 实测过一次：下载少了 195495 字节，哈希直接对不上。
    bad = []
    for n in want:
        local = os.path.join(ROOT, "dist-src", n)
        if os.path.isfile(local) and got[n] != os.path.getsize(local):
            bad.append(f"{n}（远端 {got[n]} vs 本地 {os.path.getsize(local)}）")
    if bad:
        print(f"             🔴 release 上 {'; '.join(bad)} 大小不符 —— "
              "疑似上传被截断，重传")
        return
    print(f"             ✓ release {SOURCE_RELEASE_TAG} 上两个源码资产都在，"
          "大小与本地一致")


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="准备随包分发的二进制素材")
    ap.add_argument("--check", action="store_true", help="只检查，不下载")
    ap.add_argument("--force", action="store_true", help="重下所有素材")
    args = ap.parse_args()

    if args.check:
        print("检查随包素材（不下载）\n")
        rows = [
            ("ffmpeg.exe", os.path.join(ROOT, "ffmpeg.exe"), True),
            ("思源黑体", os.path.join(ROOT, "fonts",
                                   "SourceHanSansSC-Bold.otf"), True),
            ("新青年体", os.path.join(ROOT, "fonts", XQN_NAME), False),
        ]
        # 普惠体两个字重任一个到位即算有（默认用 Heavy）
        for fname in PUHUI_FILES:
            rows.insert(1, (f"普惠体 {fname.split('-')[2]}",
                            os.path.join(ROOT, "fonts", fname), False))
        missing = []
        for name, p, required in rows:
            if os.path.isfile(p):
                print(f"  ✓ {name}  {human(os.path.getsize(p))}")
            elif required:
                print(f"  ✗ {name}  缺失（打包会拒绝）")
                missing.append(name)
            else:
                print(f"  — {name}  缺失（有回落，不阻塞）")
        if not any(os.path.isfile(os.path.join(ROOT, "fonts", f))
                   for f in PUHUI_FILES):
            print()
            print("  ⚠ 默认字幕字体普惠体缺失 —— 当前会自动退到思源黑体出片。")
            print("    要用普惠体：https://www.alibabafonts.com 手动下 "
                  "AlibabaPuHuiTi-3-105-Heavy.ttf 放进 fonts\\")
        print()
        check_offer_consistency()
        if missing:
            print(f"\n缺 {len(missing)} 项。跑 `python 准备素材.py` 补齐。")
            return 1
        print("\n素材齐全，可以打包。")
        return 0

    print("准备随包分发素材（ffmpeg + 字体）")
    print("首次准备要下约 250MiB，本机实测约 4MB/min，请耐心等\n")

    ok = True
    ok &= do_ffmpeg(args.force)
    ok &= do_puhuiti()
    ok &= do_source_han(args.force)
    ok &= do_xinqingnian()
    print()
    write_build_info()
    check_offer_consistency()

    print()
    if ok:
        print("素材准备完成，可以跑 打包.bat 了。")
        return 0
    print("有素材没准备好，见上面的 ✗。修好后重跑本脚本。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
