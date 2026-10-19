# -*- coding: utf-8 -*-
"""在原版熔炉贴图 rl.png 基础上绘制 T2 / T3 贴图。

不改轮廓和阵营绿描边，只叠加升级细节：
  T2：火焰更旺、烟囱冒火星、底座黄黑警示条、侧面冷却面板加亮
  T3：在 T2 基础上换成蓝白等离子火，通风口灯和冷却液发青光，火星变青色

用法（在项目根目录运行）：
    python tools/art/furnace_tiers.py
"""
import colorsys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "mod" / "人类" / "一本科技" / "rl.png"
OUT_T2 = ROOT / "mod" / "人类" / "一本科技" / "rl2.png"
OUT_T3 = ROOT / "mod" / "人类" / "一本科技" / "rl3.png"
FRAMES = 4

FLAME_BOX = (15, 20, 30, 32)          # 炉口火焰所在区域（单帧坐标，含左上不含右下）
SIDE_PANEL_BOX = (0, 26, 16, 36)      # 左侧蓝色冷却面板
RIGHT_PANEL_BOX = (30, 28, 37, 38)    # 右侧蓝色冷却面板
VENT_BOX = (16, 35, 29, 41)           # 前方通风口
STRIPE_ROW = 43                       # 底座前沿


def is_flame(px):
    """炉口区域里的暖色像素（从暗红到亮黄）都算火焰。"""
    r, g, b, a = px
    return a > 200 and r >= 40 and r > b + 25 and r >= g - 20


def is_blue(px):
    r, g, b, a = px
    return a > 200 and b > 120 and b > r + 40


def in_box(x, y, box):
    return box[0] <= x < box[2] and box[1] <= y < box[3]


def hotter(px):
    """火焰升温：色相往黄偏、亮度提高。"""
    r, g, b, a = px
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    h = min(h + 0.035, 0.15)
    v = min(v * 1.12 + 0.05, 1.0)
    s = max(s * 0.92, 0.0)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (round(r * 255), round(g * 255), round(b * 255), a)


def plasma(px):
    """按原火焰亮度映射到蓝白等离子色，保留原动画的明暗变化。"""
    r, g, b, a = px
    lum = (0.5 * r + 0.4 * g + 0.1 * b) / 255
    ramp = [(0.35, (18, 52, 170)), (0.5, (30, 120, 230)), (0.65, (70, 200, 255)), (1.01, (215, 250, 255))]
    for limit, color in ramp:
        if lum < limit:
            return color + (a,)
    return ramp[-1][1] + (a,)


def brighten_blue(px, cyan=False):
    r, g, b, a = px
    if cyan:
        return (min(r + 40, 255), min(g + 110, 255), 255, a)
    return (min(r + 25, 255), min(g + 35, 255), min(b + 40, 255), a)


def draw_stripes(frame):
    """把底座前沿的深色像素改成黄黑相间的警示条。"""
    for x in range(frame.width):
        px = frame.getpixel((x, STRIPE_ROW))
        if px[3] > 200 and sum(px[:3]) / 3 < 60:
            yellow = ((x // 2) % 2) == 0
            frame.putpixel((x, STRIPE_ROW), (236, 186, 32, 255) if yellow else (24, 22, 18, 255))


# 第三根烟囱：复制原版左烟囱（x=5~9，帽 y=9~12，管身 y=13~16），放到机体右后方
LEFT_STACK_X = 5
LEFT_CAP_ROWS = range(9, 13)
LEFT_PIPE_ROWS = range(13, 17)
NEW_STACK_X = 24
NEW_STACK_TOP = 5
RING_ROWS = (12, 13)                  # T3 能量环所在行（新烟囱管身）


def draw_third_stack(frame, src, tier):
    """只画在透明像素上，烟囱看起来位于机体后方。"""
    y = NEW_STACK_TOP
    for sy in LEFT_CAP_ROWS:
        for dx in range(5):
            px = src.getpixel((LEFT_STACK_X + dx, sy))
            if px[3] > 0 and frame.getpixel((NEW_STACK_X + dx, y))[3] < 40:
                frame.putpixel((NEW_STACK_X + dx, y), px)
        y += 1
    pipe = list(LEFT_PIPE_ROWS)
    i = 0
    while y < frame.height:
        sy = pipe[i % len(pipe)]
        if all(frame.getpixel((NEW_STACK_X + dx, y))[3] > 200 for dx in range(1, 4)):
            break                      # 管身已经插进机体
        for dx in range(5):
            px = src.getpixel((LEFT_STACK_X + dx, sy))
            if tier == 3 and y in RING_ROWS and 1 <= dx <= 3:
                px = (90, 215, 255, 255) if y == RING_ROWS[0] else (190, 250, 255, 255)
            if px[3] > 0 and frame.getpixel((NEW_STACK_X + dx, y))[3] < 40:
                frame.putpixel((NEW_STACK_X + dx, y), px)
        y += 1
        i += 1


# 每帧的火星位置（左烟囱帽 y=9、右烟囱帽 y=1、新烟囱帽 y=5）
EMBERS = [
    [(7, 7), (17, 0), (26, 3)],
    [(6, 5), (8, 7), (20, 0), (25, 2)],
    [(8, 4), (6, 7), (27, 3)],
    [(7, 3), (8, 6), (19, 0), (26, 1)],
]


def draw_embers(frame, index, colors):
    for i, (x, y) in enumerate(EMBERS[index]):
        if frame.getpixel((x, y))[3] < 40:
            frame.putpixel((x, y), colors[i % len(colors)])


def make_frame(frame, index, tier):
    out = frame.copy()
    for y in range(out.height):
        for x in range(out.width):
            px = out.getpixel((x, y))
            if in_box(x, y, FLAME_BOX) and is_flame(px):
                out.putpixel((x, y), hotter(px) if tier == 2 else plasma(px))
            elif (in_box(x, y, SIDE_PANEL_BOX) or in_box(x, y, RIGHT_PANEL_BOX)) and is_blue(px):
                out.putpixel((x, y), brighten_blue(px, cyan=tier == 3))
            elif tier == 3 and in_box(x, y, VENT_BOX) and is_blue(px):
                out.putpixel((x, y), (150, 245, 255, 255))
    draw_stripes(out)
    draw_third_stack(out, frame, tier)
    if tier == 2:
        draw_embers(out, index, [(255, 196, 64, 255), (255, 120, 32, 255)])
    else:
        draw_embers(out, index, [(150, 240, 255, 255), (60, 170, 255, 255)])
    return out


def build(tier, out_path):
    src = Image.open(SRC).convert("RGBA")
    fw = src.width // FRAMES
    sheet = Image.new("RGBA", src.size, (0, 0, 0, 0))
    for i in range(FRAMES):
        frame = src.crop((i * fw, 0, (i + 1) * fw, src.height))
        sheet.paste(make_frame(frame, i, tier), (i * fw, 0))
    sheet.save(out_path, optimize=True)
    print(f"已生成 {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    build(2, OUT_T2)
    build(3, OUT_T3)
