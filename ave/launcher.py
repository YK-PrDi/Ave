"""exe 入口。冻结态双击 Ave.exe 走这里，源码态用 `python -m ave.launcher`。

    python -m ave.launcher                                # 起服务 + 开浏览器
    python -m ave.launcher --pick-dir "标题" "初始目录"    # 弹目录选择框
    python -m ave.launcher --pick-files "标题" "初始目录"  # 弹多选文件框
    python -m ave.launcher --no-browser                   # 只起服务

`--pick-dir` / `--pick-files` 是 `server.py` 的依赖，必须作为 exe 的真实子命令
存在 —— 冻结后的 exe 不接受 `python -c "<代码>"` 那种调法。
"""

import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser

PORT = 8756
HEALTH = f"http://127.0.0.1:{PORT}/api/health"


def pick_dir(title="选择文件夹", initial=""):
    """弹 Windows 原生目录选择框，把选中的路径打印到 stdout。

    独立进程里跑 —— 直接在服务进程内起 tkinter 会和 uvicorn 的事件循环
    打架，且 tkinter 要求在主线程创建窗口。用户取消时打印空行。
    """
    import os
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askdirectory(
        title=title, initialdir=initial or os.path.expanduser("~"))
    root.destroy()
    print(path or "")
    return 0


def pick_files(title="选择文件", initial="", kind="audio"):
    """弹原生多选文件框，选中的路径逐行打到 stdout。

    和 `pick_dir` 同一套理由：浏览器拿不到真实文件路径，而走 HTTP 上传
    要引入 `python-multipart`（当前未装）。取消时不打任何行。

    ⚠️ 已知边界：这条路依赖对话框弹在**服务所在的那台机器**上。
    接入羽刃后若变成非本机访问，得改成真正的上传通道。
    """
    import os
    import tkinter as tk
    from tkinter import filedialog

    types = {
        "audio": [("音频文件", "*.mp3 *.wav *.m4a *.aac *.flac"),
                  ("所有文件", "*.*")],
    }.get(kind, [("所有文件", "*.*")])

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    paths = filedialog.askopenfilenames(
        title=title, initialdir=initial or os.path.expanduser("~"),
        filetypes=types)
    root.destroy()
    for p in paths or ():
        print(p)
    return 0


def port_busy(port=PORT):
    """端口是否被占。连得上就说明有人在听。"""
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def free_port_or_kill(port=PORT):
    """占端口的进程先杀掉，沿用 `启动.bat` 的逻辑。

    ⚠️ 源码态（IDEA）和打包版 exe 不要同时开 —— 这函数会直接杀掉
    占端口的那个进程，不问是谁的。
    """
    if not port_busy(port):
        return []
    killed = []
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True,
                             text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return killed
    for line in out.splitlines():
        if f":{port}" in line and "LISTENING" in line.upper():
            pid = line.split()[-1]
            if pid.isdigit() and pid != "0":
                subprocess.run(["taskkill", "/F", "/PID", pid],
                               capture_output=True, timeout=20)
                killed.append(pid)
    if killed:
        time.sleep(1.0)   # 等系统真正释放端口，否则 bind 还会失败
    return killed


def ensure_model():
    """模型不在就下载到用户数据目录。已在就直接返回。

    落用户数据目录而不是应用目录 —— 更新应用时不该冲掉 1.5G 模型
    （用户 2026-08-15 决定）。
    """
    from ave import config
    # 判据是 model.bin 在不在，不是「目录非空」【实测踩过】：
    # 下载中断会留下有 config.json / tokenizer.json 但没 model.bin 的
    # 半截目录，按「非空」算就跳过下载，之后加载才报 model.bin 打不开。
    if os.path.isfile(os.path.join(config.MODEL_DIR, "model.bin")):
        return config.MODEL_DIR

    target = os.path.join(config._USER_DIR, "models", config.MODEL_NAME)
    print(f"首次运行需下载语音识别模型（约 1.5G）到:\n  {target}")
    print("这一步只做一次，之后更新应用不会重下。请保持网络畅通…")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id="Systran/faster-whisper-medium",
                      local_dir=target)
    print("模型下载完成。")
    return target


def wait_ready(timeout=60):
    """轮询 /api/health 直到服务起来。返回是否就绪。"""
    import urllib.error
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH, timeout=2) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    return False


def serve(open_browser=True):
    """起 uvicorn，就绪后开浏览器。阻塞直到服务退出。"""
    from ave import config, server

    killed = free_port_or_kill()
    if killed:
        print(f"端口 {PORT} 被占用，已清理进程 {', '.join(killed)}")

    ensure_model()
    os.makedirs(config._USER_DIR, exist_ok=True)

    if open_browser:
        def opener():
            if wait_ready():
                webbrowser.open(f"http://127.0.0.1:{PORT}/")
            else:
                print(f"服务迟迟没就绪，请手动打开 http://127.0.0.1:{PORT}/")
        threading.Thread(target=opener, daemon=True).start()

    print(f"Ave 混剪工具已启动: http://127.0.0.1:{PORT}/")
    print("关掉这个窗口即停止服务。")
    import uvicorn
    uvicorn.run(server.app, host="127.0.0.1", port=PORT, log_level="warning")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # stdout 要能编中文路径。Windows 控制台/管道默认 GBK。
    # line_buffering：输出重定向到文件时 Python 会块缓冲，
    # 「已启动」那行要等缓冲满才出现，看起来像卡住了【实测】。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace",
                               line_buffering=True)

    if argv and argv[0] == "--pick-dir":
        return pick_dir(*argv[1:3])
    if argv and argv[0] == "--pick-files":
        return pick_files(*argv[1:4])
    if argv and argv[0] not in ("--no-browser",):
        print(f"未知参数: {argv[0]}\n"
              "用法: [--no-browser] | --pick-dir [标题] [初始目录]\n"
              "      | --pick-files [标题] [初始目录] [类型]",
              file=sys.stderr)
        return 2
    return serve(open_browser="--no-browser" not in argv)


if __name__ == "__main__":
    sys.exit(main())
