"""字幕渲染：用 Pillow 把字幕渲成透明 PNG，再由 ffmpeg overlay 叠加。

为什么不用 ffmpeg 的 drawtext/subtitles/ass：
剪映自带的 ffmpeg 是裁剪版，这三个滤镜都没有【实测】。
自带完整 ffmpeg 构建会让分发包大好几十兆，而 Pillow 已经是依赖。
Pillow 还能精确控字距、描边、阴影，对齐剪映观感更可控。

字号换算【推算，需与剪映实际出片比对校准】：
剪映字号刻度以 1080p 竖屏为基准，字号 N 的字高约 N x 4 px。
需求要 10-15 号，取中间值 12 → 1080 宽下约 48px，
换到 720 宽画布按比例 x (720/1080) = 32px。
"""

import os

from PIL import Image, ImageDraw, ImageFont

# 画布
CANVAS_W, CANVAS_H = 720, 1280

# 字号刻度 -> 1080p 基准像素
SIZE_SCALE = 4.0
REF_WIDTH = 1080

# 垂直位置：文本块中心距**画面底边** 12.5%（用户 2026-08-17 定）。
# 自顶算即 1 - 0.125 = 87.5%。原值 0.72 太靠中间，会和素材自带的花字打架。
BOTTOM_MARGIN = 0.125
VERTICAL_POS = 1.0 - BOTTOM_MARGIN

# 一块几个字。**这是「一次显示多少」不是「一行放多少」** ——
# 26 字的长句会被切成 3~4 块先后出现，见 split_blocks()。
# 用户 2026-08-18 定死 6~10：原来只设上限 8，「遇标点就断」造出大量
# 3~5 字碎块（实测 213 块里 58 块 ≤5 字，如单独的「接住,」），一屏太空。
MIN_CHARS_PER_BLOCK = 6
MAX_CHARS_PER_BLOCK = 10

# 阴影：纯黑、右下偏移
SHADOW_COLOR = (0, 0, 0, 220)
SHADOW_OFFSET = (2, 2)

TEXT_COLOR = (255, 255, 255, 255)

# 描边：白字压在浅色背景（厨房台面）上会发虚，实测需要描边才立得住。
# 剪映默认字幕也带细描边。宽度按字号比例走。
STROKE_COLOR = (0, 0, 0, 255)
STROKE_RATIO = 0.06

# 一行最多几个字。超了折行。竖屏 720 宽放不下太多字。
MAX_CHARS_PER_LINE = 14


def font_px(size_scale, canvas_w=CANVAS_W):
    """把剪映字号刻度换算成本画布的像素字号。"""
    return max(12, round(size_scale * SIZE_SCALE * canvas_w / REF_WIDTH))


BREAKABLE = "，。！？；、,.!?;…"


def split_blocks(text, min_chars=MIN_CHARS_PER_BLOCK,
                 max_chars=MAX_CHARS_PER_BLOCK):
    """把一句话切成若干「一次显示」的小块，按顺序返回。

    与 wrap_text 的区别：wrap_text 是同一张 PNG 内折行（同时可见），
    这里切出来的块**先后出现**，各自渲一张 PNG。
    ASR 单句实测中位 26 字（4~6 秒），整句挂满全程一次看太多字。

    规则（用户 2026-08-18 定）：每块字数**必须落在 6~10**，
    在这个前提下尽量在标点处断开、标点留块末不跑到块首。

    **不能用贪心**：贪心到句尾必撞死区 —— 剩 11 字时 6+5 会造 5 字块、
    整块出又超 10，只有回头把前面的块改短才解得开。所以这里用 DP
    对「整句的所有合法切法」求最优，代价函数只惩罚不在标点收尾。
    """
    text = text.strip()
    if not text:
        return []

    n = len(text)
    # 数学死区：n < 2*min 时切两块必有一块不足下限（11 字只能 6+5），
    # 切不了就整块出。宁可一块 11 字（仍是单行，折行阈值 14）
    # 也不放出 5 字碎块 —— 下限是用户这次的硬要求。
    if n < 2 * min_chars:
        return [text]

    def cut_cost(end):
        """在 end 处切一刀的代价：标点收尾最好，其次是标点的下一字。

        词中断罚得重（30）：轻罚过实测 DP 会为了凑长度乱切，
        断出「先看颜色和位 | 置合不合适」这种半个词。罚重之后它宁可
        让块长在 6~10 里挪，也会去够那个标点。
        """
        if text[end - 1] in BREAKABLE:
            return 0
        if end < n and text[end] in BREAKABLE:
            return 60     # 把标点甩到下一块块首，最差
        return 30         # 词中间硬断

    # best[i] = 把 text[i:] 切完的最小代价，nxt[i] = 第一刀切在哪
    INF = float("inf")
    best = [INF] * (n + 1)
    nxt = [None] * (n + 1)
    best[n] = 0
    for i in range(n - 1, -1, -1):
        rest = n - i
        for size in range(min_chars, max_chars + 1):
            j = i + size
            if j > n:
                # 收尾块：不足下限就不合法，除非整句只剩这一块（上面已排除）
                break
            if best[j] == INF:
                continue
            c = best[j] + (cut_cost(j) if j < n else 0)
            if c < best[i]:
                best[i] = c
                nxt[i] = j
        # 尾巴比下限还短（rest < min_chars）时 best[i] 保持 INF，
        # DP 自会绕开这种切法，回头把前面的块拉长/缩短去消化它。
        if rest < min_chars:
            best[i] = INF
            nxt[i] = None

    if best[0] == INF:
        # 理论上 n > max_chars 时总有解；真无解就退化成等分，别丢字。
        step = max_chars
        return [text[k:k + step] for k in range(0, n, step)]

    blocks, i = [], 0
    while i < n:
        j = nxt[i]
        blocks.append(text[i:j])
        i = j
    return [b.strip() for b in blocks if b.strip()]


def wrap_text(text, max_chars=MAX_CHARS_PER_LINE):
    """中文按字数折行。优先在标点处断，避免标点跑到行首。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    breakable = "，。！？；、,.!?;… "
    lines, cur = [], ""
    for ch in text:
        cur += ch
        if len(cur) >= max_chars:
            # 往回找最近的可断点，找不到就硬断
            cut = -1
            for i in range(len(cur) - 1, max(0, len(cur) - 5), -1):
                if cur[i] in breakable:
                    cut = i + 1
                    break
            if cut > 0:
                lines.append(cur[:cut].strip())
                cur = cur[cut:]
            else:
                lines.append(cur)
                cur = ""
    if cur.strip():
        lines.append(cur.strip())

    lines = [l for l in lines if l]

    # 孤立标点不能单独成行 —— 实测出现过句末「。」掉到第二行。
    # 只剩标点的行合并回上一行。
    fixed = []
    for l in lines:
        if fixed and not l.strip(breakable):
            fixed[-1] += l
        else:
            fixed.append(l)
    return fixed


def render_png(text, out_path, font_path, size_scale=12,
               canvas=(CANVAS_W, CANVAS_H), shadow=True):
    """把一句字幕渲成透明 PNG，尺寸等于整个画布，可直接 overlay 到 0,0。

    返回 out_path；文本为空则返回 None（不产文件，调用方跳过叠加）。
    """
    lines = wrap_text(text)
    if not lines:
        return None

    w, h = canvas
    px = font_px(size_scale, w)
    font = ImageFont.truetype(font_path, px)

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    line_h = round(px * 1.35)
    total_h = line_h * len(lines)
    # 以 VERTICAL_POS 为文本块的垂直中心
    top = round(h * VERTICAL_POS - total_h / 2)
    stroke = max(1, round(px * STROKE_RATIO))

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke)
        tw = bbox[2] - bbox[0]
        x = round((w - tw) / 2) - bbox[0]
        y = top + i * line_h

        if shadow:
            draw.text((x + SHADOW_OFFSET[0], y + SHADOW_OFFSET[1]), line,
                      font=font, fill=SHADOW_COLOR,
                      stroke_width=stroke, stroke_fill=SHADOW_COLOR)
        draw.text((x, y), line, font=font, fill=TEXT_COLOR,
                  stroke_width=stroke, stroke_fill=STROKE_COLOR)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path)
    return out_path
