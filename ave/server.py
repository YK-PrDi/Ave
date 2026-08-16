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

只监听 127.0.0.1，不对外暴露。这是本机工具，不做鉴权。
"""

import os
import queue
import subprocess
import sys
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from ave import config, pipeline

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


class Job:
    """一个渲染任务。事件同时进队列（给 SSE）和列表（给轮询/补看）。"""

    def __init__(self, req: JobReq):
        self.id = uuid.uuid4().hex[:12]
        self.req = req
        self.status = "running"
        self.events = []
        self.queue = queue.Queue()
        self.result = None
        self.error = None
        self._stop = threading.Event()
        self.created = time.time()

    def on_event(self, ev):
        ev["at"] = round(time.time() - self.created, 1)
        self.events.append(ev)
        self.queue.put(ev)

    def should_stop(self):
        return self._stop.is_set()

    def stop(self):
        self._stop.set()

    def run(self):
        try:
            self.result = pipeline.run(
                source=self.req.source, points=self.req.points,
                hook_limit=self.req.hook_limit, limit=self.req.limit,
                seed=self.req.seed, out_dir=self.req.out_dir,
                bgm_dir=self.req.bgm_dir, sub_size=self.req.sub_size,
                dedup=self.req.dedup,
                on_event=self.on_event, should_stop=self.should_stop)
            self.status = "stopped" if self._stop.is_set() else "done"
        except (RuntimeError, OSError, ValueError) as e:
            self.error = str(e)
            self.status = "error"
            self.queue.put({"type": "error", "error": str(e)})
        finally:
            self.queue.put(None)  # SSE 结束哨兵

    def snapshot(self):
        return {"id": self.id, "status": self.status, "events": self.events,
                "result": self.result, "error": self.error}


JOBS: dict[str, Job] = {}


@app.get("/api/health")
def health():
    """环境自检。前端用它决定要不要提示缺东西。"""
    backend_ready = config.TTS_BACKEND == "stub" or all(
        [config.VOLCANO_APPID, config.VOLCANO_TOKEN, config.VOLCANO_VOICE])
    bgm_count = 0
    if os.path.isdir(config.BGM_DIR):
        bgm_count = len([f for f in os.listdir(config.BGM_DIR)
                         if os.path.splitext(f)[1].lower() in
                         (".mp3", ".wav", ".m4a", ".aac", ".flac")])
    return {
        "ffmpeg": os.path.isfile(config.FFMPEG) or bool(config.FFMPEG),
        "font": os.path.isfile(config.FONT_PATH),
        "model": os.path.isdir(config.MODEL_DIR),
        "tts_backend": config.TTS_BACKEND,
        "tts_ready": backend_ready,
        "bgm_count": bgm_count,
        "source_dir": config.SOURCE_DIR,
        "output_dir": config.OUTPUT_DIR,
        "defaults": {"points": config.POINT_COUNT,
                     "hook_limit": config.HOOK_USE_LIMIT,
                     "sub_size": config.SUBTITLE_SIZE},
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


@app.post("/api/pick-dir")
def pick_dir(req: PickReq):
    """弹 Windows 原生目录选择框，返回选中的绝对路径。

    浏览器的 <input type="file"> 出于安全限制拿不到真实目录路径，
    所以必须由后端弹系统对话框。用户取消时返回 path=null。

    对话框跑在独立进程里 —— 直接在服务进程内起 tkinter 会和
    uvicorn 的事件循环打架，且 tkinter 要求在主线程创建窗口。

    **子进程必须走 `sys.executable`**，不准硬编码 `"python"`：
    办公机不装 Python，写死 `python` 这按钮必然失败。
    冻结态 `sys.executable` 是 Ave.exe，直接加 `--pick-dir`（exe 不认 `-c`）；
    源码态是 python.exe，调 `-m ave.launcher --pick-dir`。
    """
    argv = [sys.executable]
    if not getattr(sys, "frozen", False):
        argv += ["-m", "ave.launcher"]
    argv += ["--pick-dir", req.title, req.initial or os.path.expanduser("~")]
    try:
        r = subprocess.run(argv, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300,
                           cwd=os.path.dirname(os.path.dirname(
                               os.path.abspath(__file__))))
    except subprocess.TimeoutExpired:
        raise HTTPException(408, "选择超时") from None
    if r.returncode != 0:
        raise HTTPException(500, f"打开选择框失败: {r.stderr[-200:]}")
    path = r.stdout.strip()
    return {"path": os.path.normpath(path) if path else None}


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
