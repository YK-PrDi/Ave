"""本地 HTTP 服务，给 Vue3 前端调用。

    python -m ave.server          # 起在 http://127.0.0.1:8756

接口：
    GET  /api/health              环境自检（ffmpeg/字体/模型/配音后端是否就绪）
    POST /api/scan                扫素材，返回盘点与预计产量
    POST /api/preview             预览组合方案，不渲染
    POST /api/jobs                提交渲染任务，返回 job_id
    GET  /api/jobs/{id}           查任务状态
    GET  /api/jobs/{id}/events    SSE 实时进度
    POST /api/jobs/{id}/stop      停止任务（当前条跑完后停）
    GET  /api/outputs             列出已产出的成品
    POST /api/open-output         在资源管理器里打开输出目录
    GET  /api/bgm                 列出两层 BGM（内置 + 自定义）
    POST /api/bgm/add             弹文件框，把音频加到自定义层
    POST /api/bgm/delete          删自定义层的一首（内置层拒绝）
    POST /api/copy/list           每个片段的口播状态与 AI 文案（只读缓存）
    POST /api/copy/save           存人工改过的文案
    POST /api/copy/generate       批量生成文案，返回 job_id（复用 SSE）
    POST /api/vision/test         视觉接口自检，真发一次请求
    POST /api/export              成品整条变速导出到子目录，返回 job_id（复用 SSE）

只监听 127.0.0.1，不对外暴露。这是本机工具，不做鉴权。
"""

import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from ave import config, pipeline, vision

app = FastAPI(title="Ave 混剪工具")

# 开发期前端跑在 vite 的 5173 端口，需要放行
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScanReq(BaseModel):
    source: str | None = None


class PreviewReq(BaseModel):
    source: str | None = None
    points: int | None = None
    hook_limit: int | None = None
    seed: int | None = None
    limit: int = 0
    # 卖点语义去重。关掉则同一条里可能出现多个卖点讲同一件事
    dedup: bool = True


class JobReq(PreviewReq):
    out_dir: str | None = None
    bgm_dir: str | None = None
    sub_size: int | None = None
    # 画面倍速。1.0 = 原速，默认 config.PLAYBACK_SPEED（1.2）
    speed: float | None = None
    # 给无口播片段用 AI 补口播文案。关掉则回落静音占位
    ai_copy: bool | None = None
    # BGM 音量百分比。0 = 不加 BGM，默认 config.BGM_VOLUME
    bgm_volume: float | None = None


class Job:
    """一个后台任务。事件同时进队列（给 SSE）和列表（给轮询/补看）。

    `target(on_event, should_stop) -> dict` 由构造方给 —— 渲染和「批量生成
    文案」两条流程共用这一套进度/停止/SSE 机制，不各写一份。
    """

    def __init__(self, req=None, target=None, kind="render"):
        self.id = uuid.uuid4().hex[:12]
        self.req = req
        self.kind = kind
        self.status = "running"
        self.events = []
        self.queue = queue.Queue()
        self.result = None
        self.error = None
        self._stop = threading.Event()
        self.created = time.time()
        self._target = target or self._render

    def on_event(self, ev):
        ev["at"] = round(time.time() - self.created, 1)
        self.events.append(ev)
        self.queue.put(ev)

    def should_stop(self):
        return self._stop.is_set()

    def stop(self):
        self._stop.set()

    def _render(self, on_event, should_stop):
        return pipeline.run(
            source=self.req.source, points=self.req.points,
            hook_limit=self.req.hook_limit, limit=self.req.limit,
            seed=self.req.seed, out_dir=self.req.out_dir,
            bgm_dir=self.req.bgm_dir, sub_size=self.req.sub_size,
            dedup=self.req.dedup, speed=self.req.speed,
            ai_copy=self.req.ai_copy, bgm_volume=self.req.bgm_volume,
            on_event=on_event, should_stop=should_stop)

    def run(self):
        try:
            self.result = self._target(self.on_event, self.should_stop)
            self.status = "stopped" if self._stop.is_set() else "done"
        except (RuntimeError, OSError, ValueError) as e:
            self.error = str(e)
            self.status = "error"
            self.queue.put({"type": "error", "error": str(e)})
        finally:
            self.queue.put(None)  # SSE 结束哨兵

    def snapshot(self):
        return {"id": self.id, "kind": self.kind, "status": self.status,
                "events": self.events, "result": self.result,
                "error": self.error}


JOBS: dict[str, Job] = {}


@app.get("/api/health")
def health():
    """环境自检。前端用它决定要不要提示缺东西。"""
    backend_ready = config.TTS_BACKEND == "stub" or all(
        [config.VOLCANO_APPID, config.VOLCANO_TOKEN, config.VOLCANO_VOICE])
    layers = config.bgm_layers()
    tracks = config.list_bgm()
    return {
        "ffmpeg": os.path.isfile(config.FFMPEG) or bool(config.FFMPEG),
        "font": os.path.isfile(config.FONT_PATH),
        "model": os.path.isdir(config.MODEL_DIR),
        "tts_backend": config.TTS_BACKEND,
        "tts_ready": backend_ready,
        # 总数保留 —— HealthBar 在用。分层明细在 bgm 里。
        "bgm_count": len(tracks),
        "bgm": {
            "builtin": sum(1 for _p, t in tracks if t == "builtin"),
            "custom": sum(1 for _p, t in tracks if t == "custom"),
            "builtin_dir": layers[0][0],
            "custom_dir": config.BGM_DIR,
        },
        "source_dir": config.SOURCE_DIR,
        "output_dir": config.OUTPUT_DIR,
        "defaults": {"points": config.POINT_COUNT,
                     "hook_limit": config.HOOK_USE_LIMIT,
                     "sub_size": config.SUBTITLE_SIZE,
                     "speed": config.PLAYBACK_SPEED,
                     "bgm_volume": config.BGM_VOLUME},
    }


@app.post("/api/scan")
def scan(req: ScanReq):
    src = req.source or config.SOURCE_DIR
    if not os.path.isdir(src):
        raise HTTPException(400, f"目录不存在: {src}")
    try:
        _pools, stats = pipeline.scan(src)
    except (OSError, ValueError) as e:
        raise HTTPException(400, str(e)) from e
    return stats


@app.post("/api/preview")
def preview(req: PreviewReq):
    import combo

    src = req.source or config.SOURCE_DIR
    if not os.path.isdir(src):
        raise HTTPException(400, f"目录不存在: {src}")
    pools, stats = pipeline.scan(src)
    theme_map, theme_note = pipeline.build_theme_map(pools, req.dedup)
    try:
        combos = combo.build_combos(
            pools,
            point_count=req.points if req.points is not None
            else config.POINT_COUNT,
            hook_limit=req.hook_limit if req.hook_limit is not None
            else config.HOOK_USE_LIMIT,
            seed=req.seed, theme_map=theme_map)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if req.limit:
        combos = combos[:req.limit]
    return {
        "stats": stats,
        "total": len(combos),
        "theme_note": theme_note,
        "themes": len(set(theme_map.values())) if theme_map else 0,
        "combos": [{
            "index": c.index,
            "hook": c.hook.label,
            "points": [p.label for p in c.points],
            "ending": c.ending.label,
        } for c in combos],
    }


@app.post("/api/jobs")
def create_job(req: JobReq):
    src = req.source or config.SOURCE_DIR
    if not os.path.isdir(src):
        raise HTTPException(400, f"目录不存在: {src}")
    if any(j.status == "running" for j in JOBS.values()):
        raise HTTPException(409, "已有任务在跑，请等它结束或先停止")
    job = Job(req)
    JOBS[job.id] = job
    threading.Thread(target=job.run, daemon=True).start()
    return {"id": job.id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return job.snapshot()


@app.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    job.stop()
    return {"ok": True, "note": "当前这条渲染完成后停止"}


@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: str):
    """SSE 推进度。断线重连时会重发已有事件，前端按 index 去重即可。"""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")

    def gen():
        import json
        # 补发历史。记下已发数量，避免队列里同一批事件再发一次。
        sent = 0
        for ev in list(job.events):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            sent += 1
        if job.status != "running":
            yield "data: {\"type\":\"eof\"}\n\n"
            return
        while True:
            ev = job.queue.get()
            if ev is None:
                yield "data: {\"type\":\"eof\"}\n\n"
                return
            # 已在补发阶段发过的跳过
            if sent > 0:
                sent -= 1
                continue
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/outputs")
def outputs(out_dir: str | None = None):
    d = out_dir or config.OUTPUT_DIR
    if not os.path.isdir(d):
        return {"dir": d, "files": []}
    # 组合明细取自渲染时落盘的清单，不按序号去对当次预览结果 ——
    # 预览不传 seed 会重新随机，序号对不上当初渲的那条【实测】。
    manifest = pipeline.read_manifest(d)
    files = []
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith(".mp4"):
            continue
        p = os.path.join(d, f)
        st = os.stat(p)
        files.append({"name": f, "size_mb": round(st.st_size / 1e6, 1),
                      "mtime": int(st.st_mtime),
                      # 旧成品没有记录，返回 null，界面显示"不可用"而不是猜
                      "combo": manifest.get(f)})
    return {"dir": d, "files": files}


def _safe_output_file(name: str, out_dir: str | None):
    """把前端给的文件名解析成输出目录下的真实路径。

    只允许输出目录直属的 .mp4，挡掉 ../ 穿越和绝对路径 ——
    这服务虽然只听 127.0.0.1，但浏览器里任何页面都能发请求到本机端口，
    不能让它读到磁盘上任意文件。
    """
    d = os.path.realpath(out_dir or config.OUTPUT_DIR)
    if not name.lower().endswith(".mp4"):
        raise HTTPException(400, "只支持 mp4")
    # basename 掉掉所有路径成分，再 realpath 兜住软链接
    p = os.path.realpath(os.path.join(d, os.path.basename(name)))
    if os.path.dirname(p) != d:
        raise HTTPException(400, "非法路径")
    if not os.path.isfile(p):
        raise HTTPException(404, "文件不存在")
    return p


@app.get("/api/video")
def video(name: str, out_dir: str | None = None):
    """回放成品。Starlette 的 FileResponse 原生处理 Range 并返回 206，
    所以 <video> 拖进度条能直接 seek，不用自己切分片【实测源码确认】。
    """
    p = _safe_output_file(name, out_dir)
    return FileResponse(p, media_type="video/mp4",
                        content_disposition_type="inline")


@app.post("/api/outputs/delete")
def delete_output(name: str, out_dir: str | None = None):
    """删掉一条成品。组合质量不合意时在界面上直接清掉。"""
    p = _safe_output_file(name, out_dir)
    os.remove(p)
    pipeline.prune_manifest(os.path.dirname(p), os.path.basename(p))
    return {"ok": True, "name": os.path.basename(p)}


@app.post("/api/open-output")
def open_output(out_dir: str | None = None):
    d = out_dir or config.OUTPUT_DIR
    os.makedirs(d, exist_ok=True)
    subprocess.Popen(["explorer", os.path.normpath(d)])
    return {"ok": True, "dir": d}


class PickReq(BaseModel):
    title: str = "选择文件夹"
    initial: str | None = None


def _run_launcher(*args, timeout=300):
    """在独立进程里跑 `launcher.py` 的一个子命令，返回 stdout。

    **必须走 `sys.executable`**，不准硬编码 `"python"`：办公机不装 Python，
    写死必然失败。冻结态 `sys.executable` 是 Ave.exe，直接加子命令
    （exe 不认 `-c`）；源码态是 python.exe，走 `-m ave.launcher`。

    对话框跑在独立进程里 —— 直接在服务进程内起 tkinter 会和 uvicorn 的
    事件循环打架，且 tkinter 要求在主线程创建窗口。
    """
    argv = [sys.executable]
    if not getattr(sys, "frozen", False):
        argv += ["-m", "ave.launcher"]
    argv += [str(a) for a in args]
    try:
        r = subprocess.run(argv, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           cwd=os.path.dirname(os.path.dirname(
                               os.path.abspath(__file__))))
    except subprocess.TimeoutExpired:
        raise HTTPException(408, "选择超时") from None
    if r.returncode != 0:
        raise HTTPException(500, f"打开选择框失败: {r.stderr[-200:]}")
    return r.stdout


@app.post("/api/pick-dir")
def pick_dir(req: PickReq):
    """弹 Windows 原生目录选择框，返回选中的绝对路径。

    浏览器的 <input type="file"> 出于安全限制拿不到真实目录路径，
    所以必须由后端弹系统对话框。用户取消时返回 path=null。
    """
    out = _run_launcher("--pick-dir", req.title,
                        req.initial or os.path.expanduser("~"))
    path = out.strip()
    return {"path": os.path.normpath(path) if path else None}


# ---------------- BGM 两层管理 ----------------
# 内置层随应用更新替换（我们维护），自定义层在用户数据目录（各公司自己加）。
# 只有自定义层可增删 —— 内置层是随包授权的曲子，删了下次更新还会回来。


def _bgm_custom_dir(custom: str | None):
    return os.path.realpath(custom or config.BGM_DIR)


@app.get("/api/bgm")
def bgm_list(custom_dir: str | None = None):
    layers = config.bgm_layers(custom_dir)
    tracks = []
    for p, tag in config.list_bgm(custom_dir):
        st = os.stat(p)
        tracks.append({"name": os.path.basename(p), "source": tag,
                       "size_mb": round(st.st_size / 1e6, 2)})
    return {
        "builtin_dir": layers[0][0],
        "custom_dir": _bgm_custom_dir(custom_dir),
        "tracks": tracks,
    }


@app.post("/api/bgm/add")
def bgm_add(custom_dir: str | None = None):
    """弹原生多选文件框，把选中的音频拷进自定义层。

    走系统对话框而不是 HTTP 上传：浏览器拿不到真实路径，而上传要引入
    `python-multipart`（当前未装）。取消时返回 added=[]。
    """
    out = _run_launcher("--pick-files", "选择要添加的 BGM 音频",
                        os.path.expanduser("~"), "audio")
    picked = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if not picked:
        return {"added": [], "skipped": []}

    dst_dir = _bgm_custom_dir(custom_dir)
    os.makedirs(dst_dir, exist_ok=True)
    added, skipped = [], []
    for src in picked:
        name = os.path.basename(src)
        if os.path.splitext(name)[1].lower() not in config.BGM_EXTS:
            skipped.append({"name": name, "why": "不是支持的音频格式"})
            continue
        if not os.path.isfile(src):
            skipped.append({"name": name, "why": "文件不存在"})
            continue
        dst = os.path.join(dst_dir, name)
        # 同名不覆盖 —— 加序号。覆盖会静默弄丢已在用的曲子。
        stem, ext = os.path.splitext(name)
        k = 2
        while os.path.exists(dst):
            name = f"{stem}-{k}{ext}"
            dst = os.path.join(dst_dir, name)
            k += 1
        try:
            shutil.copy2(src, dst)
        except OSError as e:
            skipped.append({"name": name, "why": str(e)[:120]})
            continue
        added.append(name)
    return {"added": added, "skipped": skipped}


@app.post("/api/bgm/delete")
def bgm_delete(name: str, custom_dir: str | None = None):
    """删一首自定义层的 BGM。内置层拒绝删除。

    路径校验与 `_safe_output_file()` 同一套：basename 掉掉路径成分，
    realpath 兜住软链接，再比对父目录 —— 服务虽只听 127.0.0.1，
    但浏览器里任何页面都能往本机端口发请求。
    """
    base = os.path.basename(name)
    d = _bgm_custom_dir(custom_dir)
    p = os.path.realpath(os.path.join(d, base))
    if os.path.dirname(p) != d:
        raise HTTPException(400, "非法路径")
    if os.path.splitext(p)[1].lower() not in config.BGM_EXTS:
        raise HTTPException(400, "只支持音频文件")
    if not os.path.isfile(p):
        # 内置层同名文件存在时给出针对性说明，而不是干巴巴的「不存在」
        builtin = config.bgm_layers(custom_dir)[0][0]
        if os.path.isfile(os.path.join(builtin, base)):
            raise HTTPException(
                400, f"「{base}」是内置 BGM，不能删除 —— "
                     f"它随应用更新提供，删掉下次更新还会回来。")
        raise HTTPException(404, "文件不存在")
    os.remove(p)
    return {"ok": True, "name": base}


# ---------------- AI 口播文案 ----------------
# 无口播的片段（幻觉闸门拦下的静音片）交给视觉模型写文案，
# 走的还是原来那条 TTS + 字幕链路。人工可在界面上审校。


class CopyReq(BaseModel):
    source: str | None = None


class CopySaveReq(BaseModel):
    path: str
    text: str
    source: str | None = None      # 素材根目录，用于路径校验


def _clips_of(source):
    """扫素材，返回全部片段（钩子 + 卖点 + 结尾）。"""
    import combo
    src = source or config.SOURCE_DIR
    if not os.path.isdir(src):
        raise HTTPException(400, f"目录不存在: {src}")
    pools = combo.scan_product(src)
    return src, list(pools.hooks) + list(pools.points) + list(pools.endings)


def _check_inside(path, root):
    """确认 path 落在 root 内。挡掉 ../ 穿越和任意绝对路径 ——
    服务只听 127.0.0.1，但浏览器里任何页面都能往本机端口发请求。"""
    r = os.path.realpath(root)
    p = os.path.realpath(path)
    if not (p == r or p.startswith(r + os.sep)):
        raise HTTPException(400, "非法路径")
    return p


@app.post("/api/copy/list")
def copy_list(req: CopyReq):
    """列出每个片段的口播状态与 AI 文案。**只读缓存，不发任何 API 请求。**

    `asr` 三态：True 有口播 / False 已识别但无口播 / None 还没识别过。
    界面据此区分「确认无口播」和「状态未知」，不猜。
    """
    src, clips = _clips_of(req.source)
    store = pipeline.CopyStore()
    asr_cache = {}
    if os.path.isfile(config.ASR_CACHE):
        try:
            import json as _json
            with open(config.ASR_CACHE, encoding="utf-8") as f:
                asr_cache = _json.load(f)
        except (OSError, ValueError):
            asr_cache = {}

    items = []
    for c in clips:
        try:
            key = pipeline.CopyStore.key(c.path)
        except OSError:
            continue
        r = asr_cache.get(key)
        has_asr = None if r is None else bool(r.get("segments"))
        rec = store.get(c.path) or {}
        items.append({
            "path": c.path,
            "name": c.name,
            "role": c.role,
            "label": c.label,
            "asr": has_asr,
            "speech_ratio": (r or {}).get("speech_ratio"),
            "copy": rec.get("text", ""),
            "copy_source": rec.get("source", ""),
        })
    return {
        "source": src,
        "vision_backend": config.VISION_BACKEND,
        "vision_model": config.ARK_VISION_MODEL,
        "vision_models": list(config.ARK_VISION_MODELS),
        "items": items,
    }


@app.post("/api/copy/save")
def copy_save(req: CopySaveReq):
    """存人工修改的文案，标记成 'edited' —— 之后重新生成不会覆盖它。

    文本清空则删掉该条（回落成「无口播就静音占位」）。
    """
    root = req.source or config.SOURCE_DIR
    p = _check_inside(req.path, root)
    if not os.path.isfile(p):
        raise HTTPException(404, "片段不存在")
    store = pipeline.CopyStore()
    text = (req.text or "").strip()
    if text:
        store.put(p, text, source="edited")
    else:
        store._data.pop(pipeline.CopyStore.key(p), None)
    store.save()
    return {"ok": True, "text": text, "copy_source": "edited" if text else ""}


@app.post("/api/copy/generate")
def copy_generate(req: CopyReq):
    """批量给无口播片段生成文案。走 Job/SSE，进度条和停止按钮复用渲染那套。"""
    if config.VISION_BACKEND == "stub":
        raise HTTPException(
            400, "未配置 ARK_API_KEY，无法生成 AI 文案。"
                 "见 docs/资源需求清单.md 的方舟开通步骤。")
    if any(j.status == "running" for j in JOBS.values()):
        raise HTTPException(409, "已有任务在跑，请等它结束或先停止")

    src, clips = _clips_of(req.source)

    def target(on_event, should_stop):
        from ave import asr as _asr
        from ave import tts as _tts
        store = pipeline.CopyStore()
        backend = vision.make_backend()
        rec = _asr.Recognizer(config.MODEL_DIR, config.FFMPEG,
                              config.ASR_CACHE)
        os.makedirs(config.WORK_DIR, exist_ok=True)
        total = len(clips)
        on_event({"type": "start", "total": total,
                  "vision_backend": backend.name})
        made = skipped = failed = 0
        for i, c in enumerate(clips, 1):
            if should_stop():
                on_event({"type": "stopped", "done": i - 1, "total": total})
                break
            ev = {"type": "item", "index": i, "total": total, "file": c.name}
            try:
                r = rec.recognize(c.path, config.WORK_DIR)
                if r.get("segments"):
                    skipped += 1
                    ev.update(ok=True, action="有口播，跳过")
                else:
                    dur = _tts.probe_duration(c.path, config.FFMPEG)
                    txt, fresh = store.make(
                        c, dur / config.PLAYBACK_SPEED, backend)
                    if txt and fresh:
                        made += 1
                        ev.update(ok=True, action="已生成", copy=txt)
                    elif txt:
                        skipped += 1
                        ev.update(ok=True, action="已有文案，跳过", copy=txt)
                    else:
                        failed += 1
                        ev.update(ok=False, error="模型未返回文案")
            except (RuntimeError, OSError) as e:
                failed += 1
                ev.update(ok=False, error=str(e)[:300])
            on_event(ev)
        result = {"total": total, "made": made, "skipped": skipped,
                  "failed": failed, "source": src}
        on_event({"type": "done", **result})
        return result

    job = Job(target=target, kind="copy")
    JOBS[job.id] = job
    threading.Thread(target=job.run, daemon=True).start()
    return {"id": job.id}


class ExportReq(BaseModel):
    # 整体倍速。1.0 = 原样拷贝（仍会重编码，但不变速）
    speed: float = 1.2
    # 要导出哪些成品。None/空 = 全部
    names: list[str] | None = None
    out_dir: str | None = None
    # 导出落在 out_dir 下的子目录，默认按倍速命名
    sub_dir: str | None = None


@app.post("/api/export")
def export_outputs(req: ExportReq):
    """把已渲好的成品整条变速后导出到子目录。

    用户 2026-08-26 定：「整个视频出来之后，再过一遍前端的倍速，然后再导出」。
    **不覆盖原片** —— 落 `out_dir/导出_1.2x/`，改倍速不用重渲
    （全量重渲要 9 分钟，变速一条只要 1.4 秒）。

    走 Job/SSE，进度条和停止按钮复用渲染那套。
    """
    if not 0.5 <= req.speed <= 2.0:
        raise HTTPException(
            400, f"倍速 {req.speed} 超出范围 —— atempo 单实例只接受 0.5~2.0")
    if any(j.status == "running" for j in JOBS.values()):
        raise HTTPException(409, "已有任务在跑，请等它结束或先停止")

    src_dir = os.path.realpath(req.out_dir or config.OUTPUT_DIR)
    if not os.path.isdir(src_dir):
        raise HTTPException(400, f"目录不存在: {src_dir}")

    # 挑要导的文件。逐个走 _safe_output_file 把路径限死在输出目录内。
    if req.names:
        picked = [_safe_output_file(n, src_dir) for n in req.names]
    else:
        picked = [os.path.join(src_dir, f) for f in sorted(os.listdir(src_dir))
                  if f.lower().endswith(".mp4")]
    if not picked:
        raise HTTPException(400, "没有可导出的成品")

    sub = req.sub_dir or f"导出_{req.speed:g}x"
    # 子目录名不许带路径成分，否则能写到输出目录外面去
    if os.path.basename(sub) != sub or sub in (".", ".."):
        raise HTTPException(400, "子目录名不合法")
    dst_dir = os.path.join(src_dir, sub)

    def target(on_event, should_stop):
        import shutil as _sh
        from ave import render as _r
        os.makedirs(dst_dir, exist_ok=True)
        enc = _r.pick_encoder(config.FFMPEG)
        total = len(picked)
        on_event({"type": "start", "total": total, "speed": req.speed,
                  "out_dir": dst_dir, "encoder": enc})
        ok = failed = 0
        for i, src in enumerate(picked, 1):
            if should_stop():
                on_event({"type": "stopped", "done": ok, "total": total})
                break
            name = os.path.basename(src)
            dst = os.path.join(dst_dir, name)
            ev = {"type": "item", "index": i, "total": total, "file": name}
            t0 = time.time()
            try:
                if abs(req.speed - 1.0) < 0.001:
                    _sh.copy2(src, dst)     # 1.0 不重编码，直接拷
                else:
                    _r.respeed(src, dst, req.speed, config.FFMPEG, encoder=enc)
                ok += 1
                ev.update(ok=True,
                          size_mb=round(os.path.getsize(dst) / 1e6, 1),
                          seconds=round(time.time() - t0, 1))
            except (RuntimeError, OSError) as e:
                failed += 1
                ev.update(ok=False, error=str(e)[:300])
            on_event(ev)

        # 清单一并拷过去，成品的组合明细在导出目录里也查得到
        try:
            items = pipeline.read_manifest(src_dir)
            keep = {os.path.basename(p): items[os.path.basename(p)]
                    for p in picked if os.path.basename(p) in items}
            if keep:
                for v in keep.values():
                    v["export_speed"] = req.speed
                mp = pipeline.manifest_path(dst_dir)
                tmp = mp + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    import json as _j
                    _j.dump({"version": 1, "items": keep}, f,
                            ensure_ascii=False, indent=1)
                os.replace(tmp, mp)
        except (OSError, ValueError):
            pass    # 清单拷不过去不该让导出算失败

        result = {"ok": ok, "failed": failed, "total": total,
                  "speed": req.speed, "out_dir": dst_dir}
        on_event({"type": "done", **result})
        return result

    job = Job(target=target, kind="export")
    JOBS[job.id] = job
    threading.Thread(target=job.run, daemon=True).start()
    return {"id": job.id, "out_dir": dst_dir, "total": len(picked)}


@app.post("/api/vision/test")
def vision_test(req: CopyReq):
    """视觉接口自检。**真发一次请求** —— 只看 Key 非空说明不了任何事。

    抽一帧真图去问，把方舟返回的错误原文透传出来：模型 ID 不对时
    它会直接说该用什么，改 credentials.json 即可，不用改代码。
    """
    backend = vision.make_backend()
    if backend.name == "stub":
        return {"ok": False, "backend": "stub", "error": backend.note}

    frames = []
    try:
        _src, clips = _clips_of(req.source)
        if clips:
            frames = vision.extract_frames(
                clips[0].path, os.path.join(config.WORK_DIR, "frames"),
                config.FFMPEG, n=1)
    except HTTPException:
        pass    # 素材目录不可用也要能测通连通性，退化成纯文本探测

    r = backend.ping(frames)
    for f in frames:
        try:
            os.remove(f)
        except OSError:
            pass
    r["backend"] = backend.name
    r["with_image"] = bool(frames)
    return r


# ---------------- 前端静态文件 ----------------
# ⚠️ **必须放在所有 API 路由定义之后**。挂在 "/" 上的 StaticFiles 会吞掉
# 它之后注册的同前缀路由 —— 写在上面会把 /api/* 全遮蔽掉。
# 开发期没有 web/ 目录就跳过，vite 的 5173 流程不受影响。
_WEB_DIR = config._resource("web")
if os.path.isdir(_WEB_DIR):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8756, log_level="info")


if __name__ == "__main__":
    main()
