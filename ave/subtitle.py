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

# 「正中央偏下」：垂直位置取画面高度的 72%（剪映默认字幕位置附近）
VERTICAL_POS = 0.72

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
