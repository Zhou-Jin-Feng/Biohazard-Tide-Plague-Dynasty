# -*- coding: utf-8 -*-
"""在原版补给站贴图 tx.png 基础上绘制 T2 / T3 贴图。

保留原版水泥方块、卫星天线和自带阴影，只叠加升级细节：
  T2：大门改成金属卷帘并加黄黑警示条，正面两角加钢制包边，屋顶放补给箱和红色信号灯
  T3：在 T2 基础上加天线桅杆、屋顶太阳能板、门边蓝色状态灯

用法（在项目根目录运行）：
    python tools/art/supply_tiers.py
"""
import random
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "mod" / "人类" / "二本科技" / "tx.png"
OUT_T2 = ROOT / "mod" / "人类" / "二本科技" / "tx2.png"
OUT_T3 = ROOT / "mod" / "人类" / "二本科技" / "tx3.png"

DOOR = (19, 38, 40, 50)               # 正面大门内部（含左上不含右下）
DOOR_SILL_ROWS = (50, 51)             # 门槛
LEFT_EDGE_X = (14, 15)                # 正面左侧边角
RIGHT_EDGE_X = (44, 45)               # 正面右侧边角
EDGE_ROWS = range(34, 50)


def clamp(v):
    return max(0, min(255, int(round(v))))


def shade(px, delta):
    r, g, b, a = px
    return (clamp(r + delta), clamp(g + delta), clamp(b + delta), a)


def textured(color, rng, amount=6):
    """给纯色加一点噪点，贴合原图的写实质感。"""
    d = rng.randint(-amount, amount)
    return tuple(clamp(c + d) for c in color[:3]) + (255,)


def roller_door(im):
    """大门做成金属卷帘：每隔 3 行一道亮缝 + 下方暗线，保留原有纹理。"""
    x0, y0, x1, y1 = DOOR
    for y in range(y0, y1):
        phase = (y - y0) % 3
        for x in range(x0, x1):
            px = im.getpixel((x, y))
            if px[3] < 200:
                continue
            if phase == 0:
                im.putpixel((x, y), shade(px, 22))
            elif phase == 2:
                im.putpixel((x, y), shade(px, -10))


def hazard_sill(im):
    for y in DOOR_SILL_ROWS:
        for x in range(DOOR[0], DOOR[2]):
            if im.getpixel((x, y))[3] < 200:
                continue
            yellow = ((x + y) // 2) % 2 == 0
            im.putpixel((x, y), (214, 168, 38, 255) if yellow else (30, 27, 22, 255))


def steel_edges(im, rng):
    for xs in (LEFT_EDGE_X, RIGHT_EDGE_X):
        for y in EDGE_ROWS:
            for i, x in enumerate(xs):
                if im.getpixel((x, y))[3] < 200:
                    continue
                base = (128, 136, 146) if i == 0 else (96, 103, 112)
                color = textured(base, rng, 4)
                if (y - EDGE_ROWS.start) % 5 == 2 and i == 0:
                    color = (190, 196, 204, 255)          # 铆钉
                im.putpixel((x, y), color)


def crate(im, x, y, w, rng):
    """斜俯视的木箱：顶面亮、正面暗，边框深色，中间一道木板缝。"""
    top, front, edge = (176, 134, 82), (124, 86, 48), (58, 38, 22)
    for dx in range(w):
        for dy in range(3):
            im.putpixel((x + dx, y + dy), textured(top, rng, 8))
        for dy in range(3, 6):
            im.putpixel((x + dx, y + dy), textured(front, rng, 8))
    for dx in range(w):
        im.putpixel((x + dx, y), (196, 156, 102, 255))
        im.putpixel((x + dx, y + 5), edge + (255,))
    for dy in range(6):
        im.putpixel((x, y + dy), edge + (255,))
        im.putpixel((x + w - 1, y + dy), edge + (255,))
    for dx in range(1, w - 1):
        im.putpixel((x + dx, y + 3), edge + (255,))


def beacon(im, x, y, color):
    """小立柱 + 一个灯珠，周围一圈淡淡的光晕。"""
    im.putpixel((x, y + 1), (40, 40, 44, 255))
    im.putpixel((x, y + 2), (40, 40, 44, 255))
    im.putpixel((x, y), color + (255,))
    for gx, gy in ((x - 1, y), (x + 1, y), (x, y - 1)):
        px = im.getpixel((gx, gy))
        glow = tuple(clamp(px[i] * 0.4 + color[i] * 0.6) for i in range(3))
        im.putpixel((gx, gy), glow + (max(px[3], 160),))


def antenna_mast(im):
    """屋顶右后方的天线桅杆，顶端红灯、中段白灯。"""
    x = 41
    for y in range(4, 15):
        im.putpixel((x, y), (52, 54, 58, 255))
        im.putpixel((x + 1, y), (118, 122, 128, 255))
    for y in (7, 10):
        im.putpixel((x - 1, y), (70, 72, 76, 255))
        im.putpixel((x + 2, y), (70, 72, 76, 255))
    im.putpixel((x, 3), (235, 50, 36, 255))
    im.putpixel((x + 1, 3), (255, 120, 96, 255))
    im.putpixel((x + 1, 9), (240, 244, 250, 255))


def solar_panel(im, rng):
    """屋顶左下方的太阳能板。"""
    x0, y0, w, h = 16, 24, 10, 6
    for dy in range(h):
        for dx in range(w):
            color = textured((34, 56, 92), rng, 6)
            if dx % 3 == 0 or dy % 3 == 0:
                color = textured((56, 84, 124), rng, 5)
            im.putpixel((x0 + dx, y0 + dy), color)
    for dx in range(w):
        im.putpixel((x0 + dx, y0), textured((112, 140, 176), rng, 6))
        im.putpixel((x0 + dx, y0 + h), (34, 34, 38, 255))
    for dy in range(h + 1):
        im.putpixel((x0 - 1, y0 + dy), (34, 34, 38, 255))
        im.putpixel((x0 + w, y0 + dy), (34, 34, 38, 255))


def status_lights(im):
    for y in (40, 44):
        im.putpixel((42, y), (110, 225, 255, 255))
        im.putpixel((43, y), (40, 120, 170, 255))


def build(tier, out_path):
    rng = random.Random(20261019 + tier)          # 固定随机种子，保证每次生成结果一致
    im = Image.open(SRC).convert("RGBA")
    roller_door(im)
    hazard_sill(im)
    steel_edges(im, rng)
    crate(im, 34, 26, 6, rng)
    crate(im, 39, 28, 5, rng)
    if tier == 3:
        solar_panel(im, rng)
        antenna_mast(im)
        status_lights(im)
    beacon(im, 44, 13, (230, 46, 34))
    im.save(out_path, optimize=True)
    print(f"已生成 {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    build(2, OUT_T2)
    build(3, OUT_T3)
