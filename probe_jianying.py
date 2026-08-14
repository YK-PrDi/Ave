"""剪映功能探测脚本 —— 回答三个阻塞架构的未验证问题

用法（跟着提示做，全程只用 2 个片段，不是 55 个）：

    python probe_jianying.py guide     # 看操作步骤
    python probe_jianying.py snap A    # 操作前拍快照
    python probe_jianying.py snap B    # 操作后拍快照
    python probe_jianying.py diff A B  # 看多出了什么文件
    python probe_jianying.py silence <wav路径>   # 验静音检测能否切片

要回答的问题：
  1. 人声分离后还能不能用口播换音色（若互斥，需求要改）
  2. 换音色能不能全选批量应用
  3. 换音色的产物文件落在哪个目录
"""

import json
import os
import subprocess
import sys
import time

FFMPEG = r"D:\Tool\JianyingPro\11.2.0.14339\ffmpeg.exe"
LOCALAPP = os.environ.get("LOCALAPPDATA", "")
JY_USERDATA = os.path.join(LOCALAPP, "JianyingPro", "User Data")
DRAFT_ROOT = r"D:\Tool\JianyingPro Drafts"
SNAP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".probe")

# 监视这些目录 —— 换音色/人声分离/音乐库的产物可能落在任一处
WATCH = [
    DRAFT_ROOT,
    os.path.join(JY_USERDATA, "Cache"),
    os.path.join(JY_USERDATA, "EMaterial"),
    os.path.join(JY_USERDATA, "Download"),
]

AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".pcm", ".ogg", ".dat", ".opus"}


def scan():
    """记录路径 -> (大小, 修改时间)。不算 hash，省时间。"""
    out = {}
    for root in WATCH:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in filenames:
                p = os.path.join(dirpath, fn)
                try:
                    st = os.stat(p)
                    out[p] = (st.st_size, int(st.st_mtime))
                except OSError:
                    pass
    return out


def human(n):
    for unit in ("B", "K", "M", "G"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}T"


def cmd_snap(tag):
    os.makedirs(SNAP_DIR, exist_ok=True)
    data = scan()
    path = os.path.join(SNAP_DIR, f"snap_{tag}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"快照 {tag}: {len(data)} 个文件 -> {path}")


def cmd_diff(tag_a, tag_b):
    def load(t):
        with open(os.path.join(SNAP_DIR, f"snap_{t}.json"), encoding="utf-8") as f:
            return json.load(f)

    try:
        a, b = load(tag_a), load(tag_b)
    except FileNotFoundError as e:
        print(f"缺快照: {e}")
        return

    new = [p for p in b if p not in a]
    changed = [p for p in b if p in a and a[p] != b[p]]

    print(f"\n=== 新增 {len(new)} 个文件 ===")
    audio_new = [p for p in new if os.path.splitext(p)[1].lower() in AUDIO_EXT]
    other_new = [p for p in new if p not in audio_new]

    if audio_new:
        print(f"\n--- 音频类 {len(audio_new)} 个（重点看这些）---")
        for p in sorted(audio_new, key=lambda x: -b[x][0])[:40]:
            print(f"  {human(b[p][0]):>6}  {p}")
    else:
        print("  (无新音频文件)")

    if other_new:
        print(f"\n--- 其他 {len(other_new)} 个（只列前 25）---")
        for p in sorted(other_new, key=lambda x: -b[x][0])[:25]:
            print(f"  {human(b[p][0]):>6}  {p}")

    print(f"\n=== 内容变化 {len(changed)} 个（只列前 20）===")
    for p in changed[:20]:
        print(f"  {human(a[p][0])} -> {human(b[p][0])}  {p}")

    # audioAlg 是已知的人声分离产物目录，单独盯一下
    alg = [p for p in list(b) if "audioAlg" in p]
    print(f"\n=== audioAlg 目录下 {len(alg)} 个文件 ===")
    for p in alg[:20]:
        print(f"  {human(b[p][0]):>6}  {p}")


def cmd_silence(wav):
    """验证能否靠静音间隙把长音频切回单片段。"""
    if not os.path.isfile(wav):
        print(f"文件不存在: {wav}")
        return
    print(f"检测静音: {wav}\n")
    r = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", wav,
         "-af", "silencedetect=noise=-40dB:d=0.4", "-f", "null", "-"],
        capture_output=True, text=True, errors="ignore",
    )
    marks = [l.strip() for l in r.stderr.splitlines() if "silence_" in l]
    if not marks:
        print("没检测到静音段。可能是：间隙没留够、阈值要调、或导出时被压缩了。")
        print("试试放宽: noise=-30dB:d=0.2")
        return
    for m in marks:
        print("  " + m)
    starts = [l for l in marks if "silence_start" in l]
    print(f"\n检测到 {len(starts)} 段静音 → 可切成 {len(starts) + 1} 个片段")


GUIDE = r"""
================== 剪映功能探测步骤 ==================

只用 2 个片段测，不要拿 55 个。建议用这两个（时长短、都有口播）：
  D:\Download\分镜\7\钩子前期-从容秩序-1.mp4      (4.06s)
  D:\Download\分镜\7\卖点1-方寸灶台-1.mp4          (5.xx s)

--- 测试 A：换音色能否全选批量应用 ---
  1. 剪映新建草稿，把上面 2 个片段都拖到时间线，中间留约 1 秒空隙
  2. 命令行跑:  python probe_jianying.py snap A1
  3. 时间线上全选两个片段（Ctrl+A 或框选）
  4. 右侧 音频 → 口播换音色 → 搜「小姐姐」→ 应用
  5. 观察并记录：
     - 是两个片段都变了，还是只有一个？
     - 有没有出现"仅支持单个片段"之类的提示？
     - 是否要求会员？
  6. 等处理完，跑:  python probe_jianying.py snap A2
  7. 跑:  python probe_jianying.py diff A1 A2
     → 看新增的音频文件在哪个目录，这就回答了"产物落在哪"

--- 测试 B：人声分离与换音色是否互斥（最关键）---
  8. 对第 1 个片段（已换过音色的），再点 人声分离 → 仅保留人声
  9. 记录：
     - 人声分离能不能点？会不会提示冲突？
     - 处理完后，换音色的设置还在吗？还是被重置了？
     - 试听：听到的是小姐姐音色，还是变回原声？
 10. 反向再测：对第 2 个片段，先做人声分离，再试换音色
     → 记录换音色此时能不能用

  ★ 这一步的结果决定整个架构。如果两者互斥，
    「仅保留人声」和「换成小姐姐」只能选一个，需求 4 与 6/7 冲突。

--- 测试 C：导出字幕能否拿到纯文本 SRT ---
 11. 对时间线点 识别字幕（智能字幕 → 识别字幕）
 12. 等识别完，点右上 导出
 13. 看导出面板有没有「导出字幕」勾选项，格式里有没有 SRT
 14. 勾上导出，记录 .srt 文件落在哪、内容对不对
     → 这条通了就不用解密草稿，绕开了最大的技术障碍

--- 测试 D：导出音频 + 静音检测能否切片 ---
 15. 导出面板选 导出音频（WAV 优先，MP3 也行）
 16. 跑:  python probe_jianying.py silence "<刚导出的音频路径>"
     → 确认能否检测到你留的 1 秒空隙
     → 通了就能把长音频按间隙切回单片段，
       不受 24fps 帧量化和换音色改时长的影响

======================================================
做完 A~D 把结果告诉我（尤其是 B），我按结果定架构再开工。
"""


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    c = sys.argv[1]
    if c == "guide":
        print(GUIDE)
    elif c == "snap" and len(sys.argv) > 2:
        cmd_snap(sys.argv[2])
    elif c == "diff" and len(sys.argv) > 3:
        cmd_diff(sys.argv[2], sys.argv[3])
    elif c == "silence" and len(sys.argv) > 2:
        cmd_silence(sys.argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
