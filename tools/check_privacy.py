# -*- coding: utf-8 -*-
"""开源前自检：扫一遍仓库，看有没有把密钥 / 个人路径漏出去。

用法：
    python tools/check_privacy.py

退出码：0 = 干净（可以开源）；1 = 发现问题（先修再发）
"""
import os
import re
import sys

try:                                    # 让中文提示在 GBK 控制台里也不乱码
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# 只扫文本类文件；二进制/素材/虚拟环境一律跳过
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "build", "dist",
             "node_modules", "runtime", "backup", ".idea", ".vscode"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".webm", ".mp4",
            ".zip", ".7z", ".rar", ".exe", ".dll", ".pyc", ".pyd", ".woff",
            ".woff2", ".ttf", ".pdf", ".bin", ".so", ".db", ".sqlite"}

# ===== 要抓的模式 =====
PATTERNS = [
    # 1) 真的像 DeepSeek / OpenAI Key 的串
    ("疑似 API Key", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b")),
    # 2) 别的服务常见 Key 前缀
    ("疑似其他服务 Token", re.compile(r"\b(ghp_|gho_|github_pat_|xoxb-|AKIA|AIza)[A-Za-z0-9_\-]{12,}\b")),
    # 3) 赋值式：api_key = "很长的一串"
    ("疑似硬编码密钥赋值",
     re.compile(r"(?i)\b(api[_-]?key|apikey|secret|token|passwd|password)\b\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']")),
    # 4) 别人机器上的私人路径（原作者素材目录）
    ("个人路径（原作者素材目录）", re.compile(r"[A-Za-z]:\\图图")),
    # 5) 具体用户目录（可能暴露用户名）—— <你> 这种尖括号占位符不算
    ("个人路径（用户目录）", re.compile(r"[A-Za-z]:\\Users\\[^\\\"'\s<>]{2,}")),
]

# 这些是「故意写成占位符 / 故意造假」的，命中不算问题
ALLOW = (
    "我的API key 填充sk……",
    "你的城市",
    "sk-xxxxxxxx",
    "your-api-key-here",
    "YOUR_API_KEY",
    # tools/selftest.py 里专门用的**假** Key，用来验证掩码逻辑，不是真 Key
    "sk-abcdefghijklmnopqrstuvwxyz0123456789",
)

# 路径里带这些词说明是占位符写法（<你的名字> / 用户名 / username…），不算泄露
PLACEHOLDER_WORDS = ("你的", "名字", "<", ">", "username", "user", "用户名", "账户名")


def iter_text_files():
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if os.path.splitext(fn)[1].lower() in SKIP_EXT:
                continue
            p = os.path.join(root, fn)
            if os.path.getsize(p) > 4 * 1024 * 1024:      # 超过 4MB 的当二进制跳过
                continue
            yield p


def main():
    problems = []
    scanned = 0
    for path in iter_text_files():
        rel = os.path.relpath(path, REPO)
        # 本文件自己是「抓密钥的规则」，会命中自己的正则，跳过
        if os.path.abspath(path) == os.path.abspath(__file__):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception:
            continue
        scanned += 1
        for i, line in enumerate(lines, 1):
            if any(a in line for a in ALLOW):
                continue
            for label, rx in PATTERNS:
                m = rx.search(line)
                if not m:
                    continue
                hit = m.group(0)
                # 占位符写法的路径（<你的名字> / 用户名 / username…）不算泄露
                if label.startswith("个人路径") and any(w in hit.lower() for w in PLACEHOLDER_WORDS):
                    continue
                # 只回显一小段，避免把疑似密钥完整打印到终端/日志里
                masked = hit[:8] + "***" if len(hit) > 8 else "***"
                problems.append((rel, i, label, masked))
                break

    print("扫描了 %d 个文本文件（已跳过 .venv / 素材 / 运行期目录）" % scanned)
    print()

    # 额外检查：个人配置有没有被 gitignore 挡住
    gi = os.path.join(REPO, ".gitignore")
    gi_text = ""
    if os.path.exists(gi):
        with open(gi, "r", encoding="utf-8", errors="ignore") as f:
            gi_text = f.read()
    for must in ("config.json", "key.bin"):
        if must not in gi_text:
            problems.append((".gitignore", 0, "%s 没被 gitignore 挡住" % must, must))

    # 再实际看一眼：仓库里不应该真的躺着这两个文件
    for must in ("config.json", "key.bin"):
        if os.path.exists(os.path.join(REPO, must)):
            problems.append((must, 0, "仓库里真的存在这个个人文件（应当只留 %s）" % must,
                             must))

    if problems:
        print("发现 %d 处需要处理：" % len(problems))
        for rel, line, label, masked in problems:
            where = "%s:%d" % (rel, line) if line else rel
            print("  [%s] %s  ->  %s" % (label, where, masked))
        print()
        print("如果这些是模板占位符，请把它们加进本文件的 ALLOW 列表；")
        print("如果是真的密钥，请立刻更换密钥，并把它从代码里删掉（改用 key.bin / config.json 读取）。")
        return 1

    print("干净 ✓ 没有发现漏出去的密钥或个人路径，可以开源。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
