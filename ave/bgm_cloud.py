"""云端 BGM 曲库：拉清单 + 按需下载 + 本地缓存。

为什么要这个：曲库要扩到 100~300 首（0.3~0.8GB），随包会把分发 zip 从
192MB 顶到 1GB，微信都传不了。

**为什么按需下载可行**：`pipeline.pick_bgm()` 随机只需要「清单」，
音频本体仅在 `render()` 那一刻要真实可读。且每条成品只用一首 ——
全量 39 条是 39 次有放回抽样，期望只碰到 30~36 首（约 90MB），
**下载量与库大小无关**，100 首和 300 首都是这个数。

保持成**纯后端**（照 `tts.py` / `vision.py` 那套）：只管清单和文件，
不碰 ffmpeg、不碰随机。随机归 `pipeline.pick_bgm()`。

清单格式（`生成清单.py` 产出）：

    {"version": "2026-09-01",
     "tracks": [{"id": "...", "name": "...", "url": "...",
                 "size": 2600000, "sha256": "...", "duration": 132.5,
                 "license": "Pixabay Content License",
                 "source": "https://pixabay.com/music/-152767/",
                 "downloaded": "2026-08-30"}]}
"""

import hashlib
import json
import os
import time

from ave import config

TIMEOUT = 30
RETRIES = 3
BACKOFF = 1.5          # 指数退避 1.5s → 3.0s，同 tts / vision
PREFETCH_WORKERS = 4   # 别开太多，打爆带宽反而慢


class Fatal(RuntimeError):
    """不该重试的错误：URL 写错、没权限、文件不存在。

    ⚠️ **为什么要单独一个类**：`ensure_local()` 的重试兜的是
    `(RuntimeError, OSError)`，而 `urllib.error.HTTPError` **既是 URLError
    又是 OSError 的子类** —— 不区分的话 404 会被当成网络抖动白重试 3 次、
    每首白等 4.5 秒。300 首里有几十个 URL 写错就是几分钟纯浪费【实测】。
    这是铁律 16 换了个马甲：那条说的是 except 顺序，这里是**异常继承**。
    """

# 清单缓存有效期。**别每次调用都去拉** —— 界面每刷一次 BGM 面板就会调
# `cache_stats()`，渲染开始时也要拉一次，不设 TTL 等于反复打服务器。
# 曲库不会一分钟内变几次，10 分钟足够新。
MANIFEST_TTL = 600


def sha256(path):
    """算文件 SHA256。分块读 —— 曲子几 MB，别整个塞内存。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def enabled():
    """有清单 URL 才算启用云端。空 = 完全回落本地两层，老用户零感知。"""
    return bool(config.BGM_CLOUD_MANIFEST)


def _explain(code, detail):
    """把云存储的错误翻成中文再附原文 —— 运营看不懂 `AccessDenied`。"""
    hints = [
        ("AccessDenied", "没有访问权限，检查 bucket 是否公读、或密钥是否有效"),
        ("NoSuchBucket", "bucket 不存在，检查 BGM_CLOUD_MANIFEST 的地址"),
        ("NoSuchKey", "清单文件不存在，确认已上传 manifest.json"),
        ("SignatureDoesNotMatch", "签名不符，密钥可能填错了"),
        ("AccountOverdue", "云存储账户欠费，去控制台结清"),
    ]
    low = (detail or "").lower()
    for needle, msg in hints:
        if needle.lower() in low:
            return f"{msg}。原文: {detail[:300]}"
    if code == 403:
        return f"云存储拒绝访问（权限或欠费）。原文: {detail[:300]}"
    if code == 404:
        return f"清单地址不存在（404）。原文: {detail[:300]}"
    return detail[:400] or f"HTTP {code}"


def _get(url, timeout=TIMEOUT):
    """GET 一个 URL，返回 bytes。失败抛 RuntimeError。

    ⚠️ **`except HTTPError` 必须排在 `except URLError` 前面**（铁律 16）——
    前者是后者的子类，写反了 4xx 永远进不去那个分支，会被当成网络抖动
    白重试 3 次、等 4.5 秒退避，且服务端错误原文被丢掉。
    """
    import urllib.error
    import urllib.request

    last = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:600]
            except OSError:
                pass
            if 400 <= e.code < 500:
                # 4xx 是地址/权限错，重试无意义
                raise RuntimeError(
                    f"云端曲库返回 {e.code}: {_explain(e.code, detail)}") from e
            last = RuntimeError(f"云端曲库 {e.code}: {detail}")
        except (urllib.error.URLError, OSError) as e:
            last = e
        if attempt + 1 < RETRIES:
            time.sleep(BACKOFF * (2 ** attempt))
    raise RuntimeError(f"云端曲库连不上（重试 {RETRIES} 次）: {last}")


def _read_cached_manifest():
    try:
        with open(config.BGM_MANIFEST_CACHE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def fetch_manifest(force=False):
    """拉清单，返回 (tracks, note)。

    note 非空表示有情况要告诉用户 —— **不准静默退化**（铁律 9 那个教训：
    看起来在工作其实没有）。

    拉失败就用上次缓存的那份：离线仍能按上次的库随机，已缓存的照常出片。
    都没有则返回空列表 → 调用方回落本地两层。

    **本地清单在 TTL 内直接复用，不打服务器**（`force=True` 强制刷新）。
    界面每刷一次面板都会问一次，不缓存等于反复请求。
    """
    if not enabled():
        return [], ""

    # TTL 内直接用本地副本
    if not force:
        try:
            age = time.time() - os.path.getmtime(config.BGM_MANIFEST_CACHE)
            if age < MANIFEST_TTL:
                tracks = _valid(_read_cached_manifest().get("tracks") or [])
                if tracks:
                    return tracks, ""
        except OSError:
            pass

    try:
        raw = _get(config.BGM_CLOUD_MANIFEST)
        data = json.loads(raw.decode("utf-8"))
        tracks = data.get("tracks") or []
        if not isinstance(tracks, list):
            raise ValueError("清单格式不对，tracks 应是数组")
        # 存一份本地副本给离线兜底
        os.makedirs(config.BGM_CACHE_DIR, exist_ok=True)
        tmp = config.BGM_MANIFEST_CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, config.BGM_MANIFEST_CACHE)
        return _valid(tracks), ""
    except (RuntimeError, ValueError, OSError) as e:
        cached = _read_cached_manifest()
        tracks = _valid(cached.get("tracks") or [])
        if tracks:
            return tracks, (f"云端曲库拉取失败，用本地缓存的清单"
                            f"（{len(tracks)} 首）: {str(e)[:150]}")
        return [], f"云端曲库不可用: {str(e)[:200]}"


def _valid(tracks):
    """滤掉缺关键字段的条目。`id` 和 `url` 少一个就没法用。"""
    out = []
    for t in tracks:
        if isinstance(t, dict) and t.get("id") and t.get("url"):
            out.append(t)
    return out


def cache_path(entry):
    """这首曲子在本地缓存里的落点。

    文件名用 `id` + 原扩展名 —— `id` 由清单保证唯一，
    比曲名安全（曲名可能带空格、中文、重名）。
    """
    ext = os.path.splitext(entry.get("name") or entry["url"])[1].lower()
    if ext not in config.BGM_EXTS:
        ext = ".mp3"
    return os.path.join(config.BGM_CACHE_DIR, f"{entry['id']}{ext}")


def is_cached(entry):
    """缓存是否命中。

    只看文件在不在 + 非空，**不每次重算 sha256** —— 39 条渲染要查很多次，
    每次哈希几 MB 太慢。校验在下载完那一刻做（见 `ensure_local`），
    之后信任它。
    """
    p = cache_path(entry)
    try:
        return os.path.getsize(p) > 0
    except OSError:
        return False


def _download(url, dest, timeout=TIMEOUT):
    """下载到 dest。`.part` 续传 + 原子落盘。

    形态取自 `下载模型.py:download()`（Range 续传 + 416 处理），
    去掉了进度打印 —— 这里由 `prefetch()` 统一 emit 事件给前端进度条。

    ⚠️ **必须先写 `.part` 再 rename**：直接写目标文件的话，下载中断会留下
    半截文件，而 `is_cached()` 看「在不在 + 非空」就会把它当成有效缓存，
    之后 ffmpeg 读到坏文件才报错（`launcher.ensure_model()` 踩过同类坑）。
    """
    import urllib.error
    import urllib.request

    tmp = dest + ".part"
    done = os.path.getsize(tmp) if os.path.exists(tmp) else 0

    req = urllib.request.Request(url)
    if done:
        req.add_header("Range", f"bytes={done}-")

    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 416:            # 已经下完了
            os.replace(tmp, dest)
            return
        if 400 <= e.code < 500:
            # 地址/权限错，重试无意义 —— 抛 Fatal 让上层立刻放弃
            raise Fatal(
                f"HTTP {e.code}: {_explain(e.code, '')}（{url[:120]}）") from e
        raise

    mode = "ab" if done and resp.status == 206 else "wb"
    with open(tmp, mode) as f:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    os.replace(tmp, dest)


def ensure_local(entry):
    """保证这首曲子在本地可读，返回路径。已缓存直接返回。

    下载完校验 sha256（清单里给了才校验）。不符就删掉重抛 ——
    留着坏文件会让下次 `is_cached()` 误判成命中。
    """
    dest = cache_path(entry)
    if is_cached(entry):
        return dest

    os.makedirs(config.BGM_CACHE_DIR, exist_ok=True)
    last = None
    for attempt in range(RETRIES):
        try:
            _download(entry["url"], dest)
            want = entry.get("sha256")
            if want:
                got = sha256(dest)
                if got != want:
                    os.remove(dest)
                    raise RuntimeError(
                        f"SHA256 不符（期望 {want[:16]}… 实得 {got[:16]}…）")
            return dest
        except Fatal:
            # 4xx：URL 写错或没权限，重试一万次也一样。直接抛，别浪费时间
            raise
        except (RuntimeError, OSError) as e:
            last = e
            if attempt + 1 < RETRIES:
                time.sleep(BACKOFF * (2 ** attempt))
    raise RuntimeError(f"下载 {entry.get('name') or entry['id']} 失败: {last}")


def prefetch(entries, on_event=None):
    """并发把这批曲子下到本地。返回 (成功数, [失败说明])。

    **渲染前调用**：不然渲染跑到一半才去下载，进度条会莫名卡住
    （单首几 MB、网络慢时要几秒，39 条累积起来很难看）。

    单首失败不抛 —— 那首回落成「这条片子没 BGM」，不该拖垮整批。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    todo = [e for e in entries if not is_cached(e)]
    total = len(todo)
    if not total:
        return 0, []

    ok, fails = 0, []
    with ThreadPoolExecutor(max_workers=PREFETCH_WORKERS) as pool:
        futs = {pool.submit(ensure_local, e): e for e in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            e = futs[fut]
            err = None
            try:
                fut.result()
                ok += 1
            except (RuntimeError, OSError) as exc:
                err = str(exc)[:200]
                fails.append(f"{e.get('name') or e['id']}: {err}")
            if on_event:
                ev = {"type": "bgm_prefetch", "done": i, "total": total,
                      "file": e.get("name") or e["id"]}
                if err:
                    ev["error"] = err
                on_event(ev)
    return ok, fails


def cache_stats():
    """给界面看的：清单总数、已缓存数、占用空间、清单版本。"""
    tracks, note = fetch_manifest()
    n_cached, size = 0, 0
    for t in tracks:
        p = cache_path(t)
        try:
            size += os.path.getsize(p)
            n_cached += 1
        except OSError:
            pass
    ver = _read_cached_manifest().get("version", "")
    return {"enabled": enabled(), "total": len(tracks), "cached": n_cached,
            "size_mb": round(size / 1e6, 1), "version": ver, "note": note}


def clear_cache():
    """清空已下载的曲子（清单副本留着）。返回删掉几个。"""
    n = 0
    try:
        names = os.listdir(config.BGM_CACHE_DIR)
    except OSError:
        return 0
    for f in names:
        if os.path.splitext(f)[1].lower() not in config.BGM_EXTS:
            continue        # 别把 manifest.json 删了
        try:
            os.remove(os.path.join(config.BGM_CACHE_DIR, f))
            n += 1
        except OSError:
            pass
    return n