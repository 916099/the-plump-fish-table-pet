# -*- coding: utf-8 -*-
"""精灵边缘去污 + 预乘alpha缩放：
1) 边缘像素做白底去混合，恢复真实颜色（消除移动/旋转时的白边）
2) 用黑底/白底合成法做预乘alpha缩放，直接生成各尺寸精灵

用法（开源版：路径不再写死任何人的机器）：
  先跑 tools/preprocess.py 得到透明底三视图，再跑本脚本生成多尺寸精灵。
  指定素材目录，二选一：
    - 推荐：set DAFEIYU_SRC=素材目录
    - 或者：把下面的 SRC 直接改成你的目录
  输出默认写到本仓库的 sprites/ 目录（可用 DAFEIYU_OUT 改）。
"""
from PIL import Image
import os

# ===== 路径配置：留空就要你显式指定，绝不猜 =====
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)

SRC = os.environ.get("DAFEIYU_SRC", "").strip()          # ← 抠好图的三视图目录
OUT = os.environ.get("DAFEIYU_OUT", "").strip() or os.path.join(_REPO, "sprites")
SIZES = {0.55: 187, 0.7: 238, 0.9: 306}

if not SRC or not os.path.isdir(SRC):
    raise SystemExit(
        "还没指定素材目录。\n"
        "  目录里需要有：正面.png / 侧面.png / 背面.png（透明底，先跑 preprocess.py）\n"
        "  推荐做法：set DAFEIYU_SRC=你的素材目录\n"
        "  也可以直接改本文件开头的 SRC。\n"
        "  当前 SRC = %r" % SRC)

os.makedirs(OUT, exist_ok=True)


def decontaminate(im):
    """边缘像素对白底去混合：pixel = fg*a + 255*(1-a) → fg = (pixel - 255*(1-a))/a"""
    im = im.convert("RGBA")
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if 0 < a < 255:
                t = a / 255.0
                if a < 40:          # 极淡边缘直接透明，避免除噪放大
                    px[x, y] = (0, 0, 0, 0)
                    continue
                nr = (r - 255 * (1 - t)) / t
                ng = (g - 255 * (1 - t)) / t
                nb = (b - 255 * (1 - t)) / t
                px[x, y] = (int(max(0, min(255, nr))), int(max(0, min(255, ng))),
                            int(max(0, min(255, nb))), a)
    return im


def cutout(path):
    """白底泛洪抠图（沿用第一版逻辑）"""
    im = Image.open(path).convert("RGBA")
    from PIL import ImageDraw
    w, h = im.size
    for sx, sy in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        ImageDraw.floodfill(im, (sx, sy), (0, 0, 0, 0), thresh=30)
    return im.crop(im.getbbox())


def premult_resize(im, height):
    """预乘alpha缩放：黑底/白底各缩放一次，再解出真实颜色+alpha"""
    w0, h0 = im.size
    nw = max(1, round(w0 * height / h0))
    black = Image.new("RGBA", im.size, (0, 0, 0, 255))
    white = Image.new("RGBA", im.size, (255, 255, 255, 255))
    b_img = Image.alpha_composite(black, im).resize((nw, height), Image.LANCZOS)
    w_img = Image.alpha_composite(white, im).resize((nw, height), Image.LANCZOS)
    bp, wp = b_img.load(), w_img.load()
    out = Image.new("RGBA", (nw, height))
    op = out.load()
    for y in range(height):
        for x in range(nw):
            br, bg, bb, _ = bp[x, y]
            wr, wg, wb, _ = wp[x, y]
            a = 255 - max(wr - br, wg - bg, wb - bb)   # 覆盖度
            if a < 6:
                op[x, y] = (0, 0, 0, 0)
                continue
            t = a / 255.0
            op[x, y] = (int(max(0, min(255, br / t))), int(max(0, min(255, bg / t))),
                        int(max(0, min(255, bb / t))), a)
    return out


for name in ["正面", "侧面", "背面"]:
    raw = cutout(os.path.join(SRC, f"{name}.png"))
    clean = decontaminate(raw)
    for mult, h in SIZES.items():
        im = premult_resize(clean, h)
        im.save(os.path.join(OUT, f"{name}_{h}.png"))
        print(f"{name}_{h}.png {im.size}")

# 托盘图标（用中档再缩）
icon = Image.open(os.path.join(OUT, "正面_187.png")).convert("RGBA")
icon = premult_resize(icon, 64)
icon.save(os.path.join(OUT, "icon.png"))
print("icon 64x64")
