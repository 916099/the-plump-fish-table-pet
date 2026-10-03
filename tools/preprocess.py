# -*- coding: utf-8 -*-
"""三视图抠图+规格化：白底 → 透明 PNG，统一高度，裁掉空白边。

用法（开源版：路径不再写死任何人的机器）：
  1) 把你的三视图原图（白底）放进一个目录，里面要有 正面.png / 侧面.png / 背面.png
  2) 指定素材目录，二选一：
       - 推荐：设环境变量   set DAFEIYU_SRC=D:\\我的素材\\大肥鱼
       - 或者：把下面的 SRC 直接改成你的目录
  3) 运行   python tools/preprocess.py
  输出默认写到本仓库的 sprites/ 目录（可用 DAFEIYU_OUT 改）。
"""
from PIL import Image, ImageDraw
import os

# ===== 路径配置：留空就要你显式指定，绝不猜 =====
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)

SRC = os.environ.get("DAFEIYU_SRC", "").strip()          # ← 你的三视图原图目录
OUT = os.environ.get("DAFEIYU_OUT", "").strip() or os.path.join(_REPO, "sprites")
TARGET_H = 340  # 桌宠显示高度(px)

if not SRC or not os.path.isdir(SRC):
    raise SystemExit(
        "还没指定三视图素材目录。\n"
        "  目录里需要有：正面.png / 侧面.png / 背面.png（白底）\n"
        "  推荐做法：set DAFEIYU_SRC=你的素材目录\n"
        "  也可以直接改本文件开头的 SRC。\n"
        "  当前 SRC = %r" % SRC)

os.makedirs(OUT, exist_ok=True)

def cutout(path):
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    seed = im.getpixel((0, 0))
    # 1) 从四角做连通域泛洪，把背景整片变透明（人物内部的白不受影响）
    for sx, sy in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        ImageDraw.floodfill(im, (sx, sy), (0, 0, 0, 0), thresh=30)
    # 2) 去白边：贴着透明区的亮像素也变透明（消除抗锯齿白晕）
    for _ in range(3):
        px = im.load()
        changed = False
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                if a == 0:
                    continue
                if r > 215 and g > 215 and b > 215:
                    # 检查邻域是否有透明像素
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < w and 0 <= ny < h and px[nx, ny][3] == 0:
                            px[x, y] = (0, 0, 0, 0)
                            changed = True
                            break
        if not changed:
            break
    # 3) 裁掉透明边
    bbox = im.getbbox()
    if bbox is None:
        raise RuntimeError(f"{path}: 抠图后为空！")
    im = im.crop(bbox)
    # 4) 统一高度
    w2, h2 = im.size
    scale = TARGET_H / h2
    im = im.resize((max(1, round(w2 * scale)), TARGET_H), Image.LANCZOS)
    return im

for name in ["正面", "侧面", "背面"]:
    im = cutout(os.path.join(SRC, f"{name}.png"))
    out_path = os.path.join(OUT, f"{name}.png")
    im.save(out_path)
    print(f"{name}: {im.size} -> {out_path}")

# 托盘小图标
Icon = cutout(os.path.join(SRC, "正面.png")).resize((64, 64), Image.LANCZOS)
Icon.save(os.path.join(OUT, "icon.png"))
print("icon: 64x64")
