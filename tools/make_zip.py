# -*- coding: utf-8 -*-
"""打源码分享 zip（**排除**个人配置 / venv / 打包产物）

开源版说明：
- 路径不再写死作者机器 —— BASE 默认就是「本文件所在仓库的根目录」。
- 用的是**白名单**（只打包下面 files 里列的东西），所以 config.json
  这种含 API Key 的个人配置**天然不会被带进去**，不用担心手滑分享出去。
- 产物 zip 默认丢在仓库**上一级**目录，不污染仓库本身。

用法：
  python tools/make_zip.py
  # 想连 52MB 的 anim/ 视频素材一起打包：
  set DAFEIYU_ZIP_ANIM=1 && python tools/make_zip.py
"""
import os
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("DAFEIYU_BASE", "").strip() or os.path.dirname(_HERE)
OUT = os.environ.get("DAFEIYU_ZIP", "").strip() or os.path.join(
    os.path.dirname(BASE.rstrip("\\/")), "大肥鱼桌宠_源码.zip")

files = ["桌宠.py", "启动桌宠.bat", "requirements.txt", "README.md", "LICENSE",
         "icon.ico", ".gitignore", "config.example.json", "溯源与致谢.md",
         "tools/preprocess.py", "tools/preprocess2.py", "tools/make_zip.py",
         "tools/check_privacy.py", "tools/selftest.py"]

# 立绘素材
for root, dirs, fs in os.walk(os.path.join(BASE, "sprites")):
    for f in fs:
        files.append(os.path.relpath(os.path.join(root, f), BASE).replace(os.sep, "/"))

# 视频动画素材体积大，按需打包
if os.environ.get("DAFEIYU_ZIP_ANIM", "").strip() in ("1", "true", "yes", "on"):
    for root, dirs, fs in os.walk(os.path.join(BASE, "anim")):
        for f in fs:
            files.append(os.path.relpath(os.path.join(root, f), BASE).replace(os.sep, "/"))

# 安全兜底：万一有人把 config.json 加进上面的列表，这里再拦一次
files = [f for f in files if os.path.basename(f) not in ("config.json", ".env")]

missing = [f for f in files if not os.path.exists(os.path.join(BASE, f))]
if missing:
    print("[警告] 这些文件不存在，已跳过：", missing)
    files = [f for f in files if f not in missing]

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for f in files:
        z.write(os.path.join(BASE, f), f)

print("BASE:", BASE)
print("files:", len(files))
print("size:", os.path.getsize(OUT) // 1024, "KB")
print("out:", OUT)
