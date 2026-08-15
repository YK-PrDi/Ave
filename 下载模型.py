"""下载语音识别模型。走国内镜像，支持中断续传。

    python 下载模型.py            # 默认下 medium（1.5G，更准）
    python 下载模型.py small      # 下 small（484M，快但专业词易错）

为什么不用 huggingface_hub 自带的下载：
它默认走 HuggingFace 的 xet 存储后端，国内镜像上不通（实测报 401），
禁用 xet 后又走不到镜像。直接按 URL 拉文件最省事，也好做续传。
"""

import os
import sys
import time
import urllib.error
import urllib.request

MIRROR = "https://hf-mirror.com"
REPOS = {
    "small": ("Systran/faster-whisper-small", 484),
    "medium": ("Systran/faster-whisper-medium", 1528),
}
FILES = ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]

ROOT = os.path.dirname(os.path.abspath(__file__))


def human(n):
    for u in ("B", "K", "M", "G"):
        if n < 1024:
            return f"{n:.0f}{u}"
        n /= 1024
    return f"{n:.1f}T"


def download(url, dest):
    """带进度和续传的下载。"""
    tmp = dest + ".part"
    done = os.path.getsize(tmp) if os.path.exists(tmp) else 0

    req = urllib.request.Request(url)
    if done:
        req.add_header("Range", f"bytes={done}-")
        print(f"      续传，已有 {human(done)}")

    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as e:
        if e.code == 416:           # 已经下完了
            os.replace(tmp, dest)
            return True
        raise

    total = int(resp.headers.get("Content-Length", 0)) + done
    mode = "ab" if done else "wb"
    t0, last = time.time(), 0

    with open(tmp, mode) as f:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            now = time.time()
            if now - last > 0.5:
                last = now
                spd = done / max(now - t0, 0.1)
                pct = f"{done * 100 / total:.0f}%" if total else "?"
                sys.stdout.write(
                    f"\r      {pct}  {human(done)}/{human(total)}  "
                    f"{human(spd)}/s   ")
                sys.stdout.flush()

    sys.stdout.write("\r" + " " * 60 + "\r")
    os.replace(tmp, dest)
    return True


def main():
    size = sys.argv[1] if len(sys.argv) > 1 else "medium"
    if size not in REPOS:
        print(f"只支持 {' / '.join(REPOS)}")
        return 1

    repo, mb = REPOS[size]
    out = os.path.join(ROOT, "models", f"fw_{size}")
    os.makedirs(out, exist_ok=True)

    print(f"下载 {size} 模型（约 {mb}M）到 models/fw_{size}/")
    print(f"镜像 {MIRROR}\n")

    for i, name in enumerate(FILES, 1):
        dest = os.path.join(out, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(f"  [{i}/{len(FILES)}] {name} 已存在，跳过")
            continue
        print(f"  [{i}/{len(FILES)}] {name}")
        url = f"{MIRROR}/{repo}/resolve/main/{name}"
        for attempt in range(3):
            try:
                download(url, dest)
                print(f"      完成 {human(os.path.getsize(dest))}")
                break
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                if attempt == 2:
                    print(f"\n  下载失败: {e}")
                    print("  已下载的部分会保留，重新运行本脚本可续传。")
                    return 1
                print(f"      第 {attempt + 1} 次失败，重试…")
                time.sleep(2)

    print(f"\n模型就绪: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
