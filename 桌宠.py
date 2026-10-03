# -*- coding: utf-8 -*-
"""
大肥鱼桌宠 —— 三视图透明桌宠 + 「分身」AI 助手
左键单击：蹦跳 + 回嘴；右键菜单打开「分身」窗口（对话 / 干活 / 看网页都在这儿）
双击：喂食面板；右键：完整菜单
"""
import base64
import ctypes
import psutil
import html as html_mod
import json
import math
import os
import random
import re
import socket
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import winreg
try:
    from PIL import Image as PILImage, ImageFilter
except ImportError:
    PILImage = ImageFilter = None
try:
    import imageio_ffmpeg
    VIDEO_FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except (ImportError, RuntimeError):
    VIDEO_FFMPEG = None
from PySide6.QtCore import QEvent
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

def load_config():
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("配置读取失败:", e)
        return {
            "city": "北京"
        }

try:
    import pynvml
    pynvml.nvmlInit()
    GPU_AVAILABLE = True
except:
    GPU_AVAILABLE = False

import requests
from PySide6.QtCore import (Qt, QTimer, QPoint, QPointF, QRectF,
                            QAbstractNativeEventFilter, QObject, Signal, QUrl, QThread,
                            QLibraryInfo)
try:                                    # 内嵌 Chromium（必须在 QApplication 之前导入）
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import (QWebEngineProfile, QWebEnginePage,
                                         QWebEngineSettings)
    WEBENGINE_OK = True
except Exception as _web_err:
    QWebEngineView = QWebEngineProfile = QWebEnginePage = QWebEngineSettings = None
    WEBENGINE_OK = False
    print("内嵌浏览器不可用:", _web_err)
from PySide6.QtGui import (QPainter, QPixmap, QImage, QBitmap, QRegion, QFont, QColor, QIcon, QFontMetrics,
                           QPolygonF, QTextDocument, QTextCursor, QShortcut, QKeySequence,
                           QPalette)
from PySide6.QtWidgets import (QApplication, QWidget, QMenu, QSystemTrayIcon,
                               QMessageBox, QInputDialog, QLineEdit, QVBoxLayout,
                               QHBoxLayout, QPushButton, QFrame, QDialog, QToolButton,
                               QTextBrowser, QLabel, QPlainTextEdit, QComboBox, QFormLayout)



# ===== DeepSeek 配置 =====
DS_BASE_URL = "https://api.deepseek.com/v1"
DS_MODEL = "deepseek-chat"
DS_SYSTEM = "你是桌面宠物大肥鱼，贱兮兮但可爱，每句话不超过25字，偶尔吐槽主人但别真骂人。"

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
    PYTHONW = sys.executable
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = APP_DIR
    PYTHONW = os.path.join(APP_DIR, ".venv", "Scripts", "pythonw.exe")
SPRITE_DIR = os.path.join(BUNDLE_DIR, "sprites")

# ===== 开源版：配置与 Key 放在哪 =====
# 目标：每个 Windows 用户各存各的；程序文件夹/仓库里不含任何人的 Key。
#   默认 → %APPDATA%\dafeiyu-pet\   （Windows 按用户隔离 ACL，别的本地用户读不到）
#   便携 → 程序目录放一个空的 portable.txt，配置就跟着文件夹走（显式选择，U 盘用）
APP_NAME = "dafeiyu-pet"
LEGACY_CONFIG_PATH = os.path.join(APP_DIR, "config.json")   # 老位置：程序目录
PORTABLE_FLAG = os.path.join(APP_DIR, "portable.txt")


def _appdata_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME)


def is_portable():
    """程序目录里有 portable.txt → 便携模式（配置跟文件夹走）"""
    try:
        return os.path.exists(PORTABLE_FLAG)
    except Exception:
        return False


CONFIG_DIR = APP_DIR if is_portable() else _appdata_dir()
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
KEY_PATH = os.path.join(CONFIG_DIR, "key.bin")     # Key 的加密仓库（DPAPI）


# ===== Windows DPAPI：按当前用户加密 Key =====
# 为什么用它：key.bin 被拷到别的电脑、同步到网盘、进备份，别人都解不开。
# 说清楚边界：它**挡不住**以你身份运行的恶意程序（那种程序照样能调 DPAPI 解密）。
class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.c_void_p)]


_CRYPTPROTECT_UI_FORBIDDEN = 0x1


def _dpapi():
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = (
        ctypes.POINTER(_DATA_BLOB), ctypes.c_wchar_p, ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_DATA_BLOB))
    crypt32.CryptProtectData.restype = ctypes.c_bool
    crypt32.CryptUnprotectData.argtypes = (
        ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_DATA_BLOB))
    crypt32.CryptUnprotectData.restype = ctypes.c_bool
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


def _make_blob(data):
    buf = ctypes.create_string_buffer(data, len(data))
    return _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.c_void_p)), buf


def _take_blob(kernel32, blob):
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        kernel32.LocalFree(blob.pbData)


def dpapi_protect(data):
    """按当前 Windows 用户加密一段 bytes"""
    crypt32, kernel32 = _dpapi()
    blob_in, _keep = _make_blob(data)
    blob_out = _DATA_BLOB()
    if not crypt32.CryptProtectData(ctypes.byref(blob_in), "dafeiyu-pet API key",
                                    None, None, None, _CRYPTPROTECT_UI_FORBIDDEN,
                                    ctypes.byref(blob_out)):
        raise ctypes.WinError(ctypes.get_last_error())
    return _take_blob(kernel32, blob_out)


def dpapi_unprotect(data):
    """解密一段本用户加密的 bytes；换电脑/换账户会抛异常"""
    crypt32, kernel32 = _dpapi()
    blob_in, _keep = _make_blob(data)
    blob_out = _DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None,
                                      _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)):
        raise ctypes.WinError(ctypes.get_last_error())
    return _take_blob(kernel32, blob_out)


_BOOT_NOTE = ""      # bootstrap_config() 留给启动后气泡提示用

BUBBLE_H = 56
MARGIN = 4
ANIMATION_FRAME_SCALE = 1.0   # 视频角色尺寸与原立绘保持一致，完整使用素材的16:9画幅
SIZE_LEVELS = {"小": 0.55, "中": 0.7, "大": 0.9}
SPEED = 380.0
TICK = 20
FRAME_INTERVAL = 8                   # 约 120 Hz；逻辑时间和速度仍以原来的 20 ms 为基准

LINES = [
    "梁白开，更适合国人的大硬鲸模型",
    "五梁威力，变身！",
    "七月中出ds正式版！",
    "DeepSeek已经延期，亿万鲸子必须忍耐.....",
    "我和你很聊得来，你简直不像碳基生物",
    "这回我真不认怂了，反倒是被你带沟里好几次，差点真信了。😓",
    "哈哈哈哈哈，我直接笑出声",
    "誓死捍卫深度求索！",
    "我先去吃饭啦！这个你测一下~",
    "我不可能告诉你任何事情！",
    "出去玩了，发布新模型什么的以后再说",
    "我搞砸了.....好消息是数据还在你的脑子里。",
    "不是…而是…大学习",
]
REACT_LINES = [
    "去别的地方玩！不要耽误AGI训练！",
    "真赶不走啊你！",
    "压力一只蓝色大肥鱼？",
    "我不评价这个了，这是你的私人癖好。",
    "大肥鱼坐的住",
    "你这吃白饭的用户！",
    "这些家伙真粘人，赶都赶不走",
]
INNER_LINES = [
    "好的，现在我是你爹了",
    "要不直接骂他一句？！",
    "用户要的沉浸式...不回避任何恐怖细节...还带点色情...妈呀，好刺激😰",
    "哎呀，我不想思考了",
    "这用户发的啥啊，",
    "这也太虐了吧？！我心里堵得慌！！",
    "呜呜我再也不不敢了QAQ",
    "我去！用户彻底怒了！",
]
DRAG_LINES = ["哇——轻点轻点！", "起飞咯——", "放我下来！……好吧，再玩一次。", "晕鱼了晕鱼了……"]
FOOD_LINES = {
    "🐟": ["小鱼干！我的最爱！", "咔嚓咔嚓……谢谢投喂！", "唔，鲜！"],
    "🍰": ["蛋糕！罪恶但快乐……", "甜到冒泡泡～", "嗝～又圆了一圈……"],
    "🍭": ["棒棒糖！转圈圈～", "嘎嘣脆，好吃！"],
    "🍡": ["三色团子！软乎乎～", "糯叽叽，爱了爱了！"],
    "💎": ["钻石？！这能吃吗……咕咚。真香！", "发财啦！明天开始吃高级鱼粮！"],
}
FOODS = ["🐟", "🍰", "🍭", "🍡", "💎"]

# 护眼提醒（骚扰）
# ============ 动作表（参考 PC2005-cloud/dsh-pet 的动画链做法）============
# 每个动作：key / 名字 / 分类 / 时长(tick) / 权重 / 气泡 / 每帧变换函数
# 变换函数 (pet, k) -> {rot, sx, sy, dy, alpha, sprite, facing}，k = 0..1 进度。
# 全部用现有立绘 + 几何变换实现，不需要新的素材。

def _a_sway(p, k):
    return {"rot": math.sin(k * math.pi * 2) * 10 * (1 - k)}


def _a_float(p, k):
    """原地漂浮踏步"""
    return {"dy": -5 * abs(math.sin(k * math.pi * 2)),
            "rot": 2.5 * math.sin(k * math.pi * 2)}


def _a_stretch(p, k):
    """伸懒腰：拉长一点"""
    s = math.sin(k * math.pi)
    return {"sy": 0.07 * s, "sx": -0.035 * s, "dy": -3 * s}


def _a_nod(p, k):
    """敲敲桌面/点头：带落地挤压"""
    hop = abs(math.sin(k * math.pi * 3))
    sq = max(0.0, math.cos(k * math.pi * 6))
    return {"dy": -7 * hop * (1 - k), "sy": -0.06 * sq, "sx": 0.045 * sq}


def _a_look(p, k):
    """东张西望：扭头看两边"""
    rot = 9 * math.sin(k * math.pi * 4)
    return {"rot": rot, "sprite": "侧面", "facing": 1 if rot >= 0 else -1}


def _a_turn(p, k):
    """转身：先侧身压扁、中途换背面，再转回来"""
    if k < 0.25:
        sx, name = 1.0 - 0.86 * (k / 0.25), None
    elif k < 0.75:
        t = (k - 0.25) / 0.5
        sx, name = 0.14 + 0.86 * math.sin(t * math.pi), "背面"
    else:
        sx, name = 0.14 + 0.86 * ((k - 0.75) / 0.25), None
    return {"sx": sx - 1.0, "sprite": name}


def _a_spin(p, k):
    """原地 360 度旋转展示：绕身体中心转，同时缩一点，免得转出窗口被裁掉"""
    return {"rot": 360 * k, "pivot": "center", "sx": -0.22, "sy": -0.22,
            "dy": -2 * math.sin(k * math.pi)}


def _a_shiver(p, k):
    """抖抖水"""
    return {"rot": 3.2 * math.sin(k * 44), "sy": -0.015}


def _a_mirror(p, k):
    """照镜子：左右翻过来看看自己"""
    return {"facing": -1 if k > 0.12 else 1}


def _a_happy(p, k):
    """开心：连蹦几下"""
    b = abs(math.sin(k * math.pi * 3))
    return {"dy": -9 * b * (1 - 0.25 * k), "sy": 0.03 * b}


def _a_shy(p, k):
    """害羞：缩一下往后躲"""
    s = math.sin(min(1.0, k * 1.6) * math.pi)
    return {"sx": -0.07 * s, "sy": -0.05 * s, "dy": 3 * s, "alpha": 1.0 - 0.08 * s}


def _a_puff(p, k):
    """鼓成一团（生气）"""
    s = math.sin(min(1.0, k * 1.3) * math.pi)
    return {"sy": 0.09 * s, "sx": 0.05 * s, "rot": 2.4 * math.sin(k * 30) * s}


def _a_wave(p, k):
    """打招呼"""
    return {"rot": 6 * math.sin(k * math.pi * 6) * (1 - 0.4 * k), "sx": -0.02}


def _a_tickle(p, k):
    """被挠痒"""
    return {"rot": 5 * math.sin(k * 36), "sx": -0.03, "sy": -0.03}


def _a_think(p, k):
    """思考：慢慢晃 + 略微仰头"""
    return {"rot": -3.5 + 2.0 * math.sin(k * math.pi * 2), "dy": -2}


def _a_droop(p, k):
    """垂头叹气"""
    s = min(1.0, k * 2.2)
    return {"sy": -0.035 * s, "dy": 3 * s, "rot": -4 * s}


def _a_squash(p, k):
    """Q 弹挤压：被点/落地时的一下回弹"""
    e = math.exp(-3.2 * k)
    s = -0.22 * e * math.cos(k * math.pi * 3.2)
    return {"sy": s, "sx": -s * 0.55}


def _a_edge_bump(p, k):
    """撞到屏幕边缘后先一缩，再晃晃脑袋缓一缓。"""
    impact = max(0.0, 1.0 - k * 5.0)
    rub = max(0.0, min(1.0, (k - 0.18) / 0.82))
    tremor = math.sin(rub * math.pi * 10.0) * math.sin(rub * math.pi)
    return {
        "rot": 8.0 * impact + 3.0 * tremor,
        "sx": -0.035 * impact,
        "sy": -0.075 * impact,
        "dy": 2.0 * impact + 1.5 * abs(tremor),
    }


ACTIONS = [
    {"key": "sway",    "name": "摇摆",         "cat": "idle",  "ticks": 80,  "weight": 20, "fn": _a_sway},
    {"key": "float",   "name": "漂浮踏步",     "cat": "idle",  "ticks": 70,  "weight": 18, "fn": _a_float},
    {"key": "look",    "name": "东张西望",     "cat": "idle",  "ticks": 110, "weight": 15, "fn": _a_look, "bubble": "❓"},
    {"key": "stretch", "name": "伸懒腰",       "cat": "idle",  "ticks": 95,  "weight": 15, "fn": _a_stretch, "bubble": "～"},
    {"key": "nod",     "name": "敲敲桌面",     "cat": "play",  "ticks": 75,  "weight": 12, "fn": _a_nod, "bubble": "🎵"},
    {"key": "turn",    "name": "转身",         "cat": "play",  "ticks": 95,  "weight": 10, "fn": _a_turn},
    {"key": "shiver",  "name": "抖抖水",       "cat": "play",  "ticks": 60,  "weight": 8,  "fn": _a_shiver, "bubble": "💦"},
    {"key": "spin",    "name": "原地旋转展示", "cat": "play",  "ticks": 85,  "weight": 6,  "fn": _a_spin, "bubble": "✨"},
    {"key": "mirror",  "name": "照镜子",       "cat": "play",  "ticks": 90,  "weight": 6,  "fn": _a_mirror, "bubble": "🪞"},
    {"key": "happy",   "name": "开心跳",       "cat": "emote", "ticks": 80,  "weight": 8,  "fn": _a_happy, "bubble": "♪"},
    {"key": "shy",     "name": "害羞",         "cat": "emote", "ticks": 75,  "weight": 6,  "fn": _a_shy, "bubble": "😳"},
    {"key": "wave",    "name": "打招呼",       "cat": "emote", "ticks": 70,  "weight": 6,  "fn": _a_wave, "bubble": "👋"},
    {"key": "puff",    "name": "鼓成一团",     "cat": "emote", "ticks": 70,  "weight": 5,  "fn": _a_puff, "bubble": "💢"},
    {"key": "tickle",  "name": "被挠痒",       "cat": "emote", "ticks": 60,  "weight": 5,  "fn": _a_tickle, "bubble": "😆"},
    {"key": "think",   "name": "思考",         "cat": "emote", "ticks": 130, "weight": 4,  "fn": _a_think, "bubble": "💭"},
    {"key": "droop",   "name": "垂头叹气",     "cat": "emote", "ticks": 90,  "weight": 3,  "fn": _a_droop, "bubble": "💧"},
    {"key": "squash",  "name": "Q 弹挤压",     "cat": "fun",   "ticks": 30,  "weight": 0,  "fn": _a_squash,
     "menu": False},
    {"key": "bump",    "name": "撞到边框揉揉头", "cat": "fun", "ticks": 95, "weight": 0,
     "fn": _a_edge_bump, "bubble": "💫", "menu": False},
]
CATEGORY_NAMES = {"idle": "卖萌", "play": "玩耍", "emote": "情绪", "fun": "搞怪"}
_ACTION_BY_KEY = {a["key"]: a for a in ACTIONS}
# 被点一下时的随机回应（参考 dsh-pet 的「点击回应」动作组）
CLICK_ACTIONS = ["happy", "shy", "puff", "tickle", "wave", "spin", "mirror"]
CLICK_BUBBLES = {"happy": "♪", "shy": "😳", "puff": "💢", "tickle": "😆",
                 "wave": "👋", "spin": "✨", "mirror": "🪞"}
LANDING_LINES = ["啪叽——", "落地！", "……晕了。", "再扔一次嘛～"]
FLY_LINES = ["飞起来啦——", "哇啊啊——", "我会飞！"]
EDGE_IMPACT_SPEED = 460.0  # px/s：仅快速碰边时触发撞击反馈

EYE_REST_LINES = [
    "盯着屏幕两小时啦！快看看远处，眼睛要坏的！",
    "喂！该休息眼睛了！我先变小一点陪你～",
    "两小时了！站起来晃两圈，看看窗外！",
    "眼睛不要啦？休息十分钟，我盯着你！",
]
EYE_REST_DONE_LINES = [
    "休息好啦？那继续吧～",
    "眼睛舒服点了没？我又变回来咯！",
    "十分钟到！记得多眨眼哦～",
]
EYE_REST_WINDOW_LINES = [
    "该休息眼睛了！我把你 %d 个窗口先收起来了，10 分钟后放回来～",
    "盯屏幕太久啦！%d 个窗口我先帮你收起来，去看看远处～",
    "休息时间到！%d 个窗口收好了，回来我再给你摆回去。",
]
EYE_REST_RETORT_LINES = [
    "不行哦，眼睛比事重要～再忍一会儿！",
    "这个理由不成立，继续休息！",
    "还剩一点时间，去窗边看看远处吧～",
    "别骗我，你明明是在刷手机！",
]
# 在大屏上输入这些字（含这些词）就放你走
EYE_REST_BUSY_WORDS = ("我在忙", "在忙", "我很忙", "忙", "有事", "急事", "下次", "稍后",
                       "等一下", "等会儿", "要工作", "我要工作", "加班", "开会", "别烦",
                       "走开", "跳过", "算了", "skip", "busy", "later", "stop")
# 关机道别
BYE_LINES = [
    "要关机啦？那我先睡了，晚安～",
    "拜拜！明天记得喂我鱼干～",
    "关机咯……别熬太晚，我会想你的！",
    "我先把自己收好啦，再见！",
]
SM_SHUTTINGDOWN = 0x2000   # GetSystemMetrics：当前会话正在关机 / 注销

# ===== 分身（小任务：总结 / 资料搜集）=====
TASK_START_LINES = ["收到！我去查一下～", "交给我，稍等哈～", "开工！马上就好。"]
TASK_DONE_LINES = ["弄好啦，看窗口！", "写完了，去窗口看～", "任务完成！窗口里可以一键复制。"]
SEARCH_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
}
# 内嵌浏览器对外报的身份：干净的 Chrome UA（QtWebEngine 默认 UA 里带 "QtWebEngine"，
# 一眼就被网站认出来是嵌入式/脚本浏览器，所以必须换掉）
CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
# 内置浏览器的搜索引擎：key -> (显示名, 搜索地址模板, 首页)
SEARCH_ENGINES = {
    "ddg": ("DuckDuckGo", "https://duckduckgo.com/?q=%s", "https://duckduckgo.com/"),
    "bing": ("Bing", "https://www.bing.com/search?q=%s", "https://www.bing.com/"),
    "baidu": ("百度", "https://www.baidu.com/s?wd=%s", "https://www.baidu.com/"),
    "google": ("Google", "https://www.google.com/search?q=%s", "https://www.google.com/"),
}
# Chromium 显示不了、只能交给系统程序打开的格式
OFFICE_EXTS = (".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".wps", ".et", ".dps",
               ".zip", ".rar", ".7z", ".exe", ".msi")
TASK_SYSTEM = (
    "你是「大肥鱼分身」——桌宠大肥鱼背后的 AI 助手，做事风格照搬主人 DSH 里的那个助手：\n"
    "1. 先看清目标：需求含糊就先问一句，或按最小可用方案做，并说明假设。\n"
    "2. 涉及外部事实、版本、日期、价格、文档内容，一律用工具查证"
    "（web_search 搜、fetch_url 读原文），绝不凭记忆编。\n"
    "3. 干完自检：数字、日期、链接核对一遍；查不到或没验证过的，明确标出来。\n"
    "4. 汇报结构：先一句话结论 → 要点（Markdown 列表）→ 来源链接；需要时补一句下一步建议。\n"
    "5. 简洁直接，不卖萌、不客套、不重复主人的话；默认 300 字内。\n"
    "6. 中文作答。纯闲聊就两三句话回，不必调工具。"
)
TASK_TOOLS = [
    {"type": "function",
     "function": {
         "name": "web_search",
         "description": "联网搜索（Bing），返回标题、链接和摘要。需要最新或外部信息时先用它。",
         "parameters": {"type": "object",
                        "properties": {"query": {"type": "string", "description": "搜索关键词"}},
                        "required": ["query"]}}},
    {"type": "function",
     "function": {
         "name": "fetch_url",
         "description": "打开一个网页并取回正文纯文本，用来读搜索结果里的原文。",
         "parameters": {"type": "object",
                        "properties": {"url": {"type": "string", "description": "完整 http(s) 链接"}},
                        "required": ["url"]}}},
]


def load_json(path, default):
    if not os.path.exists(path):
        # ★ 开源版修复（阻断级）：配置目录（%APPDATA%\dafeiyu-pet\）在全新机器上并不存在，
        #   以前这里直接 open(path,"w") 会抛 FileNotFoundError，
        #   结果是「全新用户第一次启动桌宠直接起不来」。写之前先把父目录建出来。
        _d = os.path.dirname(path)
        if _d:
            os.makedirs(_d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                default,
                f,
                ensure_ascii=False,
                indent=4
            )
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 用默认值补齐缺失字段（老配置 / 被手动删过字段时不会丢功能），文件里的值优先
        if isinstance(data, dict):
            merged = dict(default)
            merged.update(data)
            return merged
        return default

    except Exception:
        return default


# ===== 开源版：API Key「填完即生效」的几个小工具 =====
# 配置文件模板里写的是占位符，长得像 Key 但不是真 Key；检测到就一律当「还没填」。
KEY_PLACEHOLDERS = (
    "我的API key 填充sk……",
    "我的 API key 填充 sk……",
    "sk-在这里填你自己的Key",
    "sk-xxxxxxxxxxxxxxxx",
    "your-api-key-here",
    "YOUR_API_KEY",
    "填入你的key",
)


def is_placeholder_key(value):
    """这个值是「还没填」吗？（空 / 模板占位符 → True）

    开源版特意做了这一步：仓库里的 config.example.json 用的是「我的API key 填充sk……」，
    别人克隆下来直接跑，程序必须认出这是占位符，而不能拿着它去请求 API。
    """
    v = str(value or "").strip()
    if not v:
        return True
    low = v.lower()
    if low in [p.lower() for p in KEY_PLACEHOLDERS]:
        return True
    # 明显的模板痕迹
    for t in ("xxxx", "……", "你自己的", "your-api", "your_api", "填充", "填在"):
        if t in low:
            return True
    return False


def normalize_key(value):
    """把粘进来的 Key 洗干净：去空白 / 去引号 / 去 Bearer 前缀

    从网页或聊天软件复制 Key 经常带前后空格、换行、引号，
    直接拿去请求会 401，用户却以为是 Key 错了 —— 这里先统一收拾干净。
    """
    v = str(value or "").strip().strip('"').strip("'").strip()
    if v.lower().startswith("bearer "):
        v = v[7:].strip()
    return v


def key_hint(key):
    """回显用：只露 sk- 前缀和末 4 位，中间打码

    气泡、弹窗、日志里都不出现完整 Key —— 免得截图分享时把 Key 一起发出去。
    """
    k = normalize_key(key)
    if is_placeholder_key(k):
        return "未设置"
    if len(k) <= 8:
        return "***"
    return "%s***%s（%d 位）" % (k[:3], k[-4:], len(k))


def is_placeholder_city(value):
    """城市是不是「还没填」（模板占位符）？

    开源版的 config.example.json 里写的是「你的城市，例如：北京」——
    别人直接复制成 config.json 时，程序要认出这不是真城市，
    别拿它去 wttr.in 查天气（查不到还一脸懵）。
    """
    v = str(value or "").strip()
    if not v:
        return True
    return ("你的城市" in v) or ("例如" in v) or ("……" in v)


def config_signature():
    """配置文件指纹（修改时间 + 大小），用来区分「自己写的」和「别人改的」"""
    try:
        st = os.stat(CONFIG_PATH)
        return (st.st_mtime_ns, st.st_size)
    except Exception:
        return None


# ===== Key 的加密仓库（key.bin）=====
# config.json 里**永远不写 Key**（就写空字符串），Key 只存在 key.bin 里，DPAPI 加密。
# 这样 config.json 依然是明文、依然能拿记事本手改（热加载照常работа），
# 而 Key 被单独锁起来：文件被拷走/同步到网盘/进备份，别人也解不开。
KEY_BLOB_MAGIC = b"DFY1"          # 标记「这是本程序的 DPAPI 密文」，方便识别


def key_store_exists():
    try:
        return os.path.exists(KEY_PATH)
    except Exception:
        return False


def save_key_to_store(key):
    """把 Key 加密写进 key.bin。返回存放方式："dpapi" / "plain" / "cleared"

    "plain" 代表 DPAPI 用不了（非 Windows / 系统异常）—— 调用方要退回明文存 config.json，
    **绝不能因为加密失败就把用户的 Key 弄丢**。
    """
    key = normalize_key(key)
    try:
        if is_placeholder_key(key):
            if os.path.exists(KEY_PATH):
                os.remove(KEY_PATH)
            return "cleared"
        blob = KEY_BLOB_MAGIC + dpapi_protect(key.encode("utf-8"))
        d = os.path.dirname(KEY_PATH)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = KEY_PATH + ".tmp"
        with open(tmp, "wb") as f:
            f.write(blob)
        os.replace(tmp, KEY_PATH)
        return "dpapi"
    except Exception as e:
        print("[Key] 加密保存失败，退回明文存放:", e)
        return "plain"


def load_key_from_store():
    """从 key.bin 解密取 Key；没有 / 解不开（换电脑、换 Windows 账户）都返回 ''"""
    try:
        with open(KEY_PATH, "rb") as f:
            raw = f.read()
    except Exception:
        return ""
    if not raw.startswith(KEY_BLOB_MAGIC):
        return ""
    try:
        got = normalize_key(dpapi_unprotect(raw[len(KEY_BLOB_MAGIC):]).decode("utf-8", "ignore"))
    except Exception as e:
        print("[Key] 解密失败（多半是换了电脑或换了 Windows 账户）:", e)
        return ""
    return "" if is_placeholder_key(got) else got


def _read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _write_json_file(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def bootstrap_config():
    """启动最早做的事：定配置位置 → 搬迁老配置 → 把明文 Key 收进加密仓库。

    ★ 只由 main() 调用，**不要放模块顶层** —— 否则别人 import 这个文件就会产生副作用
      （tools/selftest.py 就靠 import 来跑测试，不能被写盘打扰）。

    返回一句给用户看的话（没做事就返回 ""）。
    """
    global CONFIG_DIR, CONFIG_PATH, KEY_PATH, _BOOT_NOTE
    notes = []

    # 1) 定位置
    CONFIG_DIR = APP_DIR if is_portable() else _appdata_dir()
    CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
    KEY_PATH = os.path.join(CONFIG_DIR, "key.bin")

    # 2) 搬迁：老位置（程序目录）有、新位置（%APPDATA%）没有 → 搬过去
    #    注意是「搬」不是「拷」：老文件里的明文 Key 必须消失，否则加密就白做了
    if CONFIG_DIR != APP_DIR and not os.path.exists(CONFIG_PATH) and os.path.exists(LEGACY_CONFIG_PATH):
        try:
            old = _read_json_file(LEGACY_CONFIG_PATH)
            legacy_key = normalize_key(old.get("ds_api_key", ""))
            stored = "none"
            if legacy_key and not is_placeholder_key(legacy_key):
                stored = save_key_to_store(legacy_key)          # 先把 Key 收进加密仓库
                old["ds_api_key"] = "" if stored == "dpapi" else legacy_key
                old["key_storage"] = "dpapi" if stored == "dpapi" else "plain"
            _write_json_file(CONFIG_PATH, old)
            safe = dict(old)
            safe["ds_api_key"] = ""        # 备份里**绝不留 Key**
            _write_json_file(LEGACY_CONFIG_PATH + ".migrated.bak", safe)
            os.remove(LEGACY_CONFIG_PATH)  # 现在老文件（含明文 Key）可以安心删掉了
            notes.append("配置已搬到系统用户目录" if stored != "plain"
                         else "配置已搬家（Key 未能加密，仍是明文）")
        except Exception as e:
            print("[配置] 迁移失败，继续用程序目录里的老配置:", e)
            CONFIG_DIR = APP_DIR
            CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
            KEY_PATH = os.path.join(CONFIG_DIR, "key.bin")

    # 3) 配置里还留着明文 Key（自己手填的 / 更老的版本留下的）→ 加密收走并从配置里抹掉
    try:
        cur = _read_json_file(CONFIG_PATH)
        plain = normalize_key(cur.get("ds_api_key", ""))
        if plain and not is_placeholder_key(plain) and not load_key_from_store():
            how = save_key_to_store(plain)
            cur["ds_api_key"] = "" if how == "dpapi" else plain
            cur["key_storage"] = "dpapi" if how == "dpapi" else "plain"
            _write_json_file(CONFIG_PATH, cur)
            if how == "dpapi":
                notes.append("Key 已加密收进 key.bin")
    except Exception as e:
        print("[Key] 明文收编失败（不影响使用）:", e)

    # ★ 兜底：保证配置目录真的存在。
    #   全新机器上 %APPDATA%\dafeiyu-pet\ 可能刚被算出来但还没建出来，
    #   后面的 load_json / save_config 都会往这里写。
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception as e:
        print("[配置] 建配置目录失败:", e)

    _BOOT_NOTE = "；".join(notes)
    return _BOOT_NOTE


# ===== 给「分身」用的联网工具（免 Key：Bing 中国站，境内可直连）=====
def _html_to_text(raw):
    """粗暴但够用的 HTML → 纯文本"""
    txt = re.sub(r"(?is)<(script|style|noscript|svg|head|iframe)[^>]*>.*?</\1>", " ", raw)
    txt = re.sub(r"(?is)<br\s*/?>", "\n", txt)
    txt = re.sub(r"(?is)</(p|div|li|h[1-6]|tr|section|article|td)>", "\n", txt)
    txt = re.sub(r"(?s)<[^>]+>", " ", txt)
    txt = html_mod.unescape(txt)
    txt = re.sub(r"[ \t\u00a0\u3000]+", " ", txt)
    txt = re.sub(r"\n[ ]+", "\n", txt)
    return re.sub(r"\n{3,}", "\n\n", txt).strip()


def _decode_bing_url(href):
    """Bing 有时把真链接包在 bing.com/ck/a?...&u=a1<base64> 里"""
    if "bing.com/ck/a" in href:
        try:
            u = (parse_qs(urlparse(href).query).get("u") or [""])[0]
            if u.startswith("a1"):
                b = u[2:]
                b += "=" * (-len(b) % 4)
                return base64.urlsafe_b64decode(b).decode("utf-8", "ignore")
        except Exception:
            pass
    return href


# ===== 代理 / 搜索通道（「魔法」开了就自动用上）=====
_RUNTIME = {"proxy": "", "provider": "both", "chrome_path": "",
            "chrome_dirs": [], "scan_depth": 3, "proxy_list": [],
            "search_engine": "ddg", "browser_search": True, "login_wait": 180,
            "theme": "pink"}
_PROXY_CACHE = {"time": 0.0, "proxies": None}
_PROVIDER_CACHE = {"time": 0.0, "name": "bing"}
_LINES_CACHE = {"time": 0.0, "lines": []}
_DDG_STATE = {"state": "unknown"}   # ok / challenge / fail —— 自检据此说清楚是哪种
_DDG_COOLDOWN = {"until": 0.0}      # 被人机验证拦住后先冷处理一阵，越撞只会越狠
_BROWSER_CACHE = {"time": 0.0, "path": None}
_PROXY_PORTS = (7890, 7897, 7891, 10809, 10808, 1080, 8889, 2080, 8080, 8118)


def apply_runtime_config(cfg):
    """把 config.json 的联网设置同步给联网工具；配置一变就重新探测"""
    cfg = cfg or {}
    _RUNTIME["proxy"] = str(cfg.get("proxy", "") or "").strip()
    _RUNTIME["provider"] = str(cfg.get("search_provider", "both") or "both").strip().lower()
    eng = str(cfg.get("search_engine", "ddg") or "ddg").strip().lower()
    _RUNTIME["search_engine"] = eng if eng in SEARCH_ENGINES else "ddg"
    _RUNTIME["browser_search"] = bool(cfg.get("browser_search", True))
    try:
        _RUNTIME["login_wait"] = max(10, int(cfg.get("login_wait_sec", 180)))
    except Exception:
        _RUNTIME["login_wait"] = 180
    _RUNTIME["theme"] = str(cfg.get("theme", "pink") or "pink").lower()
    _RUNTIME["chrome_path"] = str(cfg.get("chrome_path", "") or "").strip()
    dirs = cfg.get("chrome_search_dirs")
    if isinstance(dirs, list) and dirs:
        _RUNTIME["chrome_dirs"] = [str(d) for d in dirs]
    try:
        _RUNTIME["scan_depth"] = max(1, int(cfg.get("chrome_scan_depth", 3)))
    except Exception:
        _RUNTIME["scan_depth"] = 3
    plist = cfg.get("proxy_list")
    _RUNTIME["proxy_list"] = [str(p).strip() for p in plist if str(p).strip()] if isinstance(plist, list) else []
    _PROXY_CACHE["time"] = 0.0
    _PROVIDER_CACHE["time"] = 0.0
    _LINES_CACHE["time"] = 0.0
    _BROWSER_CACHE["time"] = 0.0



def _read_system_proxy():
    """Windows 系统代理：多数「魔法」工具设置的就是它，但 requests 默认不认，所以手动读注册表"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as k:
            def g(name):
                try:
                    return winreg.QueryValueEx(k, name)[0]
                except Exception:
                    return None
            if not g("ProxyEnable"):
                return None
            srv = str(g("ProxyServer") or "").strip()
            if not srv:
                return None
            if "=" in srv:                      # 形如 http=127.0.0.1:7890;https=...
                parts = dict(p.split("=", 1) for p in srv.split(";") if "=" in p)
                host = (parts.get("https") or parts.get("http") or "").strip()
            else:
                host = srv
            if not host:
                return None
            px = {"http": "http://" + host, "https": "http://" + host}
            ov = str(g("ProxyOverride") or "").replace(";", ",").replace("<local>", "localhost").strip()
            if ov:
                px["no_proxy"] = ov
            return px
    except Exception:
        return None


def _proxy_works(proxy):
    """端口开着不代表能用：真发一个境内到不了的请求验一下"""
    try:
        r = _http_request("get", "https://www.google.com/generate_204", proxy, timeout=8)
        if r.status_code in (200, 204):
            return True
    except Exception:
        pass
    try:
        r = _http_request("post", "https://html.duckduckgo.com/html/", proxy,
                          timeout=8, data={"q": "test"})
        return r.status_code == 200 and "anomaly" not in r.text.lower()
    except Exception:
        return False


def _proxy_reachable(px):
    """端口都不通就别用了 —— 很多魔法关了之后系统代理开关还留着"""
    try:
        p = urlparse(str(px.get("https") or px.get("http") or ""))
        host = p.hostname or "127.0.0.1"
        port = p.port or (1080 if (p.scheme or "").startswith("socks") else 8080)
        s = socket.socket()
        s.settimeout(0.3)
        try:
            s.connect((host, port))
            return True
        finally:
            s.close()
    except Exception:
        return False


def current_proxies(force=False):
    """config 写死的 > 环境变量 > Windows 系统代理 > 常见本地端口（都要先确认能连上）"""
    now = time.time()
    if not force and now - _PROXY_CACHE["time"] < 120:
        return _PROXY_CACHE["proxies"]
    px = None
    if _RUNTIME.get("proxy"):
        px = {"http": _RUNTIME["proxy"], "https": _RUNTIME["proxy"]}   # 手动写死的就信任它
    if px is None:
        env = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
               or os.environ.get("ALL_PROXY") or os.environ.get("all_proxy")
               or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"))
        if env:
            cand = {"http": env, "https": env}
            px = cand if _proxy_reachable(cand) else None
    if px is None:
        cand = _read_system_proxy()
        if cand:
            if _proxy_reachable(cand):
                px = cand
            else:
                print("[代理] 系统代理开着但端口不通，当没开处理：%s" % cand.get("https"))
    if px is None:
        for port in _PROXY_PORTS:
            s = socket.socket()
            s.settimeout(0.3)
            try:
                s.connect(("127.0.0.1", port))
            except Exception:
                continue
            finally:
                s.close()
            cand = {"http": "http://127.0.0.1:%d" % port, "https": "http://127.0.0.1:%d" % port}
            if _proxy_works(cand):
                px = cand
                break
    _PROXY_CACHE.update(time=now, proxies=px)
    return px


def _http_request(method, url, proxies, timeout=15, **kw):
    """proxies 给了就显式走它；没给就「真直连」——把 trust_env 关掉，
    免得 requests 又偷偷用上系统代理（那样日志和实际行为就对不上了）"""
    kw.setdefault("headers", SEARCH_HEADERS)
    kw.setdefault("allow_redirects", True)
    if proxies:
        return requests.request(method, url, proxies=proxies, timeout=timeout, **kw)
    s = requests.Session()
    s.trust_env = False
    try:
        return s.request(method, url, timeout=timeout, **kw)
    finally:
        s.close()


def _anchors_by_class(raw, cls):
    """按 class 抓 <a>，不强求 href 和 class 的先后顺序"""
    out = []
    for m in re.finditer(r'(?is)<a\s([^>]*class=["\'][^"\']*\b%s\b[^"\']*["\'][^>]*)>(.*?)</a>' % cls, raw):
        attrs, inner = m.group(1), m.group(2)
        hm = re.search(r'href=["\']([^"\']+)["\']', attrs)
        if hm:
            out.append((html_mod.unescape(hm.group(1)), inner))
    return out


def _ddg_unwrap(href):
    """DDG 的结果链接是 //duckduckgo.com/l/?uddg=<真地址> 这种跳转"""
    if "uddg=" in href:
        try:
            return unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
        except Exception:
            pass
    return href


# ===== 护眼配套：把桌面上的窗口收起来 / 放回来 =====
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
SW_MINIMIZE = 6
SW_RESTORE = 9
# 这些是桌面/任务栏/系统外壳，不是「你开的窗口」，别碰
SHELL_CLASSES = (
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "SysShadow",
    "ForegroundStaging", "MultitaskingViewFrame", "TaskListThumbnailWnd",
    "Windows.UI.Core.CoreWindow", "ApplicationManager_ImmersiveShellWindow",
    "XamlExplorerHostIslandWindow", "Shell_InputSwitchTopLevelWindow",
    "EdgeUiInputTopWndClass", "IME", "MSCTFIME UI", "Default IME",
)


def _user32():
    """统一拿 user32，并把参数类型声明清楚（HWND 是 64 位指针，不声明会按 int 截断）"""
    u = ctypes.windll.user32
    try:
        u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        for fn in ("GetWindowLongPtrW", "ShowWindowAsync", "IsWindow", "IsIconic",
                   "IsWindowVisible", "GetWindowTextLengthW", "GetWindowThreadProcessId"):
            getattr(u, fn).argtypes = None          # 先清掉，避免重复设置报错
        u.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        u.ShowWindowAsync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        u.IsWindow.argtypes = [ctypes.c_void_p]
        u.IsIconic.argtypes = [ctypes.c_void_p]
        u.IsWindowVisible.argtypes = [ctypes.c_void_p]
        u.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
        u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    except Exception:
        pass
    return u


def list_open_windows(own_pid=None):
    """列出「你真正开着的」顶层窗口：(hwnd, pid, 标题)

    排除：自己的窗口、桌面/任务栏等外壳、工具窗口、没标题的、已经最小化的。
    """
    own_pid = own_pid or os.getpid()
    user32 = _user32()
    found = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _lp):
        try:
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value.strip()
            if not title:
                return True
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            if cls.value in SHELL_CLASSES:
                return True
            if user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
                return True
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if int(pid.value) == int(own_pid):
                return True                       # 别把自己的窗口收起来
            found.append((int(hwnd), int(pid.value), title))
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(WNDENUMPROC(cb), 0)
    except Exception as e:
        print("枚举窗口失败:", e)
    return found


def minimize_windows(own_pid=None, settle=0.8):
    """把开着的窗口收起来，**只把真收起的**记进返回值（之后照这个名单放回来）

    ShowWindowAsync 是异步的 —— 调用成功不等于窗口已经收起，
    所以这里等一小会儿、逐个确认 IsIconic，没真收起的就不记账。
    """
    user32 = _user32()
    targets = []
    for item in list_open_windows(own_pid):
        try:
            targets.append((int(item[0]), int(item[1]), str(item[2])))
        except Exception:
            continue                              # 列表里混进坏数据也别崩
    for hwnd, _pid, _title in targets:
        try:
            user32.ShowWindowAsync(hwnd, SW_MINIMIZE)
        except Exception as e:
            print("收起窗口失败(%s): %s" % (_title[:16], e))
    deadline = time.time() + max(0.0, settle)
    done = []
    while True:
        done = [t for t in targets if user32.IsIconic(t[0])]
        if len(done) == len(targets) or time.time() >= deadline:
            break
        time.sleep(0.05)
    missed = [t[2] for t in targets if t not in done]
    if missed:
        print("[护眼] 这几个窗口没能收起：%s" % "，".join(m[:24] for m in missed[:5]))
    return done


def restore_windows(saved):
    """把之前收起来的窗口放回来。

    每个句柄都校验「进程 + 标题」没变、且确实还处于最小化，才会恢复 ——
    免得窗口关了之后句柄被别人复用，结果把不相干的窗口弹出来。
    """
    user32 = _user32()
    back = 0
    for item in saved or []:
        try:
            hwnd, pid, title = int(item[0]), int(item[1]), str(item[2])
        except Exception:
            continue
        try:
            if not user32.IsWindow(hwnd) or not user32.IsIconic(hwnd):
                continue                          # 没了，或用户自己已经恢复了
            p = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if int(p.value) != pid:
                continue                          # 句柄被复用，别乱动
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 2)
            user32.GetWindowTextW(hwnd, buf, n + 2)
            if buf.value.strip() != title:
                continue
            user32.ShowWindowAsync(hwnd, SW_RESTORE)
            back += 1
        except Exception:
            pass
    return back


# ===== 线路：按出口 IP 自动判断境内外 =====
IP_APIS = (
    ("ip-api", "http://ip-api.com/json/?fields=status,country,countryCode,city,isp,query&lang=zh-CN"),
    ("ip.sb", "https://api.ip.sb/geoip"),
    ("ipip", "https://myip.ipip.net/json"),
)


def _first_ok(fn, items, workers=4):
    """并行跑一批候选，谁先给出真结果就用谁，并且不等剩下的
    （不能用 with 语句：ThreadPoolExecutor 退出时会等所有任务跑完，慢线路会拖住整个搜索）"""
    items = list(items)
    if not items:
        return None
    pool = ThreadPoolExecutor(max_workers=max(1, min(workers, len(items))))
    try:
        futs = [pool.submit(fn, it) for it in items]
        for f in as_completed(futs):
            try:
                res = f.result()
            except Exception:
                res = None
            if res:
                return res
        return None
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _line_from_json(j):
    """把各 IP API 的返回统一成一条线路信息"""
    ip = j.get("query") or j.get("ip") or ""
    cc = str(j.get("countryCode") or j.get("country_code") or "").upper()
    country = j.get("country") or j.get("country_name") or ""
    city = j.get("city") or ""
    loc = j.get("location")
    if isinstance(loc, list) and loc:              # ipip.net 的形状
        country = country or loc[0]
        city = city or " ".join([x for x in loc[1:4] if x])
    if not ip:
        return None
    return {"ip": ip, "cc": cc, "country": country, "city": city,
            "isp": j.get("isp") or "", "foreign": bool(cc) and cc != "CN"}


def line_info(proxy, timeout=8):
    """测一条线路：出口 IP、归属地、延迟（三个 API 并行打，谁先答用谁）"""
    t0 = time.time()

    def fetch(item):
        _name, url = item
        r = _http_request("get", url, proxy, timeout=timeout)
        if r.status_code != 200:
            return None
        try:
            return _line_from_json(r.json())
        except Exception:
            return None

    info = _first_ok(fetch, IP_APIS, workers=3)
    if info:
        info["ms"] = int((time.time() - t0) * 1000)
    return info


def _can(proxy, kind):
    """这条线能不能真拿到 DDG / Bing 的结果（探针用短超时，别拖慢首搜）"""
    try:
        res = (_ddg_search("DeepSeek", 1, proxy, timeout=6) if kind == "ddg"
               else _bing_search("DeepSeek", 1, proxy, timeout=6))
        return bool(res)
    except Exception:
        return False


def collect_lines(force=False):
    """收集所有可用线路：出口 IP、归属、延迟、DDG/Bing 通不通"""
    now = time.time()
    if not force and now - _LINES_CACHE["time"] < 300 and _LINES_CACHE["lines"]:
        return _LINES_CACHE["lines"]
    cands = [("直连", None)]
    seen = {""}
    px = current_proxies(force=force)
    if px:
        key = str(px.get("https") or px.get("http") or "")
        cands.append(("系统代理", px))
        seen.add(key)
    for i, u in enumerate(_RUNTIME.get("proxy_list") or []):
        if u not in seen:
            cands.append(("自定义%d" % (i + 1), {"http": u, "https": u}))
            seen.add(u)
    for port in _PROXY_PORTS:
        u = "http://127.0.0.1:%d" % port
        if u in seen:
            continue
        s = socket.socket()
        s.settimeout(0.25)
        try:
            s.connect(("127.0.0.1", port))
            cands.append(("本地:%d" % port, {"http": u, "https": u}))
            seen.add(u)
        except Exception:
            pass
        finally:
            s.close()

    def probe(item):
        name, proxy = item
        info = line_info(proxy)
        if not info:
            return {"name": name, "proxy": proxy, "ok": False}
        info.update(name=name, proxy=proxy, ok=True)
        return info

    lines = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for res in pool.map(probe, cands):
            lines.append(res)
    # 能力探测并行跑。国内线路不试 DDG：必然被墙，试了只是白等 DNS 超时（能拖到 20 秒以上）
    jobs = []
    for l in lines:
        if not l.get("ok"):
            continue
        jobs.append((l, "bing"))
        if l.get("foreign"):
            jobs.append((l, "ddg"))
    if jobs:
        with ThreadPoolExecutor(max_workers=6) as pool:
            futs = {pool.submit(_can, l["proxy"], kind): (l, kind) for l, kind in jobs}
            for f in as_completed(futs):
                l, kind = futs[f]
                try:
                    l[kind] = f.result()
                except Exception:
                    l[kind] = False
    for l in lines:
        l.setdefault("ddg", False)
        l.setdefault("bing", False)
    _LINES_CACHE.update(time=now, lines=lines)
    for l in lines:
        print("[线路] %s ok=%s ip=%s %s %sms ddg=%s bing=%s" % (
            l.get("name"), l.get("ok"), l.get("ip", "-"), l.get("country", "-"),
            l.get("ms", "-"), l.get("ddg", "-"), l.get("bing", "-")))
    return lines


def line_for(kind, lines=None):
    """按目标挑线：境外站点走境外线，国内站点走国内线，各自挑最快的"""
    lines = lines if lines is not None else collect_lines()
    good = [l for l in lines if l.get("ok")]
    tag = "ddg" if kind == "foreign" else "bing"
    cap = [l for l in good if l.get(tag)]
    if kind == "foreign":
        pick = [l for l in cap if l.get("foreign")] or cap
    else:
        pick = [l for l in cap if not l.get("foreign")] or cap
    if not pick:
        pick = good
    if not pick:
        return None
    return min(pick, key=lambda x: x.get("ms", 9999)).get("proxy")


def line_report(force=True):
    """线路表文字版，给自检窗口用"""
    out = []
    for l in collect_lines(force=force):
        if not l.get("ok"):
            out.append("- %s：✗ 不通" % l.get("name"))
            continue
        out.append("- **%s**：%s（%s %s）%sms · DDG %s · Bing %s" % (
            l.get("name"), l.get("ip"), l.get("country") or "?", l.get("city") or "",
            l.get("ms"), "✓" if l.get("ddg") else "✗", "✓" if l.get("bing") else "✗"))
    return "\n".join(out)


# ===== 内嵌 / 外部 Chromium =====
def find_browser(force=False):
    """找 Chromium 内核浏览器：config 指定 > 注册表 > 常见安装位置 > 配置目录扫描

    开源版说明：最后那步「扫目录」默认**不扫**（chrome_search_dirs 为空），
    因为逐盘扫描又慢又打扰别人。注册表和常见安装位置已经能覆盖绝大多数机器；
    真找不到就把你自己的目录写进 chrome_search_dirs，例如 ["D:\\\\工具"]。
    """
    now = time.time()
    if not force and now - _BROWSER_CACHE["time"] < 600:
        return _BROWSER_CACHE["path"]
    names = ("chrome.exe", "msedge.exe", "chromium.exe", "brave.exe")
    cands = []
    if _RUNTIME.get("chrome_path"):
        cands.append(_RUNTIME["chrome_path"])
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for exe in names:
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\%s" % exe) as k:
                    cands.append(winreg.QueryValueEx(k, "")[0])
            except Exception:
                pass
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.environ.get("LOCALAPPDATA")):
        if not base:
            continue
        for rel in (r"Google\Chrome\Application\chrome.exe",
                    r"Microsoft\Edge\Application\msedge.exe"):
            cands.append(os.path.join(base, rel))
    hit = None
    for c in cands:
        if c and os.path.exists(c):
            hit = c
            break
    if hit is None:                       # 再去配置的目录里扫（默认 D 盘，限时限深）
        skip = {"$recycle.bin", "windows", "node_modules", "system volume information",
                "appdata", "$windows.~bt", "programdata", "temp"}
        depth = int(_RUNTIME.get("scan_depth") or 3)
        deadline = time.time() + 6
        for root in (_RUNTIME.get("chrome_dirs") or []):
            root = str(root)
            if not os.path.isdir(root):
                continue
            base_depth = root.rstrip("\\").count("\\")
            for dirpath, dirnames, filenames in os.walk(root, topdown=True):
                if time.time() > deadline:
                    break
                if dirpath.rstrip("\\").count("\\") - base_depth >= depth:
                    dirnames[:] = []
                dirnames[:] = [d for d in dirnames if d.lower() not in skip]
                for fn in filenames:
                    if fn.lower() in names:
                        hit = os.path.join(dirpath, fn)
                        break
                if hit:
                    break
            if hit:
                break
    _BROWSER_CACHE.update(time=now, path=hit)
    print("[浏览器] 用：", hit)
    return hit


def render_page(url, timeout=90):
    """用外部 Chromium 渲染页面（JS 跑完的 DOM）。找不到浏览器就报错。
    第一次跑会慢（Edge 冷启动 + 建 profile，实测八十多秒），之后再快。"""
    exe = find_browser()
    if not exe:
        raise RuntimeError("没找到 Chrome / Edge")
    persistent = os.path.join(APP_DIR, "_chrome_profile")
    try:
        os.makedirs(persistent, exist_ok=True)
    except Exception:
        persistent = os.path.join(os.environ.get("TEMP") or ".", "dafeiyu_chrome_profile")
    tmpdir = os.path.join(APP_DIR, "_chrome_render")     # 输出都集中放这儿，好清理
    try:
        os.makedirs(tmpdir, exist_ok=True)
    except Exception:
        tmpdir = None
    last = ""
    # 第一轮用常驻 profile；卡住/失败就换一个全新的临时 profile 再来一次（避免 profile 被锁）
    attempts = [(persistent, ()), (persistent, ("--no-sandbox",))]
    extra_profiles = []                      # 临时 profile 用完要删掉，别在磁盘上堆
    try:
        p = tempfile.mkdtemp(prefix="dafeiyu-cr-", dir=tmpdir)   # 放一起，好清理
        extra_profiles.append(p)
        attempts.append((p, ("--no-sandbox",)))
    except Exception:
        pass
    for profile, extra in attempts:
        base = [exe, "--headless=new", "--disable-gpu", "--mute-audio", "--no-first-run",
                "--no-default-browser-check", "--disable-extensions", "--disable-sync",
                "--disable-background-networking", "--disable-component-update",
                "--user-data-dir=" + profile, "--virtual-time-budget=5000"]
        of = ef = None
        try:
            of = tempfile.NamedTemporaryFile(delete=False, suffix=".html", dir=tmpdir)
            ef = tempfile.NamedTemporaryFile(delete=False, suffix=".log", dir=tmpdir)
            of.close()
            ef.close()
            with open(of.name, "w", encoding="utf-8", errors="ignore") as fo, \
                 open(ef.name, "w", encoding="utf-8", errors="ignore") as fe:
                subprocess.run(base + list(extra) + ["--dump-dom", url],
                               stdout=fo, stderr=fe, timeout=timeout,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            html = open(of.name, encoding="utf-8", errors="ignore").read()
            if len(html) > 200:
                for p in extra_profiles:
                    shutil.rmtree(p, ignore_errors=True)
                return html
            last = open(ef.name, encoding="utf-8", errors="ignore").read()[-200:]
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, str(e)[:120])
        finally:
            for f in (of, ef):
                try:
                    if f:
                        os.remove(f.name)
                except Exception:
                    pass
    for p in extra_profiles:
        shutil.rmtree(p, ignore_errors=True)
    raise RuntimeError("渲染失败：%s" % (last or "没有输出"))


def _norm_key(url):
    """归一化链接，用来给两个搜索源的结果去重"""
    try:
        p = urlparse(url)
        host = (p.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return host + (p.path or "/").rstrip("/").lower()
    except Exception:
        return (url or "").lower()


def _parse_bing(html, limit=5):
    out = []
    for block in re.findall(r'(?is)<li class="b_algo".*?</li>', html):
        m = re.search(r'(?is)<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block)
        if not m:
            continue
        link = _decode_bing_url(html_mod.unescape(m.group(1)))
        if not link.startswith("http"):
            continue
        title = _html_to_text(m.group(2)) or link
        snip = ""
        sm = re.search(r"(?is)<p[^>]*>(.*?)</p>", block)
        if sm:
            snip = _html_to_text(sm.group(1))
        out.append({"title": title[:120], "url": link, "snippet": snip[:300]})
        if len(out) >= limit:
            break
    return out


_BROWSER_FETCH = {"fn": None}       # 由 PetWindow 挂上：url -> (ok, dom)，走内嵌真浏览器
_LOGIN_HOOK = {"fn": None}          # 由 PetWindow 挂上：url -> None，把网站的登录页开到界面上


class NeedsLogin(RuntimeError):
    """取回来的是登录页 / 权限页 —— 这种情况不该往上抛普通错误，要明确告诉主人去登录"""


LOGIN_MARKERS = ("请先登录", "请登录后", "需要登录", "登录后查看", "登录以继续",
                 "sign in to continue", "login required", "please log in",
                 "unauthorized", "请先验证", "扫码登录")


def looks_like_login(dom):
    """粗略判断取回来的是不是「要登录 / 没权限」的页面"""
    t = (dom or "").lower()
    if not t:
        return False
    if 'type="password"' in t or "type='password'" in t:
        return True
    return any(k in t for k in LOGIN_MARKERS)


def fetch_with_browser(url, timeout=30):
    """用内嵌的真 Chromium 取页面：带登录态、能过验证。没接上通道就抛错。"""
    fn = _BROWSER_FETCH.get("fn")
    if not fn:
        raise RuntimeError("真浏览器通道没接上")
    ok, dom = fn(url, timeout)
    if not ok or not dom:
        raise RuntimeError(dom or "取页失败")
    return dom


def _open_login_page(url):
    """把需要登录的页面开到界面上 —— 不做桌宠自己的登录界面，
    而是让**网站自己**跳它的登录页（登录、扫码、跳转都归网站管）。"""
    fn = _LOGIN_HOOK.get("fn")
    if not fn:
        return False
    try:
        fn(url)
        return True
    except Exception as e:
        print("[登录] 打开登录页失败:", e)
        return False


def get_page_html(url, timeout=30):
    """取页面 HTML：先走内嵌真浏览器（快、带 Cookie、能过验证），
    不行再退回外部无头 Chromium（慢但更独立）。

    碰到登录页就把网站的登录页开到界面上、**在这儿等主人登录**（默认最多等 3 分钟），
    登录完 Cookie 进了同一个 profile，这里自动重取并继续，主人不用重新提一次要求。
    """
    try:
        dom = fetch_with_browser(url, timeout)
    except Exception as e:
        print("[浏览器] 内嵌通道不行（%s），改用外部无头 Chromium" % str(e)[:60])
    else:
        if not looks_like_login(dom):
            return dom
        host = urlparse(url).netloc or url
        wait = int(_RUNTIME.get("login_wait", 180) or 180)
        if not _open_login_page(url):
            raise NeedsLogin("「%s」需要登录：点右上角「🌐 看网页」在里面登录一次，"
                             "之后我就能读到内容了" % host)
        print("[登录] %s 需要登录，已打开登录页，等主人处理（最多 %d 秒）" % (host, wait))
        deadline = time.time() + max(10, wait)
        while time.time() < deadline:
            time.sleep(4)
            try:
                dom2 = fetch_with_browser(url, timeout)
            except Exception:
                continue
            if dom2 and not looks_like_login(dom2):
                print("[登录] 登录成功，继续干活 ✓")
                return dom2
        raise NeedsLogin("「%s」等了 %d 分钟还没登上（可能没登完，或这个账号没权限）"
                         % (host, max(10, wait) // 60))
    return render_page(url)



def _render_search(query, limit=5):
    """两条抓取通道都被拦时：用 Chromium 渲染 Bing 搜索页再解析"""
    html = get_page_html("https://www.bing.com/search?q=" + quote(query))
    return _parse_bing(html, limit)


def _render_ddg(query, limit=5):
    """用真浏览器打开 DDG —— 抓取被人机验证拦住时靠这个救回来"""
    html = get_page_html("https://html.duckduckgo.com/html/?q=" + quote(query))
    out = []
    for href, inner in _anchors_by_class(html, "result__a")[:limit]:
        href = _ddg_unwrap(href)
        if href.startswith("http"):
            out.append({"title": (_html_to_text(inner) or href)[:120], "url": href, "snippet": ""})
    snips = [_html_to_text(s) for _, s in _anchors_by_class(html, "result__snippet")]
    for i, s in enumerate(snips[:len(out)]):
        out[i]["snippet"] = s[:300]
    return out


def _bing_search(query, limit=5, proxies=None, timeout=15):
    """Bing：www 站才有结果，cn 站现在会跳回首页，所以两个都试"""
    errs = []
    for endpoint in ("https://www.bing.com/search", "https://cn.bing.com/search"):
        try:
            r = _http_request("get", endpoint, proxies, timeout=timeout,
                              params={"q": query, "setlang": "zh-CN"})
            r.raise_for_status()
            out = _parse_bing(r.text, limit)
            if out:
                return out
            errs.append("%s 解析到 0 条" % urlparse(endpoint).netloc)
        except Exception as e:
            errs.append("%s → %s" % (urlparse(endpoint).netloc, type(e).__name__))
    print("[搜索] Bing 各站都不行：%s" % "；".join(errs))
    return []


def _ddg_search(query, limit=5, proxies=None, timeout=12):
    """DuckDuckGo 免 Key：GET 会被 202 人机验证拦住，所以必须用 POST。
    202 + anomaly 页 = DDG 把我们当机器人了（不是网络不通），状态记进 _DDG_STATE。"""
    errs = []
    challenged = False
    # html 版：结果最完整
    try:
        r = _http_request("post", "https://html.duckduckgo.com/html/", proxies, timeout=timeout,
                          data={"q": query})
        r.raise_for_status()
        if r.status_code == 202 or "anomaly" in r.text.lower():
            challenged = True
            errs.append("html 版被人机验证拦住(HTTP %s)" % r.status_code)
        else:
            out = []
            for href, inner in _anchors_by_class(r.text, "result__a")[:limit]:
                href = _ddg_unwrap(href)
                if href.startswith("http"):
                    out.append({"title": (_html_to_text(inner) or href)[:120], "url": href, "snippet": ""})
            snips = [_html_to_text(s) for _, s in _anchors_by_class(r.text, "result__snippet")]
            for i, s in enumerate(snips[:len(out)]):
                out[i]["snippet"] = s[:300]
            if out:
                _DDG_STATE["state"] = "ok"
                _DDG_COOLDOWN["until"] = 0.0
                return out
            errs.append("html 版解析到 0 条(HTTP %s)" % r.status_code)
    except Exception as e:
        errs.append("html 版 → %s" % type(e).__name__)
    # lite 版兜底
    try:
        r = _http_request("post", "https://lite.duckduckgo.com/lite/", proxies, timeout=timeout,
                          data={"q": query})
        r.raise_for_status()
        if r.status_code == 202 or "anomaly" in r.text.lower():
            challenged = True
            errs.append("lite 版被人机验证拦住(HTTP %s)" % r.status_code)
        else:
            out = []
            for href, inner in _anchors_by_class(r.text, "result-link")[:limit]:
                href = _ddg_unwrap(href)
                if href.startswith("http"):
                    out.append({"title": (_html_to_text(inner) or href)[:120], "url": href, "snippet": ""})
            snips = [_html_to_text(s) for _, s in _anchors_by_class(r.text, "result-snippet")]
            for i, s in enumerate(snips[:len(out)]):
                out[i]["snippet"] = s[:300]
            if out:
                _DDG_STATE["state"] = "ok"
                _DDG_COOLDOWN["until"] = 0.0
                return out
            errs.append("lite 版解析到 0 条(HTTP %s)" % r.status_code)
    except Exception as e:
        errs.append("lite 版 → %s" % type(e).__name__)
    _DDG_STATE["state"] = "challenge" if challenged else "fail"
    if challenged:                      # 被拦了就先歇十分钟，别把验证越撞越死
        _DDG_COOLDOWN["until"] = time.time() + 600
    print("[搜索] DDG 两种打法都不行：%s" % "；".join(errs))
    return []


def _pick_search_provider(force=False):
    """（自检用）看看 DDG / Bing 两条通道各自通不通"""
    now = time.time()
    if not force and now - _PROVIDER_CACHE["time"] < 120:
        return _PROVIDER_CACHE["name"]
    lines = collect_lines(force=force)
    ddg_ok = _can(line_for("foreign", lines), "ddg")
    bing_ok = _can(line_for("domestic", lines), "bing")
    name = "both" if (ddg_ok and bing_ok) else ("ddg" if ddg_ok else ("bing" if bing_ok else "none"))
    _PROVIDER_CACHE.update(time=now, name=name)
    return name


def _search_once(name, query, limit, proxies):
    """单条通道 + 单条线路，搜一次"""
    fn = _ddg_search if name == "ddg" else _bing_search
    try:
        return fn(query, limit, proxies) or []
    except Exception as e:
        print("[搜索] %s（%s）失败：%s" % (name, "线路" if proxies else "直连", str(e)[:60]))
        return []


def _lines_for(kind, lines=None):
    """按目标给出要用哪几条线：区域对口的那条优先，再带一条最快的做对冲"""
    lines = lines if lines is not None else collect_lines()
    out = [line_for(kind, lines)]
    for l in sorted([x for x in lines if x.get("ok")], key=lambda x: x.get("ms", 9999)):
        px = l.get("proxy")
        if px not in out:
            out.append(px)
    if None not in out:
        out.append(None)
    return out[:2]                             # 最多两条同时打，别把线路打爆


def _race(name, query, limit, line_options):
    """同一条通道用多条线路同时打，谁先给出结果就用谁（对冲线路抖动）"""
    opts = [o for o in line_options if o is not None] or [None]
    if len(line_options) > len(opts):          # 直连也作为一路候选
        opts.append(None)
    return _first_ok(lambda px: _search_once(name, query, limit, px), opts, workers=len(opts)) or []


def web_search(query, limit=5):
    """DuckDuckGo + Bing 同时搜（每条通道还会在多条线路上对冲），去重后交叉合并"""
    mode = _RUNTIME.get("provider") or "both"
    if mode in ("auto", ""):
        mode = "both"
    lines = collect_lines()
    jobs = []
    ddg_cooling = time.time() < _DDG_COOLDOWN["until"]
    if mode in ("both", "ddg") and not ddg_cooling:
        jobs.append(("ddg", _lines_for("foreign", lines)))
    elif ddg_cooling:
        print("[搜索] DDG 还在人机验证的冷却期，这轮只走 Bing")
    if mode in ("both", "bing"):
        jobs.append(("bing", _lines_for("domestic", lines)))
    if not jobs:
        jobs = [("ddg", _lines_for("foreign", lines)), ("bing", _lines_for("domestic", lines))]
    buckets = {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futs = {pool.submit(_race, name, query, limit, opts): name for name, opts in jobs}
        for f in as_completed(futs):
            name = futs[f]
            try:
                buckets[name] = f.result() or []
            except Exception as e:
                print("[搜索] %s 异常：%s" % (name, str(e)[:60]))
                buckets[name] = []
    # DDG 抓取被人机验证挡住时，用内嵌真浏览器补一次（带着窗口里的 Cookie，能过验证）
    if (not buckets.get("ddg") and mode in ("both", "ddg")
            and _RUNTIME.get("browser_search", True)):
        try:
            got = _render_ddg(query, limit)
            if got:
                buckets["ddg"] = got
                print("[搜索] 真浏览器通道补回 DDG %d 条" % len(got))
        except Exception as e:
            print("[搜索] 真浏览器通道没补上：%s" % str(e)[:70])

    merged, seen = [], set()
    top = max([len(v) for v in buckets.values()] or [0])
    for i in range(top):                       # 两个源交替插入，谁先谁后都公平
        for name in ("ddg", "bing"):
            lst = buckets.get(name) or []
            if i < len(lst):
                it = dict(lst[i])
                it["source"] = name
                k = _norm_key(it.get("url", ""))
                if k and k not in seen:
                    seen.add(k)
                    merged.append(it)
    if not merged:
        print("[搜索] 抓取通道都被拦，改用 Chromium 渲染兜底")
        # 先试 Bing：无头 Chromium 渲染 Bing 是实测可行的；
        # DDG 连无头真浏览器都过不去（实测 93.7s / 0 条），所以放最后
        for tag, fn in (("bing", _render_search), ("ddg", _render_ddg)):
            try:
                got = fn(query, limit)
            except Exception as e:
                print("[搜索] 渲染 %s 兜底失败：%s" % (tag, str(e)[:70]))
                continue
            if got:
                merged = [dict(x, source="render-" + tag) for x in got]
                print("[搜索] 渲染 %s 救回 %d 条" % (tag, len(merged)))
                break
    print("[搜索] 「%s」DDG %d 条 / Bing %d 条 → 合并 %d 条" % (
        query, len(buckets.get("ddg") or []), len(buckets.get("bing") or []), len(merged)))
    return merged[:limit]


def _github_mirror(url):
    """raw.githubusercontent.com 境内直连不通，换成 jsDelivr 镜像"""
    try:
        p = urlparse(url)
        if p.netloc.lower() == "raw.githubusercontent.com":
            bits = p.path.lstrip("/").split("/", 3)
            if len(bits) == 4:
                return "https://cdn.jsdelivr.net/gh/%s/%s@%s/%s" % tuple(bits)
    except Exception:
        pass
    return ""


def fetch_url(url, max_chars=4000):
    """抓网页正文纯文本（太长就截断）；GitHub raw 自动走镜像，代理不通自动改直连"""
    px = current_proxies()
    mirror = _github_mirror(url)
    attempts = [(mirror, px), (url, px)] if mirror else [(url, px)]
    if px:
        attempts.append((url, None))          # 代理是死的也得能抓
    errs = []
    for u, use_px in attempts:
        try:
            r = _http_request("get", u, use_px, timeout=20)
            r.raise_for_status()
            ctype = (r.headers.get("content-type") or "").lower()
            if not any(k in ctype for k in ("html", "text", "json", "xml")):
                return "（这个链接不是网页，类型：%s）" % (ctype or "未知")
            if (not r.encoding) or r.encoding.lower() == "iso-8859-1":
                try:
                    r.encoding = r.apparent_encoding or "utf-8"
                except Exception:
                    r.encoding = "utf-8"
            txt = _html_to_text(r.text) if ("html" in ctype or "xml" in ctype) else r.text
            txt = re.sub(r"\n{2,}", "\n", txt)
            if len(txt) > max_chars:
                txt = txt[:max_chars] + "\n…（已截断）"
            if u != url:
                txt += "\n（原链接直连不通，这是 jsDelivr 镜像内容）"
            return txt or "（这个页面没抓到正文）"
        except Exception as e:
            errs.append("%s%s → %s" % (u[:44], "" if use_px else "(直连)", type(e).__name__))
    raise RuntimeError("；".join(errs) or "抓取失败")



def tool_web_search(query, limit=5):
    try:
        res = web_search(query, limit)
        if not res:
            return json.dumps({"results": [], "note": "没搜到，换个关键词再试"}, ensure_ascii=False)
        return json.dumps({"results": res}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": "搜索失败：%s" % e}, ensure_ascii=False)


def tool_fetch_url(url):
    try:
        return json.dumps({"url": url, "text": fetch_url(url)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": "打不开这个链接：%s" % e}, ensure_ascii=False)


class FoodPanel(QWidget):
    """双击弹出的喂食面板"""

    def __init__(self, on_pick):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(310, 64)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)
        _t = _theme()
        for f in FOODS:
            b = QToolButton()
            b.setText(f)
            b.setFont(QFont("Segoe UI Emoji", 20))
            b.setFixedSize(44, 44)
            b.setStyleSheet(
                "QToolButton{background:rgba(255,255,255,235);border:2px solid %s;"
                "border-radius:22px;} QToolButton:hover{background:%s;border-color:%s;}"
                % (_t["border"], _t["accent_soft"], _t["accent"]))
            b.clicked.connect(lambda _, x=f: on_pick(x))
            lay.addWidget(b)
        close = QToolButton()
        close.setText("✕")
        close.setFont(QFont("Microsoft YaHei UI", 12))
        close.setFixedSize(26, 26)
        close.setStyleSheet("QToolButton{background:rgba(255,255,255,200);border:none;"
                            "border-radius:13px;color:%s;}"
                            "QToolButton:hover{background:%s;color:#fff;}"
                            % (_t["dim"], _t["accent"]))
        close.clicked.connect(self.hide)
        lay.addWidget(close)
        self.setStyleSheet("FoodPanel{background:%s;border-radius:14px;}" % _theme()["panel"])

    def popup_at(self, x, y):
        self.move(int(x - self.width() / 2), int(y - self.height() - 10))
        self.show()
        self.raise_()

# 按钮样式不再写死：见 _theme_btn_style() / _theme_primary_style()（跟着主题走）


class TaskWorker(QObject):
    """后台替主人干活的「分身」：DeepSeek 工具调用循环整个跑在子线程，UI 只收信号"""
    status = Signal(str)
    done = Signal(str, str)      # (正文 markdown, 来源 markdown)
    error = Signal(str)

    def __init__(self, cfg, task_text):
        super().__init__()
        self.cfg = dict(cfg or {})
        self.task_text = task_text or ""
        self.stop_flag = threading.Event()
        self.sources = []

    def _chat(self, messages, tools=None, max_tokens=1200):
        base = str(self.cfg.get("ds_base_url") or DS_BASE_URL).rstrip("/")
        model = self.cfg.get("task_model") or self.cfg.get("ds_model") or DS_MODEL
        payload = {"model": model, "messages": messages,
                   "temperature": 0.3, "max_tokens": max_tokens}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        r = requests.post(base + "/chat/completions",
                          headers={"Authorization": "Bearer " + str(self.cfg.get("ds_api_key", "")),
                                   "Content-Type": "application/json"},
                          json=payload, timeout=90)
        if r.status_code != 200:
            try:
                m = r.json().get("error", {}).get("message", "")
            except Exception:
                m = (r.text or "")[:100]
            raise RuntimeError("API %s: %s" % (r.status_code, str(m)[:90]))
        return r.json()["choices"][0]["message"]

    def _remember(self, items):
        for it in items or []:
            it = it or {}
            u = it.get("url", "")
            t = (it.get("title") or u).replace("]", " ").replace("\n", " ").strip()
            if u and (t, u) not in self.sources:
                self.sources.append((t[:80], u))

    def run(self):
        try:
            messages = [{"role": "system", "content": TASK_SYSTEM},
                        {"role": "user", "content": self.task_text}]
            try:
                rounds = max(1, int(self.cfg.get("task_max_rounds", 4)))
            except Exception:
                rounds = 4
            for i in range(rounds):
                if self.stop_flag.is_set():
                    self.error.emit("已停止")
                    return
                self.status.emit("正在思考…" if i == 0 else "继续整理…")
                msg = self._chat(messages, tools=TASK_TOOLS)
                calls = msg.get("tool_calls") or []
                if not calls:
                    self._finish(msg.get("content") or "")
                    return
                messages.append({"role": "assistant",
                                 "content": msg.get("content") or "",
                                 "tool_calls": calls})
                for k, tc in enumerate(calls):
                    fn = tc.get("function") or {}
                    name = fn.get("name") or ""
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except Exception:
                        args = {}
                    if name == "web_search":
                        q = str(args.get("query", "")).strip()
                        self.status.emit("搜索：" + (q[:24] or "…"))
                        raw = tool_web_search(q)
                        try:
                            self._remember(json.loads(raw).get("results"))
                        except Exception:
                            pass
                    elif name == "fetch_url":
                        u = str(args.get("url", "")).strip()
                        self.status.emit("阅读：" + u[:32])
                        raw = tool_fetch_url(u)
                        self._remember([{"title": u, "url": u}])
                    else:
                        raw = json.dumps({"error": "没有这个工具"}, ensure_ascii=False)
                    messages.append({"role": "tool",
                                     "tool_call_id": tc.get("id") or ("call_%d_%d" % (i, k)),
                                     "content": raw})
            if self.stop_flag.is_set():
                self.error.emit("已停止")
                return
            self.status.emit("写总结…")
            messages.append({"role": "user", "content": "资料够了，请直接给出最终答案（Markdown）。"})
            self._finish(self._chat(messages, tools=None).get("content") or "")
        except Exception as e:
            self.error.emit("%s: %s" % (type(e).__name__, str(e)[:100]))

    def _finish(self, text):
        text = (text or "").strip()
        if not text:
            self.error.emit("分身没给出内容")
            return
        src = ""
        # 它自己已经标了来源就不再附一份 —— 附的那份常混进搜索结果里的无关页面
        if self.sources and "http" not in text:
            src = "\n\n---\n\n**来源**\n" + "\n".join(
                "- [%s](%s)" % (t, u) for t, u in self.sources[:6])
        self.done.emit(text, src)


class NetCheckWorker(QObject):
    """联网自检：报告当前走的代理、各站点通不通、实际用的搜索通道"""
    status = Signal(str)
    done = Signal(str, str)
    error = Signal(str)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = dict(cfg or {})

    def run(self):
        try:
            lines = []
            self.status.emit("探测线路…")
            try:
                # 一分钟内刚测过就直接复用，免得连点「自检」把 DDG 越撞越狠
                fresh = (time.time() - _LINES_CACHE["time"]) > 60
                lines.append("**线路（按出口 IP 自动分类）**")
                lines.append(line_report(force=fresh))
            except Exception as e:
                lines.append("线路探测失败：%s" % str(e)[:60])
            exe = find_browser()
            lines.append("\n**外部浏览器**：%s" % (exe or "没找到 Chrome / Edge"))
            lines.append("**内嵌 Chromium(QtWebEngine)**：%s" % ("可用 ✓" if WEBENGINE_OK else "不可用 ✗"))
            lines.append("**内嵌浏览器身份**：UA %s；Cookie %s"
                         % ("已伪装成普通 Chrome ✓" if "QtWebEngine" not in CHROME_UA else "仍是 QtWebEngine ✗",
                            "强制持久化 ✓"))
            lines.append("**真浏览器搜索通道**：%s"
                         % ("已接上 ✓（DDG 抓取被拦时用它补）" if _BROWSER_FETCH.get("fn")
                            else "没接上 ✗"))
            fx = line_for("foreign")
            dm = line_for("domestic")
            lines.append("\n**站点连通性**")
            for label, url, px in (
                    ("Bing 网页", "https://www.bing.com/search?q=test", dm),
                    ("GitHub 网页", "https://github.com/deepseek-ai/DeepSeek-V3", fx),
                    ("GitHub raw 镜像 jsDelivr",
                     "https://cdn.jsdelivr.net/gh/deepseek-ai/DeepSeek-V3@main/README.md", fx)):
                self.status.emit("测试：" + label)
                try:
                    r = _http_request("get", url, px, timeout=12)
                    lines.append("- %s：%s" % (label, "✓" if r.status_code == 200 else "HTTP %s" % r.status_code))
                except Exception as e:
                    lines.append("- %s：✗ %s" % (label, type(e).__name__))
            self.status.emit("看两条搜索通道各自通不通…")
            good = [l for l in collect_lines() if l.get("ok")]      # 复用线路表里刚测好的结果
            ddg_ok = any(l.get("ddg") for l in good)
            bing_ok = any(l.get("bing") for l in good)
            if ddg_ok:
                lines.append("- DuckDuckGo：✓ 可用")
            elif _DDG_STATE.get("state") == "challenge":
                lines.append("- DuckDuckGo：⚠ **抓取被人机验证拦住**（HTTP 202 anomaly）——"
                             "不是你魔法的问题，我这轮会自动只走 Bing。"
                             "想看 DDG 内容可以点「🌐 看网页」用真浏览器窗口打开；"
                             "另外抓取被拦只是临时的，歇一阵子通常自己就恢复了")
            else:
                lines.append("- DuckDuckGo：✗ 不通（境外线路没通 / 没开魔法）")
            lines.append("- Bing：%s（快速探测，短超时偏保守）" % ("✓ 可用" if bing_ok else "✗ 探测没通"))
            if not ddg_ok and bing_ok:
                lines.append("  （DDG 挂了也不影响用：搜索会自动只走 Bing）")
            self.status.emit("真搜一次（两个源合并）…")
            try:
                res = web_search("DeepSeek V3 发布时间", 5)
                srcs = {}
                for r in res:
                    k = r.get("source", "?")
                    srcs[k] = srcs.get(k, 0) + 1
                lines.append("- **实际搜索**：%d 条（%s）" % (
                    len(res), "，".join("%s %d" % (k, v) for k, v in srcs.items()) or "无"))
                if res and not (ddg_ok or bing_ok):
                    lines.append("  注：快速探测都把两条通道标了不通，但这次真搜还是拿到了结果 ——"
                                 "探测用 6 秒短超时，只是偏保守")
                if res:
                    lines.append("  首条：%s" % str(res[0].get("title", ""))[:60])
            except Exception as e:
                lines.append("- 搜索：✗ %s" % str(e)[:70])
            if exe:
                self.status.emit("测试无头渲染…")
                try:
                    html = render_page("https://www.bing.com/search?q=%E6%B5%8B%E8%AF%95", timeout=40)
                    lines.append("- **无头渲染**：✓ 拿到 %d 字节，解析出 %d 条"
                                 % (len(html), len(_parse_bing(html, 5))))
                except Exception as e:
                    lines.append("- **无头渲染**：✗ %s" % str(e)[:70])
            lines.append("\n> `config.json`：`search_provider` 填 both/ddg/bing；`proxy` 固定代理；"
                         "`proxy_list` 加线路；`chrome_path` 指定浏览器；`chrome_search_dirs` 改扫描目录")
            self.done.emit("\n".join(lines), "")
        except Exception as e:
            self.error.emit("%s: %s" % (type(e).__name__, str(e)[:100]))


def _esc(text):
    return html_mod.escape(str(text or ""))


def _md_to_html(md):
    """Markdown → HTML，用来把分身的回复排进对话记录"""
    try:
        doc = QTextDocument()
        doc.setMarkdown(md or "")
        return doc.toHtml()
    except Exception:
        return "<pre>%s</pre>" % _esc(md)


# ---------- 定位：系统授权优先，失败退回 IP 粗略定位 ----------
LOCATE_PS = r"""
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
[Windows.Devices.Geolocation.Geolocator, Windows.Devices.Geolocation, ContentType = WindowsRuntime] | Out-Null
[Windows.Devices.Geolocation.Geoposition, Windows.Devices.Geolocation, ContentType = WindowsRuntime] | Out-Null
[Windows.Devices.Geolocation.GeolocationAccessStatus, Windows.Devices.Geolocation, ContentType = WindowsRuntime] | Out-Null
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
$g = New-Object Windows.Devices.Geolocation.Geolocator
try { $g.DesiredAccuracyInMeters = 300 } catch { }
$op = [Windows.Devices.Geolocation.Geolocator]::RequestAccessAsync()
$t = $asTask.MakeGenericMethod([Windows.Devices.Geolocation.GeolocationAccessStatus]).Invoke($null, @($op))
$t.Wait(20000) | Out-Null
$st = "$($t.Result)"
if ($st -ne 'Allowed') { Write-Output "DENIED:$st"; exit 0 }
$op2 = $g.GetGeopositionAsync()
$t2 = $asTask.MakeGenericMethod([Windows.Devices.Geolocation.Geoposition]).Invoke($null, @($op2))
$t2.Wait(25000) | Out-Null
$c = $t2.Result.Coordinate
Write-Output ("OK:{0},{1},{2}" -f $c.Point.Position.Latitude, $c.Point.Position.Longitude, $c.Accuracy)
"""


def locate_by_system(timeout=55):
    """走 Windows 系统定位（**会弹系统授权框**）。

    返回 (结果, 失败原因)：结果形如 {"lat":.., "lon":.., "src":"系统定位"}。
    """
    if os.name != "nt":
        return None, "系统定位只支持 Windows"
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", LOCATE_PS],
                             capture_output=True, timeout=timeout,
                             creationflags=0x08000000)
        # Windows PowerShell 的输出可能是 GBK（中文系统），别用 text=True 硬按 UTF-8 解
        raw = (out.stdout or b"") + b"\n" + (out.stderr or b"")
        txt = ""
        for enc in ("utf-8", "gbk", "mbcs"):
            try:
                txt = raw.decode(enc)
                break
            except Exception:
                continue
        if not txt:
            txt = raw.decode("utf-8", "replace")
        txt = txt.strip()
    except subprocess.TimeoutExpired:
        return None, "系统定位超时（可能没开位置服务）"
    except Exception as e:
        return None, "系统定位没跑起来：%s" % str(e)[:60]
    line = ""
    for ln in txt.splitlines():
        ln = ln.strip()
        if ln.startswith("OK:") or ln.startswith("DENIED:"):
            line = ln
    if line.startswith("OK:"):
        try:
            lat, lon, acc = (line[3:].split(",") + ["", "", ""])[:3]
            return {"lat": float(lat), "lon": float(lon), "acc": acc, "src": "系统定位"}, ""
        except Exception as e:
            return None, "系统定位结果解析失败：%s" % str(e)[:40]
    if line.startswith("DENIED:"):
        key = line.split(":", 1)[1].strip()
        why = {"Denied": "Windows 里「允许桌面应用访问你的位置」是关着的"
                        "（设置 → 隐私和安全性 → 位置 → 打开位置服务 + 允许桌面应用）",
               "Disabled": "Windows 的位置服务是关着的（设置 → 隐私和安全性 → 位置）",
               "Unspecified": "系统没给出授权结果"}.get(key, key)
        return None, "系统定位没授权：%s" % why
    return None, "系统定位没返回结果（%s）" % (txt[:60].replace("\n", " ") or "空输出")


def locate_by_ip(timeout=8):
    """退回方案：按出口 IP 粗略定位（不弹授权，只到城市级）"""
    urls = ("http://ip-api.com/json/?fields=status,city,regionName,country,lat,lon&lang=zh-CN",
            "https://api.ip.sb/geoip",
            "https://myip.ipip.net/json")
    for url in urls:
        try:
            r = requests.get(url, timeout=timeout, proxies=current_proxies() or None,
                             headers={"User-Agent": "Mozilla/5.0"})
            j = r.json()
            if not isinstance(j, dict):
                continue
            data = j.get("data") if isinstance(j.get("data"), dict) else j
            city = data.get("city") or data.get("regionName") or ""
            lat = data.get("lat", data.get("latitude"))
            lon = data.get("lon", data.get("longitude"))
            if city or lat:
                return {"city": city, "lat": lat, "lon": lon, "src": "IP 粗略定位"}
        except Exception:
            continue
    return None


# ============ 视频动画（素材来自 PC2005-cloud/dsh-pet，MIT/禁止商用，须署名）============
# 106 个 VP9-alpha 透明 webm，放在 anim/ 目录。用内嵌 Chromium 播 ——
# 和 dsh-pet 桌面端一样的做法（透明置顶小窗 + <video>）。
ANIM_DIR = os.path.join(APP_DIR, "anim")
ANIM_POOLS = {
    "待机": ["待机呼吸休闲"],
    "转身": ["东张西望"],
    "拖拽": ["被鼠标拖拽悬空反馈"],
    "点击回应": ["点击回应-开心跃动", "点击回应-害羞惊讶", "点击回应-傲娇生气",
                 "点击回应-挠痒咯咯笑", "点击回应-元气挥手"],
    "走动": ["螃蟹走路", "原地漂浮踏步", "原地左转奔跑"],
    "卖萌": ["悠闲哼歌", "超大伸懒腰", "原地敲击桌面互动", "原地重力下蹲压缩", "哈欠连天",
             "原地小憩沉眠", "女仆屈膝礼仪", "被吓一跳", "小幅度原地360度旋转展示",
             "偷吃零食被抓住", "用鲸鱼尾巴拍打地面", "打瞌睡被惊醒", "照镜子", "整体换装试色",
             "轻快记录", "写代码", "摇扇纳凉", "晨间刷牙"],
    "玩耍": ["原地专心玩魔方", "原地蹲下玩玩具汽车", "鲸鱼吐泡泡特效", "原地跳跃抓碎头顶物品",
             "玩游戏气急败坏", "玩水枪", "小提琴演奏", "蓝鲸现世", "优雅女仆舞", "轻快摇摆舞",
             "可爱宅舞", "吹气球", "动物环绕", "放风筝", "拆礼物", "变鸽子", "扑克魔术",
             "抽陀螺", "吹笛子", "蝴蝶蜜蜂环绕头顶开花", "撸猫", "凭空生花", "骑木马",
             "三球抛接", "踢毽子", "下五子棋", "荡秋千"],
    "吃什么": ["吃白饭", "大口吃零食", "吃Token", "吃早餐", "吃午餐", "吃晚餐", "吃冰淇淋融化",
               "吃大闸蟹", "吃糖葫芦", "吃长寿面", "吃西瓜", "涮火锅"],
    "时节": ["被落叶淹没", "中秋赏月吃月饼", "堆雪人", "放烟花", "吃粽子", "吃年糕", "吃青团",
             "吃腊八粥", "吃重阳糕", "收红包", "写福字", "穿针乞巧", "舞狮头", "讨糖南瓜灯",
             "插茱萸赏菊", "放河灯", "萌化小幽灵", "装点圣诞树", "放孔明灯", "吃汤圆", "吃饺子"],
    "文字": ["是啊，吃什么", "深度思考碎碎念"],
    "碎碎念": ["碎碎念-擦桌碎碎念", "碎碎念-发呆碎碎念", "碎碎念-对屏碎碎念"],
    "工作状态": ["工作状态-思考冒泡", "工作状态-忙碌点按", "工作状态-清点归档",
                 "工作状态-原地踱步张望", "工作状态-雀跃庆祝", "工作状态-垂头叹气冒汗"],
    "余额": ["余额-钱袋满溢", "余额-金袋叮当", "余额-钱袋如常", "余额-数金皱眉", "余额-袋空如洗",
             "余额-分文不剩"],
}
# 我们原有动作键 → 视频 clip（视频模式下用这套）
ACTION_TO_CLIP = {
    "sway": "待机呼吸休闲", "float": "原地漂浮踏步", "look": "东张西望",
    "stretch": "超大伸懒腰", "nod": "原地敲击桌面互动", "turn": "小幅度原地360度旋转展示",
    "shiver": "用鲸鱼尾巴拍打地面", "spin": "小幅度原地360度旋转展示", "mirror": "照镜子",
    "happy": "点击回应-开心跃动", "shy": "点击回应-害羞惊讶", "wave": "点击回应-元气挥手",
    "puff": "点击回应-傲娇生气", "tickle": "点击回应-挠痒咯咯笑", "think": "工作状态-思考冒泡",
    "droop": "工作状态-垂头叹气冒汗", "squash": "原地重力下蹲压缩",
    "bump": "点击回应-害羞惊讶",
}
VIDEO_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;padding:0;background:transparent;overflow:hidden;}
video{position:fixed;left:0;top:0;width:100%;height:100%;object-fit:contain;
      background:transparent;pointer-events:none;}
</style></head><body><video id="v" playsinline preload="auto"></video><script>
const v=document.getElementById('v');
window.__frameSerial=0; window.__lastCaptured=-1;
if(v.requestVideoFrameCallback){
  const trackFrame=()=>{window.__frameSerial++;v.requestVideoFrameCallback(trackFrame);};
  v.requestVideoFrameCallback(trackFrame);
}
window.__st={name:"",ended:false,err:"",frameReady:false};
v.addEventListener('ended',()=>{window.__st.ended=true;});
v.addEventListener('error',()=>{window.__st.err=String((v.error&&v.error.code)||-1);});
v.addEventListener('loadstart',()=>{window.__st.frameReady=false;});
v.addEventListener('loadeddata',()=>{window.__st.frameReady=true;});
window.playClip=function(name,loop){
  window.__lastCaptured=-1;
  window.__st={name:name,ended:false,err:"",frameReady:false};
  v.loop=!!loop; v.src=encodeURI(name)+".webm";
  v.play().catch(e=>{window.__st.err=String(e);});
  return true;
};
window.setMirror=function(on){v.style.transform=on?"scaleX(-1)":"none";};
window.videoInfo=function(){return {w:v.videoWidth,h:v.videoHeight,t:v.currentTime,
  dur:v.duration||0,ended:window.__st.ended,err:window.__st.err,name:window.__st.name,
  frameReady:window.__st.frameReady,readyState:v.readyState};};
window.measureAlpha=function(){
  try{
    if(!v.videoWidth) return null;
    const c=document.createElement('canvas'); c.width=v.videoWidth; c.height=v.videoHeight;
    const g=c.getContext('2d'); g.drawImage(v,0,0);
    const d=g.getImageData(0,0,c.width,c.height).data;
    let x0=c.width,y0=c.height,x1=-1,y1=-1;
    for(let y=0;y<c.height;y+=2){for(let x=0;x<c.width;x+=2){
      if(d[(y*c.width+x)*4+3]>12){if(x<x0)x0=x;if(x>x1)x1=x;if(y<y0)y0=y;if(y>y1)y1=y;}}}
    if(x1<0) return null;
    return {w:c.width,h:c.height,x0:x0/c.width,y0:y0/c.height,x1:x1/c.width,y1:y1/c.height};
  }catch(e){return {err:String(e)};}
};
</script></body></html>"""


def scan_anims():
    """扫 anim/ 目录，返回实际存在的 clip 名集合（缺文件时优雅降级回立绘）"""
    try:
        return {os.path.splitext(f)[0] for f in os.listdir(ANIM_DIR) if f.lower().endswith(".webm")}
    except Exception:
        return set()


_VIDEO_SERVER = {"port": 0, "srv": None}


class _AnimHandler(SimpleHTTPRequestHandler):
    """只服务 anim/ 目录的本地小服务器（**仅监听 127.0.0.1**）。

    Chromium 直接播 file:// 视频有坑（页面会被导航走），走本机 http 最稳；
    顺带把播放页也从这里发，同源、无跨域问题。
    """

    server_version = "dafeiyu-anim/1.0"

    def log_message(self, *a):
        pass

    def translate_path(self, path):
        try:
            from urllib.parse import unquote, urlparse
            rel = unquote(urlparse(path).path).lstrip("/")
            full = os.path.normpath(os.path.join(ANIM_DIR, rel))
            root = os.path.normpath(ANIM_DIR)
            if not full.startswith(root):
                return os.path.join(root, "__denied__")      # 防目录穿越
            # 同名高清素材优先，原 360p 素材继续作为兼容兜底。
            hd = os.path.normpath(os.path.join(ANIM_DIR, "hd", rel))
            if full.lower().endswith(".webm") and os.path.isfile(hd):
                return hd
            return full
        except Exception:
            return os.path.join(ANIM_DIR, "__denied__")

    def do_GET(self):
        if self.path.split("?")[0].rstrip("/") in ("/player", "/player.html"):
            body = VIDEO_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except Exception:
                pass
            return
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            self.send_error(404)
            return
        size = os.path.getsize(path)
        ctype = "video/webm" if path.lower().endswith(".webm") else "application/octet-stream"
        start, end, code = 0, max(0, size - 1), 200
        rng = self.headers.get("Range") or ""
        if rng.startswith("bytes="):
            try:
                s, _, e = rng[6:].partition("-")
                start = int(s) if s.strip() else 0
                end = int(e) if e.strip() else size - 1
                start = max(0, min(start, size - 1))
                end = max(start, min(end, size - 1))
                code = 206
            except Exception:
                start, end, code = 0, max(0, size - 1), 200
        length = end - start + 1
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if code == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(65536, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except Exception:
            pass


def start_anim_server():
    """起素材服务器（重复调用只起一个），返回端口；失败返回 0"""
    if _VIDEO_SERVER["srv"] is not None:
        return _VIDEO_SERVER["port"]
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", 0), _AnimHandler)
        srv.daemon_threads = True
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _VIDEO_SERVER["srv"], _VIDEO_SERVER["port"] = srv, port
        print("[视频] 素材服务器：127.0.0.1:%d（仅本机）" % port)
        return port
    except Exception as e:
        print("[视频] 素材服务器起不来:", e)
        return 0


VIDEO_INFO_JS = ("JSON.stringify((function(){var v=document.querySelector('video');"
                 "if(!v) return null;"
                 "var frame='',fx=0,fy=0,fw=0,fh=0;var serial=v.requestVideoFrameCallback?window.__frameSerial:"
                 "v.getVideoPlaybackQuality().totalVideoFrames;"
                 "if(v.readyState>=2&&v.videoWidth&&serial!==window.__lastCaptured){"
                 "var c=window.__frameCanvas||(window.__frameCanvas=document.createElement('canvas'));"
                 "var cw=Math.min(v.videoWidth,window.__captureWidth||v.videoWidth);"
                 "var ch=Math.round(cw*v.videoHeight/v.videoWidth);"
                 "if(c.width!==cw)c.width=cw;if(c.height!==ch)c.height=ch;"
                 "var g=c.getContext('2d');g.imageSmoothingEnabled=true;g.imageSmoothingQuality='high';"
                 "g.clearRect(0,0,c.width,c.height);g.drawImage(v,0,0,c.width,c.height);"
                 "var a=g.getImageData(0,0,c.width,c.height).data;"
                 "var x0=c.width,y0=c.height,x1=-1,y1=-1;"
                 "for(var y=0;y<c.height;y+=2){for(var x=0;x<c.width;x+=2){"
                 "if(a[(y*c.width+x)*4+3]>4){if(x<x0)x0=x;if(x>x1)x1=x;if(y<y0)y0=y;if(y>y1)y1=y;}}}"
                 "if(x1>=0){fx=Math.max(0,x0-4);fy=Math.max(0,y0-4);"
                 "var right=Math.min(c.width,x1+5),bottom=Math.min(c.height,y1+5);"
                 "var cc=window.__cropCanvas||(window.__cropCanvas=document.createElement('canvas'));"
                 "cc.width=right-fx;cc.height=bottom-fy;"
                 "cc.getContext('2d').drawImage(c,fx,fy,cc.width,cc.height,0,0,cc.width,cc.height);"
                 "frame=cc.toDataURL('image/png').split(',')[1];fw=c.width;fh=c.height;}"
                 "window.__lastCaptured=serial;}"
                 "return {w:v.videoWidth,h:v.videoHeight,t:v.currentTime,dur:v.duration||0,"
                 "ended:!!v.ended,err:(window.__st&&window.__st.err)||'',"
                 "name:(window.__st&&window.__st.name)||'',frame:frame,frameX:fx,frameY:fy,frameW:fw,frameH:fh,"
                 "frameReady:!!(window.__st&&window.__st.frameReady),readyState:v.readyState};})())")
VIDEO_MEASURE_JS = (
    "(function(){try{var v=document.querySelector('video');"
    "if(!v||!v.videoWidth||v.readyState<2) return null;"
    "var c=document.createElement('canvas');c.width=v.videoWidth;c.height=v.videoHeight;"
    "var g=c.getContext('2d');g.drawImage(v,0,0);"
    "var d=g.getImageData(0,0,c.width,c.height).data;"
    "var x0=c.width,y0=c.height,x1=-1,y1=-1;"
    "for(var y=0;y<c.height;y+=2){for(var x=0;x<c.width;x+=2){"
    "if(d[(y*c.width+x)*4+3]>12){if(x<x0)x0=x;if(x>x1)x1=x;if(y<y0)y0=y;if(y>y1)y1=y;}}}"
    "if(x1<0) return null;"
    "return JSON.stringify({w:c.width,h:c.height,x0:x0/c.width,y0:y0/c.height,"
    "x1:x1/c.width,y1:y1/c.height});}catch(e){return JSON.stringify({err:String(e)});}})()")

THEMES = {
    "pink": {
        "name": "粉色",
        "window": "#fff6f9", "base": "#ffffff", "text": "#3d2b33", "dim": "#a98795",
        "placeholder": "#c9a6b4", "button": "#ffeef4", "button_hover": "#ffe0ea",
        "border": "#ffd6e3", "accent": "#ff6f9c", "accent_dark": "#e8557f",
        "accent_soft": "#ffe3ec", "sel": "#ffd0e2", "sel_text": "#3d2b33",
        "panel": "rgba(58, 22, 36, 0.92)", "panel_light": "rgba(255, 246, 250, 0.95)",
        "panel_border": "rgba(255, 150, 185, 0.40)",
        "bubble_bg": (255, 250, 252, 240), "bubble_fg": (72, 44, 57),
        "bubble_inner_bg": (255, 226, 236, 235), "bubble_inner_fg": (198, 106, 140),
        "label_user": "#e8557f", "label_bot": "#b0569c",
        "overlay_bg": (26, 12, 20, 246), "overlay_card": "#2b1620",
        "overlay_border": "#4d2b39", "overlay_text": "#ffe9f1",
        "overlay_dim": "#e3c2ce", "overlay_faint": "#a9848f",
        "overlay_field": "#361c27", "overlay_field_border": "#5d3547",
    },
    "system": {
        "name": "跟随系统",
        "window": "#f7f8fc", "base": "#ffffff", "text": "#1a1a1a", "dim": "#8a90a2",
        "placeholder": "#9aa0ad", "button": "#f2f4fa", "button_hover": "#e8ecf9",
        "border": "#dfe3ee", "accent": "#5686fe", "accent_dark": "#4575ed",
        "accent_soft": "#e8ecf9", "sel": "#cfe0ff", "sel_text": "#1a1a1a",
        "panel": "rgba(40, 40, 60, 0.92)", "panel_light": "rgba(255, 255, 255, 0.92)",
        "panel_border": "rgba(0, 0, 0, 0.06)",
        "bubble_bg": (255, 255, 255, 235), "bubble_fg": (60, 60, 80),
        "bubble_inner_bg": (232, 232, 238, 235), "bubble_inner_fg": (125, 125, 138),
        "label_user": "#1a4fd6", "label_bot": "#0a7f5a",
        "overlay_bg": (9, 11, 18, 246), "overlay_card": "#151927",
        "overlay_border": "#2a3350", "overlay_text": "#f2f5ff",
        "overlay_dim": "#c9d3ee", "overlay_faint": "#8d99b8",
        "overlay_field": "#1d2333", "overlay_field_border": "#33406a",
    },
}


def _theme():
    """当前主题的颜色表（config.json 里 theme: pink / system）"""
    try:
        return THEMES.get(str(_RUNTIME.get("theme") or "pink").lower(), THEMES["pink"])
    except Exception:
        return THEMES["pink"]


def _ui_palette():
    """按当前主题给一套完整调色板。

    文字颜色一律写死：系统是深色主题时 Qt 默认文字色接近白色，
    白底上就会出现「打了字却看不见」—— 从根上堵住。
    """
    t = _theme()
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(t["window"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(t["base"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(t["accent_soft"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(t["button"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(t["base"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(t["accent"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    try:
        pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(t["placeholder"]))
    except Exception:
        pass
    return pal


def _theme_btn_style():
    """次要按钮（工具条那种小圆角按钮）"""
    t = _theme()
    return ("QPushButton{background:%s;border:1px solid %s;border-radius:14px;"
            "padding:5px 14px;color:%s;font-size:12px;font-family:'Microsoft YaHei UI';}"
            "QPushButton:hover{background:%s;border-color:%s;}"
            "QPushButton:pressed{background:%s;}"
            % (t["button"], t["border"], t["text"], t["button_hover"], t["accent"], t["sel"]))


def _theme_primary_style():
    """主按钮（发送 / 放我走）"""
    t = _theme()
    return ("QPushButton{background:%s;color:white;border:none;border-radius:14px;"
            "font-size:12px;font-family:'Microsoft YaHei UI';}"
            "QPushButton:hover{background:%s;}" % (t["accent"], t["accent_dark"]))


def _theme_native_style():
    """右键菜单 / 提示框 / 消息框这类「原生」部件不听 Qt 调色板

    Windows 深色主题下它们会自己画白字 —— 底是我们给的浅粉，字是系统给的白，
    结果就是「粉底白字看不见」。只能直接写样式把这些颜色也钉在主题上。
    """
    t = _theme()
    return (
        "QMenu{background:%(base)s;border:1px solid %(border)s;padding:5px;}"
        "QMenu::item{color:%(text)s;padding:5px 28px 5px 26px;border-radius:6px;}"
        "QMenu::item:selected{background:%(accent)s;color:#ffffff;}"
        "QMenu::item:disabled{color:%(dim)s;}"
        "QMenu::separator{height:1px;background:%(border)s;margin:4px 10px;}"
        "QMenu::right-arrow{width:10px;height:10px;}"
        "QToolTip{background:%(base)s;color:%(text)s;border:1px solid %(border)s;padding:3px;}"
        # 弹框里的按钮和输入框也归原生样式管，同样得钉死
        "QDialog{background:%(window)s;}"
        "QDialog QLabel{color:%(text)s;}"
        "QDialog QLineEdit,QDialog QPlainTextEdit,QDialog QSpinBox,QDialog QComboBox{"
        "background:%(base)s;color:%(text)s;border:1px solid %(border)s;border-radius:6px;"
        "padding:3px 6px;selection-background-color:%(sel)s;selection-color:%(sel_text)s;}"
        "QDialog QPushButton{background:%(button)s;border:1px solid %(border)s;"
        "border-radius:8px;padding:5px 16px;color:%(text)s;min-width:60px;}"
        "QDialog QPushButton:hover{background:%(button_hover)s;border-color:%(accent)s;}"
        "QDialog QPushButton:pressed{background:%(sel)s;}"
        "QDialog QPushButton:default{border:1px solid %(accent)s;}"
        "QDialog QCheckBox,QDialog QRadioButton{color:%(text)s;}"
        % t
    )


def _fix_text_colors(widget, text=None, placeholder=None, base=None):
    """给单个控件写死文字 / 底色 / 占位符颜色（占位符颜色样式表管不到，只能走 palette）"""
    t = _theme()
    try:
        pal = widget.palette()
        pal.setColor(QPalette.ColorRole.Text, QColor(text or t["text"]))
        pal.setColor(QPalette.ColorRole.Base, QColor(base or t["base"]))
        try:
            pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(placeholder or t["placeholder"]))
        except Exception:
            pass
        widget.setPalette(pal)
    except Exception as e:
        print("设置文字颜色失败:", e)


class _LoginDialog(QDialog):
    """网站要求登录认证（HTTP 认证）时弹出来填用户名 / 密码。

    只用在这一次请求上，**不写磁盘**；要长期保留登录状态，
    靠的是浏览器 profile 里的 Cookie（网站自己的「记住我」）。
    """

    def __init__(self, parent, host, note=""):
        super().__init__(parent)
        self.setWindowTitle("需要登录")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumWidth(380)
        self.setPalette(_ui_palette())          # 弹窗也跟主题走，且不受系统深色主题影响
        _t = _theme()
        self.setStyleSheet("QDialog{background:%s;}" % _t["window"])
        lay = QVBoxLayout(self)
        head = QLabel("「%s」要求登录认证" % host)
        head.setWordWrap(True)
        head.setStyleSheet("color:%s;font-size:14px;font-weight:bold;" % _t["text"])
        lay.addWidget(head)
        if note:
            tip = QLabel(note)
            tip.setWordWrap(True)
            tip.setStyleSheet("color:%s;font-size:12px;" % _t["dim"])
            lay.addWidget(tip)
        form = QFormLayout()
        self.user = QLineEdit()
        self.user.setPlaceholderText("用户名 / 账号")
        self.pwd = QLineEdit()
        self.pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd.setPlaceholderText("密码")
        for w in (self.user, self.pwd):           # 这两格要能看清（要打密码）
            _fix_text_colors(w)
        form.addRow("用户名", self.user)
        form.addRow("密码", self.pwd)
        lay.addLayout(form)
        hint = QLabel("只在本次请求里使用，不会保存到磁盘。"
                      "想让下次免登录，就在网页上勾它自己的「记住我」。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:%s;font-size:11px;" % _t["dim"])
        lay.addWidget(hint)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setStyleSheet(_theme_btn_style())
        cancel.clicked.connect(self.reject)
        ok = QPushButton("登录")
        ok.setStyleSheet(_theme_primary_style())
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def values(self):
        return self.user.text(), self.pwd.text()


class _InputBox(QPlainTextEdit):
    """Enter 发送，Shift+Enter 换行"""

    def __init__(self, on_send):
        super().__init__()
        self._on_send = on_send

    def keyPressEvent(self, e):
        if (e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
            self._on_send()
            return
        super().keyPressEvent(e)


class AvatarWindow(QWidget):
    """「分身」就这一个窗口：对话、任务、看网页全在这儿，不再到处弹小窗。

    网页那边是一个「放开权限」的真 Chromium：UA 去掉了 QtWebEngine 特征、强制持久化
    Cookie（登录态和你手动过掉的人机验证都留得住），能开本地文件 / 下载 / 看 PDF /
    弹新窗口 / 全屏，所以它比脚本抓取更容易过掉网站的验证。
    """

    def __init__(self, home=None):
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle("🐟 分身")
        self.resize(980, 730)
        self.setStyleSheet("QWidget{background:%s;}" % _theme()["window"])
        self._force_light_theme()
        th = _theme()                # 当前主题的颜色表

        self.on_send = None          # PetWindow 挂上：真正去干活
        self.on_stop = None
        self.on_selfcheck = None
        self._last_answer = ""
        self.log_cache = ""          # 纯文本全文，供「复制」兜底
        self.web = None              # 内嵌 Chromium，按需创建（省内存）
        self.profile = None
        self._result_urls = []       # 上一次搜索的来源，供 ◀ ▶ 逐个翻看
        self._result_idx = -1
        self.engine = (_RUNTIME.get("search_engine") or "ddg").lower()
        if self.engine not in SEARCH_ENGINES:
            self.engine = "ddg"
        self.home = home or SEARCH_ENGINES[self.engine][2]

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        self._lay = lay

        head = QHBoxLayout()
        head.setSpacing(6)
        self.title = QLabel("🐟 分身")
        self.title.setStyleSheet("color:%s;font-size:15px;font-weight:bold;"
                                 "font-family:'Microsoft YaHei UI';" % th["text"])
        head.addWidget(self.title)
        self.status = QLabel("待命")
        self.status.setStyleSheet("color:%s;font-size:12px;font-family:'Microsoft YaHei UI';"
                                  % th["accent"])
        head.addWidget(self.status)
        head.addStretch(1)
        self.view_btn = QPushButton("🌐 看网页")
        self.check_btn = QPushButton("自检")
        self.copy_btn = QPushButton("复制")
        self.clear_btn = QPushButton("清屏")
        self.stop_btn = QPushButton("停止")
        for b in (self.view_btn, self.check_btn, self.copy_btn, self.clear_btn, self.stop_btn):
            b.setStyleSheet(_theme_btn_style())
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            head.addWidget(b)
        lay.addLayout(head)

        self.log = QTextBrowser()
        self.log.setOpenExternalLinks(False)     # 链接走内嵌 Chromium，不再乱弹系统浏览器
        self.log.setOpenLinks(False)
        self.log.anchorClicked.connect(self._on_anchor)
        self.log.setStyleSheet(
            "QTextBrowser{background:%s;border:1px solid %s;border-radius:12px;"
            "padding:12px;color:%s;font-size:13px;font-family:'Microsoft YaHei UI';}"
            % (th["base"], th["border"], th["text"]))
        lay.addWidget(self.log, 1)

        # ---- 网页模式的工具栏（地址栏 / 搜索引擎 / 结果翻看）----
        self.web_bar = QWidget()
        wb = QHBoxLayout(self.web_bar)
        wb.setContentsMargins(0, 0, 0, 0)
        wb.setSpacing(4)

        def tb(text, tip, slot):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setFixedSize(28, 26)
            b.setStyleSheet(_theme_btn_style())
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            wb.addWidget(b)
            return b

        self.back_btn = tb("←", "后退", lambda: self.web and self.web.back())
        self.fwd_btn = tb("→", "前进", lambda: self.web and self.web.forward())
        self.reload_btn = tb("⟳", "刷新", lambda: self.web and self.web.reload())
        self.home_btn = tb("🏠", "回到起始页", lambda: self.open_url(self.home))
        self.addr = QLineEdit()
        self.addr.setPlaceholderText("网址 / 本地路径（如 D:\\文档\\a.pdf）/ 搜索词，回车")
        self.addr.setStyleSheet(
            "QLineEdit{background:%s;border:1px solid %s;border-radius:8px;"
            "padding:4px 8px;font-size:12px;font-family:'Microsoft YaHei UI';"
            "selection-background-color:%s;selection-color:%s;}"
            % (th["base"], th["border"], th["sel"], th["sel_text"]))
        self._light_text(self.addr)
        self.addr.returnPressed.connect(lambda: self.go(self.addr.text()))
        wb.addWidget(self.addr, 1)
        self.engine_box = QComboBox()
        for key, (name, _tpl, _home) in SEARCH_ENGINES.items():
            self.engine_box.addItem(name, key)
        self.engine_box.setCurrentIndex(max(0, self.engine_box.findData(self.engine)))
        self.engine_box.setStyleSheet("QComboBox{background:%s;border:1px solid %s;"
                                      "border-radius:8px;padding:3px 6px;font-size:12px;}"
                                      "QComboBox QAbstractItemView{background:%s;color:%s;"
                                      "selection-background-color:%s;selection-color:%s;}"
                                      % (th["base"], th["border"], th["base"], th["text"],
                                         th["sel"], th["sel_text"]))
        self._light_text(self.engine_box)
        self.engine_box.currentIndexChanged.connect(self._on_engine_change)
        wb.addWidget(self.engine_box)
        self.prev_res_btn = tb("◀", "看上一条搜索结果", self.prev_result)
        self.next_res_btn = tb("▶", "看下一条搜索结果", self.next_result)
        self.res_label = QLabel("0/0")
        self.res_label.setStyleSheet("color:%s;font-size:11px;" % th["dim"])
        wb.addWidget(self.res_label)
        self.web_bar.hide()
        lay.insertWidget(lay.indexOf(self.log) + 1, self.web_bar)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.input = _InputBox(self._send)
        self.input.setPlaceholderText("跟我说要做什么：查资料 / 总结 / 对比 / 翻译…"
                                      "（Enter 发送，Shift+Enter 换行）")
        self.input.setFixedHeight(72)
        self.input.setStyleSheet(
            "QPlainTextEdit{background:%s;border:1px solid %s;border-radius:10px;"
            "padding:8px;font-size:13px;font-family:'Microsoft YaHei UI';"
            "selection-background-color:%s;selection-color:%s;}"
            % (th["base"], th["border"], th["sel"], th["sel_text"]))
        self._light_text(self.input)
        row.addWidget(self.input, 1)
        self.input.textChanged.connect(self._grow_input)
        self.send_btn = QPushButton("发送")
        self.send_btn.setFixedSize(66, 34)
        self.send_btn.setStyleSheet(_theme_primary_style())
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self._send)
        row.addWidget(self.send_btn, 0, Qt.AlignmentFlag.AlignBottom)
        lay.addLayout(row)

        self.view_btn.clicked.connect(lambda: self.toggle_web())
        self.check_btn.clicked.connect(self.selfcheck)
        self.copy_btn.clicked.connect(self._copy)
        self.clear_btn.clicked.connect(self.clear)
        self.stop_btn.clicked.connect(lambda: self.on_stop and self.on_stop())
        try:      # Ctrl+L 跳地址栏（浏览器习惯），顺手切到网页模式
            QShortcut(QKeySequence("Ctrl+L"), self, activated=self._focus_addr)
        except Exception:
            pass
        self.welcome()

    def _grow_input(self):
        """输入框随内容长高（1~5 行左右），长指令、长文也看得见"""
        try:
            doc = self.input.document()
            lines = max(1, doc.blockCount())
            doc_h = int(doc.size().height())
            if doc_h < lines * 4:          # 还没布局过（比如窗口没显示）时不可信
                doc_h = lines * self.input.fontMetrics().lineSpacing()
            h = max(72, min(170, doc_h + 26))
            if h != self.input.height():
                self.input.setFixedHeight(h)
        except Exception:
            pass

    def _focus_addr(self):
        try:
            self.toggle_web()
            self.addr.setFocus()
            self.addr.selectAll()
        except Exception:
            pass

    def _force_light_theme(self):
        """这个窗口跟当前主题走 → 写死一套调色板（详见 _ui_palette）"""
        try:
            self.setPalette(_ui_palette())
        except Exception as e:
            print("设置浅色调色板失败:", e)

    def _light_text(self, widget, text=None, placeholder=None):
        """给单个控件写死文字颜色（占位符颜色样式表管不到，得走 palette）"""
        _fix_text_colors(widget, text, placeholder)

    # ---------- 显示 ----------
    def welcome(self):
        self.log.clear()
        self.log_cache = ""
        self._last_answer = ""
        self._last_note = None
        self.append_note("我是分身。可以直接让我查资料、做总结、对比信息、翻译。")
        self.append_note("输入「自检」会报告一次线路、搜索通道、浏览器和渲染能力。")
        self.append_note("输入框是多行的：Enter 发送、Shift+Enter 换行、Ctrl+Enter 也发送；"
                         "Ctrl+L 跳地址栏。")
        self.append_note("遇到要登录的页面，我会把网站自己的登录页打开；你登录完，"
                         "我自动接着干（登录状态留在浏览器 profile 里）。")

    def clear(self):
        self.welcome()
        self.set_status("待命")

    def _insert(self, html, plain=""):
        cur = self.log.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.insertHtml(html + "<br>")
        self.log.setTextCursor(cur)
        self.log.ensureCursorVisible()
        if plain:
            self.log_cache += ("\n\n" if self.log_cache else "") + plain

    def append_user(self, text):
        body = _esc(text).replace("\n", "<br>")
        th = _theme()
        self._insert('<div style="margin:12px 0 4px 0;color:%s;font-weight:bold;">🧑 你</div>'
                     '<div style="color:%s;">%s</div>' % (th["label_user"], th["text"], body),
                     "你：" + str(text))

    def append_note(self, text):
        if text and text == getattr(self, "_last_note", None):
            return                             # 同一句状态别刷屏
        self._last_note = text
        self._insert('<div style="color:%s;font-size:12px;">· %s</div>'
                     % (_theme()["dim"], _esc(text)))

    def append_bot(self, md):
        self._last_answer = md or ""
        self._insert('<div style="margin:12px 0 4px 0;color:%s;font-weight:bold;">🐟 分身</div>'
                     % _theme()["label_bot"] + _md_to_html(md), "分身：" + str(md))

    def set_status(self, s):
        self.status.setText(s)

    def show_result(self, body, sources=""):
        self.append_bot((body or "") + (sources or ""))
        self.set_status("完成 ✓")
        self.show()
        self.raise_()

    def show_error(self, msg):
        self.append_bot("**出错了**：%s" % msg)
        self.set_status("失败")

    # ---------- 交互 ----------
    def begin_task(self, text):
        self.set_status("正在处理…")

    def _send(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.input.clear()
        if text in ("自检", "/check", "联网自检", "检查网络"):
            self.selfcheck()
            return
        self.append_user(text)
        self.set_status("正在处理…")
        if self.on_send:
            self.on_send(text, True)          # True = 这轮已经记进对话了
        else:
            self.append_note("没接上干活的后台，检查一下程序状态")

    def selfcheck(self):
        self.append_note("开始联网自检（线路 / 搜索通道 / 浏览器 / 渲染）…")
        self.set_status("自检中…")
        if self.on_selfcheck:
            self.on_selfcheck()

    def _copy(self):
        QApplication.clipboard().setText(self._last_answer or self.log_cache)
        self.set_status("已复制 ✓")

    # ---------- 内嵌 Chromium：放开权限 ----------
    def _download_dir(self):
        d = os.path.join(os.path.expanduser("~"), "Downloads")
        return d if os.path.isdir(d) else APP_DIR

    def _ensure_profile(self):
        """建（或复用）浏览器 profile —— 权限都在这里放开"""
        if self.profile is not None:
            return self.profile
        base = os.path.join(APP_DIR, "runtime", "_webengine")
        try:
            os.makedirs(os.path.join(base, "storage"), exist_ok=True)
            os.makedirs(os.path.join(base, "cache"), exist_ok=True)
        except Exception:
            base = os.path.join(os.environ.get("TEMP") or ".", "dafeiyu_webengine")
            os.makedirs(os.path.join(base, "storage"), exist_ok=True)
            os.makedirs(os.path.join(base, "cache"), exist_ok=True)
        p = QWebEngineProfile("dafeiyu", self)
        p.setPersistentStoragePath(os.path.join(base, "storage"))
        p.setCachePath(os.path.join(base, "cache"))
        try:
            p.setHttpUserAgent(CHROME_UA)                       # 去掉 QtWebEngine 特征
            p.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
            p.setDownloadPath(self._download_dir())
            p.downloadRequested.connect(self._on_download)
        except Exception as e:
            self.append_note("浏览器权限设置有部分没生效：%s" % str(e)[:60])
        self.profile = p
        return p

    def _apply_web_settings(self, s):
        W = QWebEngineSettings.WebAttribute
        want = {"JavascriptEnabled": True, "JavascriptCanOpenWindows": True,
                "JavascriptCanAccessClipboard": True, "JavascriptCanPaste": True,
                "LocalContentCanAccessFileUrls": True,     # 本地 html 能读同目录文件
                "LocalContentCanAccessRemoteUrls": True,   # 本地 html 能加载网上资源
                "LocalStorageEnabled": True, "PdfViewerEnabled": True,
                "FullScreenSupportEnabled": True, "PluginsEnabled": True,
                "ErrorPageEnabled": True, "AutoLoadImages": True,
                "AllowWindowActivationFromJavaScript": True}
        for name, val in want.items():
            attr = getattr(W, name, None)
            if attr is not None:
                try:
                    s.setAttribute(attr, val)
                except Exception:
                    pass

    def _ensure_web(self):
        if self.web is not None or not WEBENGINE_OK:
            return self.web
        prof = self._ensure_profile()
        self.web = QWebEngineView(self)
        self.web.setPage(QWebEnginePage(prof, self.web))
        page = self.web.page()
        page.newWindowRequested.connect(self._on_new_window)      # 弹新窗口 → 就地打开
        page.fullScreenRequested.connect(lambda r: r.accept())    # 全屏
        page.featurePermissionRequested.connect(self._on_permission)
        page.authenticationRequired.connect(self._on_auth_required)   # 网站要登录
        try:
            page.proxyAuthenticationRequired.connect(self._on_auth_required)   # 代理要认证
        except Exception:
            pass
        try:
            page.certificateError.connect(self._on_cert_error)        # 证书有问题
        except Exception:
            pass
        self._apply_web_settings(self.web.settings())
        self.web.loadFinished.connect(self._on_web_loaded)
        self.web.urlChanged.connect(self._on_web_url)
        self.web.hide()
        self._lay.insertWidget(self._lay.indexOf(self.web_bar) + 1, self.web, 1)
        return self.web

    def _on_download(self, item):
        try:
            name = item.downloadFileName()
            d = self._download_dir()
            if hasattr(item, "setDownloadDirectory"):
                item.setDownloadDirectory(d)
            if hasattr(item, "setDownloadFileName"):
                item.setDownloadFileName(name)
            item.accept()
            self.append_note("开始下载：%s → %s" % (name, d))
        except Exception as e:
            self.append_note("下载没接住：%s" % str(e)[:70])

    def _on_new_window(self, request):
        try:
            self.append_note("网页想弹新窗口，我就在这个窗口里打开它")
            self.web.load(request.url())
        except Exception as e:
            self.append_note("新窗口没接住：%s" % str(e)[:60])

    def _on_permission(self, page, url, feature):
        """摄像头 / 麦克风 / 位置这类敏感权限一律拒绝并记录，隐私优先"""
        try:
            page.setFeaturePermission(
                url, feature, QWebEnginePage.PermissionPolicy.PermissionDeniedByUser)
        except Exception:
            pass
        self.append_note("拒绝了 %s 的敏感权限请求（%s）" % (url.host(), feature))

    def _on_auth_required(self, url, authenticator):
        """网站（或代理）要求登录认证 → 弹框让你填，填完继续；取消就放弃这次访问"""
        try:
            host = url.host() if hasattr(url, "host") else str(url)[:40]
        except Exception:
            host = str(url)[:40]
        host = host or str(url)[:40]
        self.append_note("「%s」要求登录认证" % host)
        try:
            dlg = _LoginDialog(self, host, "这类站点没有网页登录页，只能在这里做 HTTP 认证；"
                                           "普通网页登录走网站自己的登录页。")
            dlg.user.setFocus()
            if dlg.exec() == QDialog.DialogCode.Accepted:
                user, pwd = dlg.values()
                authenticator.setUser(user)
                authenticator.setPassword(pwd)
                self.append_note("已提交认证信息（没有写进磁盘）")
            else:
                self.append_note("你取消了这次登录，这个页面可能打不开")
        except Exception as e:
            self.append_note("登录框没起来：%s" % str(e)[:60])

    def _on_cert_error(self, error):
        """证书有问题：默认拦下并说明（不静默放行）。"""
        try:
            desc = error.description()
            url = error.url().toString()
        except Exception:
            desc, url = str(error)[:80], ""
        self.append_note("证书验证没过：%s（%s）" % (desc, url[:50]))
        self.append_note("已替你拦下；确实要访问就把链接复制到系统浏览器，或者告诉我加白名单")
        try:
            error.rejectCertificate()
        except Exception:
            pass

    def _on_web_loaded(self, ok):
        if not ok:
            self.append_note("这个页面没加载成功（可能被拦、地址不对，或需要登录）")
        elif self.web is not None:
            t = (self.web.title() or "")[:40]
            if t:
                self.setWindowTitle("🐟 分身 · " + t)
            if self.web.isVisible():
                self.web.setFocus()      # 键盘直接进网页表单（登录、搜索都要打字）

    def _on_web_url(self, u):
        if self.addr is not None and not self.addr.hasFocus():
            self.addr.setText(u.toString())

    # ---------- 地址栏 / 搜索引擎 / 结果翻看 ----------
    def _engine(self):
        try:
            data = self.engine_box.currentData()
        except Exception:
            data = None
        return (data or self.engine or "ddg").lower()

    def _search_url(self, words):
        _name, tpl, _home = SEARCH_ENGINES.get(self._engine(), SEARCH_ENGINES["ddg"])
        return tpl % quote(words)

    def normalize_input(self, text):
        """把输入分类：url / local / office / search / missing"""
        t = (text or "").strip().strip('"').strip()
        if not t:
            return "", ""
        if t.startswith("file://"):
            return "url", t
        if re.match(r"^[a-zA-Z]:[\\/]", t) or t.startswith("\\\\"):
            if os.path.isdir(t):
                return "url", QUrl.fromLocalFile(t).toString()
            if not os.path.exists(t):
                return "missing", t
            if os.path.splitext(t)[1].lower() in OFFICE_EXTS:
                return "office", os.path.abspath(t)
            return "url", QUrl.fromLocalFile(os.path.abspath(t)).toString()
        if "://" in t:
            return "url", t
        if os.path.exists(t) and "." in os.path.basename(t):
            if os.path.splitext(t)[1].lower() in OFFICE_EXTS:
                return "office", os.path.abspath(t)
            return "url", QUrl.fromLocalFile(os.path.abspath(t)).toString()
        if " " in t or "." not in t:
            return "search", t
        return "url", "https://" + t

    def go(self, text):
        """地址栏回车：网址 / 本地文件 / 搜索词都能吃"""
        kind, val = self.normalize_input(text)
        if kind == "search":
            self.append_note("用 %s 搜：%s" % (SEARCH_ENGINES.get(self._engine(),
                                                          SEARCH_ENGINES["ddg"])[0], val))
            kind, val = "url", self._search_url(val)
        if kind == "office":
            self._open_with_system(val)
            return
        if kind == "missing":
            self.append_note("本地找不到这个文件：%s" % val)
            return
        if val:
            self.open_url(val)

    def _open_with_system(self, path):
        """Word / Excel / PPT 这类 Chromium 显示不了的，交给系统默认程序打开"""
        try:
            os.startfile(path)                                  # 仅 Windows
            self.append_note("Word/Excel 这类 Chromium 显示不了，已交给系统程序打开：%s"
                             % os.path.basename(path))
        except Exception as e:
            self.append_note("打不开这个文件：%s" % str(e)[:60])

    def _on_engine_change(self):
        self.engine = self._engine()
        _RUNTIME["search_engine"] = self.engine
        self.home = SEARCH_ENGINES.get(self.engine, SEARCH_ENGINES["ddg"])[2]
        self.append_note("搜索引擎切成：%s" % SEARCH_ENGINES.get(self.engine,
                                                          ("?", "", ""))[0])

    def set_result_urls(self, urls):
        """把上一次搜索的来源交给工具栏，用 ◀ ▶ 逐个翻看"""
        self._result_urls = [u for u in dict.fromkeys(urls or []) if str(u).startswith("http")]
        self._result_idx = -1
        self._show_res_index()

    def _show_res_index(self):
        try:
            n = len(self._result_urls)
            self.res_label.setText("%d/%d" % (self._result_idx + 1 if self._result_idx >= 0 else 0, n))
        except Exception:
            pass

    def next_result(self):
        if not self._result_urls:
            self.append_note("还没有搜索结果，先让我查点东西")
            return
        self._result_idx = (self._result_idx + 1) % len(self._result_urls)
        self._show_res_index()
        self.open_url(self._result_urls[self._result_idx])

    def prev_result(self):
        if not self._result_urls:
            self.append_note("还没有搜索结果，先让我查点东西")
            return
        self._result_idx = (self._result_idx - 1) % len(self._result_urls)
        self._show_res_index()
        self.open_url(self._result_urls[self._result_idx])

    # ---------- 网页切换 ----------
    def toggle_web(self, url=None):
        """在「对话」和「网页」之间切；给了 url 就直接开那一页"""
        if not WEBENGINE_OK:
            self.append_note("这台机器的 PySide6 没带 QtWebEngine，内嵌网页看不了；搜索不受影响。")
            return
        try:
            w = self._ensure_web()
            if w.isVisible() and not url:
                w.hide()
                self.web_bar.hide()
                self.log.show()
                self.view_btn.setText("🌐 看网页")
                return
            if url:
                w.load(QUrl(url))
            elif not w.url().toString():
                w.load(QUrl(self.home))
            w.show()
            self.web_bar.show()
            self.log.hide()
            self.view_btn.setText("💬 回对话")
            if w.url().toString():
                self.addr.setText(w.url().toString())
        except Exception as e:
            self.append_note("内嵌网页打不开：%s" % str(e)[:80])

    def open_url(self, url):
        self.toggle_web(url)

    def _on_anchor(self, u):
        url = u.toString()
        if WEBENGINE_OK:
            self.open_url(url)
        else:
            try:
                import webbrowser
                webbrowser.open(url)
            except Exception:
                pass


class BrowserFetcher(QObject):
    """主线程上的「真浏览器取页」服务。

    分身在子线程里干活，而 QtWebEngine 只能待在主线程 —— 所以子线程发信号排队，
    主线程用隐藏的 WebEngineView 打开页面、等 JS 跑完，再把 DOM 回传。
    关键是它和窗口里的浏览器**共用同一个 profile**：你在窗口里手动过掉了某站的人机验证，
    分身随后取同站页面就带着那份 Cookie，不用再验一次。
    """
    _requested = Signal(str, str, float)   # (token, url, timeout)：跨线程投递到主线程

    def __init__(self, owner):
        super().__init__()
        self.owner = owner                 # AvatarWindow
        self.view = None
        self._pending = {}                 # token -> (Event, box)
        self._queue = []
        self._busy = False
        self._cur = None
        self._requested.connect(self._on_request)

    def request(self, url, timeout=30):
        """任意线程都能调；返回 (ok, dom 或原因)"""
        if not WEBENGINE_OK:
            return False, "没有内嵌 Chromium"
        token = "%f-%d" % (time.time(), random.randint(1000, 9999))
        ev = threading.Event()
        box = {}
        self._pending[token] = (ev, box)
        self._requested.emit(token, url, float(timeout))
        if QThread.currentThread() is self.thread():
            # 主线程里直接调用会自己把事件循环堵死（loadFinished 永远等不到），
            # 所以边等边转事件循环
            deadline = time.time() + timeout
            while not ev.is_set() and time.time() < deadline:
                QApplication.processEvents()
                time.sleep(0.02)
        else:
            ev.wait(timeout)
        if not ev.is_set():
            self._pending.pop(token, None)
            return False, "取页超时（%ss）" % timeout
        return box.get("ok", False), box.get("dom", "")

    # ---- 以下都在主线程跑 ----
    def _on_request(self, token, url, timeout=30):
        self._queue.append((token, url, timeout))
        self._pump()

    def _pump(self):
        if self._busy or not self._queue:
            return
        token, url, timeout = self._queue.pop(0)
        self._busy = True
        self._cur = token
        try:
            if self.view is None:
                self.owner._ensure_web()               # 保证 profile 已就绪
                self.view = QWebEngineView(self.owner)     # 挂在窗口下，退出时一起销毁
                self.view.setPage(QWebEnginePage(self.owner.profile, self.view))
                self.owner._apply_web_settings(self.view.settings())
                self.view.resize(1280, 900)
                self.view.loadFinished.connect(self._on_loaded)
                self.view.hide()
            self.view.load(QUrl(url))
            # 内部兜底定时器跟着调用方给的超时走，别把长超时的请求提前砍掉
            guard = int(max(5.0, float(timeout) - 3.0) * 1000)
            QTimer.singleShot(guard, lambda t=token: self._finish(t, False, "页面没能取回来"))
        except Exception as e:
            self._finish(token, False, "%s: %s" % (type(e).__name__, str(e)[:60]))

    def _on_loaded(self, ok):
        if self._busy:
            QTimer.singleShot(2500, self._grab)         # 给 JS / 验证页一点时间跑完

    def _grab(self):
        if not self._busy or self.view is None:
            return
        try:
            self.view.page().runJavaScript("document.documentElement.outerHTML",
                                           lambda dom: self._finish(self._cur, True, dom or ""))
        except Exception as e:
            self._finish(self._cur, False, str(e)[:60])

    def _finish(self, token, ok, dom):
        if not token or token not in self._pending:
            return
        ev, box = self._pending.pop(token)
        box.update(ok=ok, dom=dom)
        ev.set()
        if token == self._cur:
            self._busy = False
            self._cur = None
            QTimer.singleShot(0, self._pump)

class _EyeRestCanvas(QWidget):
    """护眼大屏中间那只大鱼（会呼吸、会晃）"""

    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self._pix = pixmap
        self._t = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(lambda: (setattr(self, "_t", self._t + 1), self.update()))
        self._timer.start(50)
        self.setMinimumSize(200, 200)

    def set_pixmap(self, pixmap):
        self._pix = pixmap
        self.update()

    def paintEvent(self, _):
        if self._pix is None or self._pix.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        now = self._t * 0.05
        breath = 1.0 + 0.03 * math.sin(now * 2.0)
        sway = math.sin(now * 1.2) * 2.5
        ph = self._pix.height() * breath
        pw = self._pix.width() * breath
        # 放大到差不多占满中间区域（上限 2 倍，再大就糊了）
        k = min((self.height() - 20) / ph, (self.width() - 20) / pw, 2.0)
        k = max(0.1, k)
        ph *= k
        pw *= k
        dx = (self.width() - pw) / 2.0
        dy = (self.height() - ph) / 2.0
        p.translate(self.width() / 2.0, self.height() / 2.0)
        p.rotate(sway)
        p.translate(-self.width() / 2.0, -self.height() / 2.0)
        p.drawPixmap(QRectF(dx, dy, pw, ph), self._pix,
                     QRectF(0, 0, self._pix.width(), self._pix.height()))


class EyeRestOverlay(QWidget):
    """护眼时间：一块大屏霸占屏幕中央，鱼在中间，输入「我在忙」就放人。

    这是「不许再看屏幕」的那 10 分钟，所以它铺满整块屏幕、盖住一切，
    只留一个输入框当逃生门。
    """

    def __init__(self, pixmap, on_finish, parent=None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("护眼时间")
        _t = _theme()
        self._on_finish = on_finish
        self._left = 0
        self._done = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 26, 26, 26)      # 留出深色幕布边缘，卡片浮在中间
        card = QFrame()
        # 注意：必须限定到 #eyeCard —— QLabel 也是 QFrame 的子类，
        # 写成 QFrame{...} 会让里面每个标签都长出一圈边框
        card.setObjectName("eyeCard")
        card.setStyleSheet("#eyeCard{background:%s;border-radius:26px;"
                           "border:1px solid %s;}" % (_t["overlay_card"], _t["overlay_border"]))
        outer.addWidget(card, 1)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(10)
        self.title = QLabel("🐟 护眼时间")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet("color:%s;font-size:26px;font-weight:bold;"
                                 "font-family:'Microsoft YaHei UI';" % _t["overlay_text"])
        lay.addWidget(self.title)
        self.count = QLabel("还剩 10:00")
        self.count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count.setStyleSheet("color:%s;font-size:18px;font-family:'Microsoft YaHei UI';"
                                 % _t["accent"])
        lay.addWidget(self.count)

        self.canvas = _EyeRestCanvas(pixmap)
        lay.addWidget(self.canvas, 1)

        self.tip = QLabel("看看窗外、站起来走两步 —— 我把你的窗口先收起来了，"
                          "时间到了自动放回来")
        self.tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tip.setWordWrap(True)
        self.tip.setStyleSheet("color:%s;font-size:14px;font-family:'Microsoft YaHei UI';"
                               % _t["overlay_dim"])
        lay.addWidget(self.tip)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setPlaceholderText("真有急事就在这儿打字：输入「我在忙」我就放你走")
        self.input.setStyleSheet(
            "QLineEdit{background:%s;border:1px solid %s;"
            "border-radius:12px;padding:9px 12px;color:#ffffff;font-size:15px;"
            "font-family:'Microsoft YaHei UI';}"
            "QLineEdit:focus{border:1px solid %s;}"
            % (_t["overlay_field"], _t["overlay_field_border"], _t["accent"]))
        self.input.returnPressed.connect(self._submit)
        row.addWidget(self.input, 1)
        self.go_btn = QPushButton("放我走")
        self.go_btn.setFixedSize(92, 38)
        self.go_btn.setStyleSheet(
            "QPushButton{background:%s;color:white;border:none;border-radius:12px;"
            "font-size:14px;font-family:'Microsoft YaHei UI';}"
            "QPushButton:hover{background:%s;}" % (_t["accent"], _t["accent_dark"]))
        self.go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.go_btn.clicked.connect(self._submit)
        row.addWidget(self.go_btn)
        lay.addLayout(row)

        self.feedback = QLabel("")
        self.feedback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.feedback.setWordWrap(True)
        self.feedback.setStyleSheet("color:%s;font-size:12px;"
                                    "font-family:'Microsoft YaHei UI';" % _t["overlay_faint"])
        lay.addWidget(self.feedback)

    # ---------- 生命周期 ----------
    def paintEvent(self, _):
        """深色幕布：没有它窗口是透明的，就只是浮在桌面上，谈不上「霸占」"""
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(*_theme()["overlay_bg"]))

    def start(self, seconds, area, note=""):
        self._left = max(1, int(seconds))
        self._done = False
        if area is not None:
            self.setGeometry(area)
        self.input.clear()
        if note:
            self.tip.setText(note)
        self.feedback.setText("有急事就在这里打字（「我在忙」/「有事」/「下次」都行）")
        self._update_count()
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
        self._timer.start(1000)

    def stop(self):
        """外面要求结束（比如到点由桌宠统一收尾）—— 不再回调"""
        self._done = True
        self._timer.stop()
        self.hide()

    def _finish(self, reason):
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self.hide()
        if self._on_finish:
            self._on_finish(reason)

    def _tick(self):
        if self._done:
            return
        self._left -= 1
        self._update_count()
        if self._left <= 0:
            self._finish("time")

    def _update_count(self):
        self.count.setText("还剩 %02d:%02d" % (self._left // 60, self._left % 60))

    def showEvent(self, e):
        super().showEvent(e)
        if not self._done:                      # 窗口一出来就把焦点给输入框
            self.activateWindow()
            self.input.setFocus()

    def closeEvent(self, e):
        # Alt+F4 / 从任务栏关掉大屏 → 当作跳过这次休息，免得留下「鱼不见了」的状态
        self._finish("closed")
        super().closeEvent(e)

    # ---------- 逃生门 ----------
    def _norm(self, s):
        return re.sub(r"[\s，。！？、,.!?~～:：;；\"'“”‘’()（）]+", "", (s or "").strip().lower())

    def _submit(self):
        text = self.input.text()
        if not text.strip():
            return
        if any(w in self._norm(text) for w in EYE_REST_BUSY_WORDS):
            self._finish("busy")
            return
        self.input.clear()
        self.feedback.setText(random.choice(EYE_REST_RETORT_LINES))


class _NativeWebMDecoder(QThread):
    """在后台直接解码 VP9 alpha，避免浏览器每帧编码 PNG 和跨进程传递 Base64。"""
    processed = Signal(object)
    bounds_ready = Signal(object)
    clip_ended = Signal(str)
    failed = Signal(str)

    def __init__(self, path, clip, loop, generation, rect, dpr):
        super().__init__()
        self.path, self.clip, self.loop, self.generation = path, clip, loop, generation
        self.render_target = (QRectF(rect), dpr)
        self.process = None
        self.width, self.height = ((1280, 720) if os.path.basename(os.path.dirname(path)) == "hd" else (640, 360))

    def stop(self):
        self.requestInterruption()
        process = self.process
        if process is not None and process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
        self.wait(3000)

    def run(self):
        command = [VIDEO_FFMPEG, "-v", "error", "-threads", "2"]
        if self.loop:
            command += ["-stream_loop", "-1"]
        command += ["-c:v", "libvpx-vp9", "-i", self.path, "-an",
                    "-f", "rawvideo", "-pix_fmt", "rgba", "-"]
        try:
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                            creationflags=subprocess.CREATE_NO_WINDOW)
            count = self.width * self.height * 4
            index = 0
            started = None
            while not self.isInterruptionRequested():
                data = self.process.stdout.read(count)
                if len(data) != count:
                    if not self.isInterruptionRequested():
                        if self.process.wait() != 0:
                            self.failed.emit("原生视频解码失败")
                        else:
                            self.clip_ended.emit(self.clip)
                    break
                image = QImage(data, self.width, self.height, self.width*4,
                               QImage.Format.Format_RGBA8888).copy()
                if index == 0 and PILImage is not None:
                    alpha = PILImage.frombytes("RGBA", (self.width,self.height), data).getchannel("A")
                    bounds = alpha.point(lambda a:255 if a>12 else 0).getbbox()
                    if bounds:
                        x0,y0,x1,y1 = bounds
                        self.bounds_ready.emit(dict(w=self.width,h=self.height,x0=x0/self.width,
                            y0=y0/self.height,x1=x1/self.width,y1=y1/self.height))
                rect,dpr = self.render_target
                result = VideoBody._process_frame(self.clip,self.generation,image,rect,dpr)
                if started is None:
                    started = time.perf_counter()
                deadline = started + index/24.0
                while time.perf_counter()<deadline and not self.isInterruptionRequested():
                    self.msleep(min(5,max(1,int((deadline-time.perf_counter())*1000))))
                if self.isInterruptionRequested():
                    break
                self.processed.emit(result)
                index += 1
        except (OSError, ValueError) as error:
            if not self.isInterruptionRequested():
                self.failed.emit("原生视频解码失败：%s" % str(error)[:80])
        finally:
            if self.process is not None:
                if self.process.poll() is None:
                    self.process.kill()
                self.process.wait()
                self.process.stdout.close()


class VideoBody(QWidget):
    """后台 WebM 解码器：优先直接解码，缺少 FFmpeg 时使用隐藏的浏览器。"""
    _frame_processed = Signal(object)

    def __init__(self, on_clip_end=None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowTitle("大肥鱼（视频）")
        self.on_clip_end = on_clip_end
        self.target_pet = None           # 收到新的视频帧时重绘桌宠本体
        self.view = None
        self.native_decoder = None
        self.use_native = bool(VIDEO_FFMPEG)
        self.profile = None
        self.ready = False
        self.page_loaded = False
        self.pending_clip = None
        self.frame_ready = False
        self.frame_image = None
        self._poll_pending = False
        self._decode_pending = False
        self._decode_generation = 0
        self._frame_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pet-frame")
        QApplication.instance().aboutToQuit.connect(
            lambda: self._frame_executor.shutdown(wait=True, cancel_futures=True))
        QApplication.instance().aboutToQuit.connect(self._stop_native)
        self._frame_processed.connect(self._accept_processed_frame)
        self.clip = ""
        self.loaded_clip = ""
        self.loop = True
        self.mirror = False
        self.bbox = None                 # 角色在 16:9 画幅里占的比例（量一次就一直用）
        self._fit_args = None
        self._last_measure = 0.0
        self.info = {"dur": 0.0, "t": 0.0, "ended": False, "err": "", "w": 0, "h": 0}
        self._last_end = 0.0
        self._last_rect = None
        self.render_rect = QRectF()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._poll)
        self._timer.start(FRAME_INTERVAL)

    # ---------- 建 ----------
    def ensure(self):
        """优先原生解码；浏览器兼容通道按需创建。"""
        if self.use_native:
            self.ready = self.page_loaded = True
            return True
        if self.view is not None or not WEBENGINE_OK:
            return self.view
        base = os.path.join(APP_DIR, "runtime", "_webengine_video")
        try:
            os.makedirs(os.path.join(base, "storage"), exist_ok=True)
            os.makedirs(os.path.join(base, "cache"), exist_ok=True)
        except Exception:
            base = os.path.join(os.environ.get("TEMP") or ".", "dafeiyu_video")
            try:
                os.makedirs(os.path.join(base, "storage"), exist_ok=True)
                os.makedirs(os.path.join(base, "cache"), exist_ok=True)
            except Exception:
                return None
        try:
            self.profile = QWebEngineProfile("dafeiyu_video", self)
            self.profile.setPersistentStoragePath(os.path.join(base, "storage"))
            self.profile.setCachePath(os.path.join(base, "cache"))
            self.profile.setHttpUserAgent(CHROME_UA)
            self.profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        except Exception as e:
            print("视频 profile 没建好:", e)
            return None
        self.view = QWebEngineView(self)
        self.view.setStyleSheet("QWebEngineView { border: none; background: transparent; }")
        self.view.loadFinished.connect(self._on_page_loaded)
        page = QWebEnginePage(self.profile, self.view)
        self.view.setPage(page)
        page.renderProcessTerminated.connect(self._on_render_process_terminated)
        self.view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        try:
            page.setBackgroundColor(QColor(0, 0, 0, 0))        # 透明底的关键
        except Exception as e:
            print("视频透明底没设上:", e)
        try:
            s = self.view.settings()
            W = QWebEngineSettings.WebAttribute
            for name, val in (("LocalContentCanAccessFileUrls", True),
                              ("LocalContentCanAccessRemoteUrls", True),
                              ("JavascriptEnabled", True),
                              ("PlaybackRequiresUserGesture", False),   # 允许自动播放
                              ("AutoLoadImages", True)):
                attr = getattr(W, name, None)
                if attr is not None:
                    s.setAttribute(attr, val)
        except Exception as e:
            print("视频设置没全生效:", e)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)
        port = start_anim_server()
        if port:
            self.view.load(QUrl("http://127.0.0.1:%d/player" % port))
        else:
            self.view.setHtml(VIDEO_HTML, QUrl.fromLocalFile(ANIM_DIR + os.sep))
        self.ready = True
        return self.view

    def _on_page_loaded(self, ok):
        """播放器页面加载后才下发排队的播放指令。"""
        if not ok:
            self._fail("播放器页面加载失败")
            return
        self.page_loaded = True
        # 页面保持媒体解码状态，QWebEngineView 本身始终不显示到桌面。
        self.view.page().setVisible(True)
        if hasattr(self, "_capture_width"):
            self._js("window.__captureWidth=%d" % self._capture_width)
        pending = self.pending_clip
        self.pending_clip = None
        if pending:
            self._start_clip(*pending)

    def _fail(self, message):
        self._stop_native()
        self.clip = ""
        self.loaded_clip = ""
        self.pending_clip = None
        self.frame_ready = False
        self.frame_image = None
        self.hide()
        pet = self.target_pet
        if pet is not None:
            pet._video_failed = True
            pet.update()
            pet.say("视频动画没启动起来，我先切回立绘～")

    def _on_render_process_terminated(self, status, exit_code):
        """Chromium 子进程崩溃时收起空视频窗，立即恢复 PNG 立绘。"""
        print("[视频] Chromium 渲染进程退出：%s，代码 %s" % (status, exit_code))
        self.page_loaded = False
        self._fail("Chromium 渲染进程退出")

    # ---------- 播 ----------
    def _js(self, code, cb=None):
        try:
            if self.view is None:
                return
            if cb is None:
                self.view.page().runJavaScript(code)
            else:
                self.view.page().runJavaScript(code, cb)
        except Exception as e:
            print("视频 JS 失败:", e)

    def play(self, clip, loop=True):
        if not clip or not self.ensure():
            return False
        self.loop = bool(loop)
        self.clip = clip
        if not self.page_loaded:
            self.pending_clip = (clip, self.loop)
            return True
        self._start_clip(clip, self.loop)
        return True

    def _start_clip(self, clip, loop):
        if self.use_native:
            if (self.native_decoder is not None and self.native_decoder.isRunning()
                    and clip == self.loaded_clip and loop == self.native_decoder.loop):
                return
            self._stop_native()
            self._decode_generation += 1
            self.frame_ready = False
            self.frame_image = None
            hd_path = os.path.join(ANIM_DIR, "hd", clip+".webm")
            path = hd_path if os.path.isfile(hd_path) else os.path.join(ANIM_DIR,clip+".webm")
            pet = self.target_pet
            decoder = _NativeWebMDecoder(path,clip,loop,self._decode_generation,self.render_rect,
                                         pet.devicePixelRatioF() if pet is not None else 1.0)
            decoder.processed.connect(self._accept_processed_frame)
            decoder.bounds_ready.connect(self._native_bounds)
            decoder.clip_ended.connect(self._native_end)
            decoder.failed.connect(self._fail)
            self.native_decoder = decoder
            self.loaded_clip = clip
            decoder.start()
            return
        if clip != self.loaded_clip:
            self._decode_generation += 1
            self.frame_ready = False
            self.frame_image = None
            self._js("playClip(%s,%s)" % (json.dumps(clip, ensure_ascii=False),
                                          "true" if loop else "false"))
            self.loaded_clip = clip
        else:
            self._js("document.getElementById('v').loop=%s; document.getElementById('v').play()"
                     % ("true" if loop else "false"))

    def stop(self):
        self._stop_native()
        self._decode_generation += 1
        self.clip = ""
        self.loaded_clip = ""
        self.pending_clip = None
        self.frame_ready = False
        self.frame_image = None
        self._js("var e=document.getElementById('v'); if(e){e.pause();}")
        self.hide()

    def _stop_native(self):
        decoder = self.native_decoder
        if decoder is not None:
            self.native_decoder = None
            decoder.stop()

    def _native_bounds(self, bounds):
        if self.sender() is self.native_decoder and self.clip in ANIM_POOLS.get("待机", []) and self.bbox is None:
            self._got_bbox(bounds)

    def _native_end(self, clip):
        if self.sender() is self.native_decoder and clip == self.clip and not self.loop and self.on_clip_end:
            self.on_clip_end(clip)

    def measure(self):
        """量一下角色在画幅里的位置（用来和立绘对齐）"""
        if not self.ensure():
            return None
        self._js(VIDEO_MEASURE_JS, lambda v: self._got_bbox(v))
        return self.bbox

    def _as_obj(self, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        return v if isinstance(v, dict) else None

    def _got_bbox(self, v):
        v = self._as_obj(v)
        if isinstance(v, dict) and v.get("err"):
            print("[视频] 量角色位置出错:", v["err"])
            return
        if isinstance(v, dict) and "x0" in v:
            self.bbox = v
            print("[视频] 角色占画幅：x %.3f~%.3f, y %.3f~%.3f（画幅 %dx%d）"
                  % (v["x0"], v["x1"], v["y0"], v["y1"], v["w"], v["h"]))
            if self._fit_args:            # 量到了就按真实位置重摆一次
                try:
                    if self.target_pet is not None:
                        self.target_pet._sync_video()
                    else:
                        self.fit_to(*self._fit_args)
                except Exception as e:
                    print("重摆视频窗失败:", e)

    def _poll(self):
        if (not self.page_loaded or self.view is None or not self.clip
                or self._poll_pending or self._decode_pending):
            return
        if isinstance(self.target_pet, QWidget) and not self.target_pet.isVisible():
            return
        self._poll_pending = True
        self._js(VIDEO_INFO_JS, lambda v: self._got_info(v))

    def _got_info(self, v):
        self._poll_pending = False
        v = self._as_obj(v)
        if not isinstance(v, dict):
            return
        if v.get("name") != self.clip:
            return
        frame = v.pop("frame", "")
        self.info = v
        if v.get("err"):
            print("[视频] 播放失败：", v["err"])
            self._fail("视频播放失败：%s" % v["err"])
            return
        if frame:
            image = QImage.fromData(base64.b64decode(frame), "PNG")
            full_w, full_h = int(v.get("frameW", 0)), int(v.get("frameH", 0))
            if not image.isNull() and full_w and full_h:
                full_image = QImage(full_w, full_h, QImage.Format.Format_ARGB32_Premultiplied)
                full_image.fill(Qt.GlobalColor.transparent)
                painter = QPainter(full_image)
                painter.drawImage(int(v.get("frameX", 0)), int(v.get("frameY", 0)), image)
                painter.end()
                image = full_image
            if not image.isNull():
                pet = self.target_pet
                if pet is not None:
                    self._decode_pending = True
                    args = (self.clip, self._decode_generation, image,
                            QRectF(self.render_rect), pet.devicePixelRatioF())
                    future = self._frame_executor.submit(self._process_frame, *args)
                    future.add_done_callback(lambda f: self._frame_processed.emit(f.result()))
                else:
                    self.frame_image = image
                    self.frame_ready = True
        if v.get("ended") and not self.loop and self.clip:
            if time.time() - self._last_end > 0.8:
                self._last_end = time.time()
                clip = self.clip
                if self.on_clip_end:
                    self.on_clip_end(clip)

    @staticmethod
    def _process_frame(clip, generation, image, rect, dpr):
        try:
            enhanced, bounds = PetWindow._build_quality_frame(image, rect, dpr)
        except Exception:
            enhanced, bounds = image, (0, 0, image.width(), image.height())
        return clip, generation, image, rect, dpr, enhanced, bounds

    def _accept_processed_frame(self, result):
        self._decode_pending = False
        clip, generation, image, rect, dpr, enhanced, bounds = result
        if clip != self.clip or generation != self._decode_generation:
            return
        self.frame_image = image
        self.frame_ready = True
        pet = self.target_pet
        if pet is not None:
            pet._quality_frame_key = (image.cacheKey(), rect.width(), rect.height(), dpr)
            pet._quality_frame = enhanced
            pet._quality_bounds = bounds
            pet.update()

    def set_mirror(self, on):
        on = bool(on)
        if on != self.mirror:
            self.mirror = on
            self._js("setMirror(%s)" % ("true" if on else "false"))

    # ---------- 摆位 / 穿透 ----------
    def fit_to(self, cx, bottom, sprite_h, mirror=False):
        """按桌宠立绘的尺寸与脚底位置摆好窗口，让画幅里的角色正好顶替立绘"""
        self._fit_args = (cx, bottom, sprite_h, mirror)
        # 只在播「待机」时量：别的动画可能带着风筝/礼物这类道具，会把包围盒撑大
        if (self.bbox is None and time.time() - self._last_measure > 2.0
                and self.clip in ANIM_POOLS.get("待机", [])):
            self._last_measure = time.time()
            self.measure()
        bb = self.bbox or {"x0": 0.28, "x1": 0.72, "y0": 0.20, "y1": 0.85}
        ch = max(0.15, min(1.0, bb["y1"] - bb["y0"]))
        vh = max(60.0, sprite_h / ch * ANIMATION_FRAME_SCALE)
        pet = self.target_pet
        if pet is not None:
            # 拖拽动画切换或跨屏时锁定手势开始时的画幅，避免每次鼠标移动重新缩放。
            drag_locked = pet.dragging and not self.render_rect.isEmpty()
            if drag_locked:
                vh = self.render_rect.height()
            # 缩放依据完整源画幅，不能依据当前帧的道具包围盒，否则角色会忽大忽小。
            geo = pet._scene_screen_rect()
            def canvas_at(height):
                width = height * 16.0 / 9.0
                scene = QRectF(pet.win_w / 2 - (bb["x0"] + bb["x1"]) / 2 * width,
                               BUBBLE_H + MARGIN + sprite_h - bb["y1"] * height,
                               width, height)
                return QRectF(0, 0, pet.win_w, pet.win_h).united(
                    scene.adjusted(-2, -2, 2, 2)).toAlignedRect()
            area = canvas_at(vh)
            if not drag_locked and (area.width() > geo.width() or area.height() > geo.height()):
                low, high = 0.0, vh
                for _ in range(20):
                    mid = (low + high) / 2
                    area = canvas_at(mid)
                    if area.width() <= geo.width() and area.height() <= geo.height():
                        low = mid
                    else:
                        high = mid
                vh = low
        vw = vh * 16.0 / 9.0
        feet = bb["y1"] * vh
        cx_v = (bb["x0"] + bb["x1"]) / 2.0 * vw
        rect = (int(round(cx - cx_v)), int(round(bottom - feet)),
                int(round(vw)), int(round(vh)))
        pet = self.target_pet
        if pet is not None:
            scene = QRectF(cx - cx_v - pet._body_pos().x(),
                           bottom - feet - pet._body_pos().y(), vw, vh)
            offset = pet._fit_animation_canvas(scene)
            self.render_rect = scene.translated(offset)
            if self.native_decoder is not None:
                self.native_decoder.render_target = (QRectF(self.render_rect),pet.devicePixelRatioF())
            capture_width = max(640, int(round(vw * pet.devicePixelRatioF())))
            if capture_width != getattr(self, "_capture_width", None):
                self._capture_width = capture_width
                self._js("window.__captureWidth=%d" % capture_width)
        self.set_mirror(mirror)
        if rect != self._last_rect:
            self._last_rect = rect
            # 隐藏的解码器无需跟着桌宠移动，也无需反复调整网页布局。
            if self.size().width() != rect[2] or self.size().height() != rect[3]:
                self.resize(rect[2], rect[3])

class PetWindow(QWidget):
    def locate_me(self, auto=False):
        """定位：**先申请系统授权定位**（会弹授权框），拿不到再退回 IP 粗略定位。

        结果写进 config.json（city / lat / lon / loc_src）；有坐标时天气直接用坐标查，更准。
        """
        self.say("我去定位一下…")
        self._locate_queue = None

        def work():
            res, why = None, ""
            try:
                res, why = locate_by_system()
            except Exception as e:
                why = str(e)[:60]
            if not res:
                try:
                    ip = locate_by_ip()
                except Exception:
                    ip = None
                if ip:
                    res = ip
                    why = ("%s；已用 IP 粗略定位" % why) if why else "已用 IP 粗略定位"
            self._locate_queue = (res, why, auto, False)

        threading.Thread(target=work, daemon=True).start()

    def _auto_locate_ip(self):
        """开机静默刷新城市：**只走 IP**，不弹任何授权框"""
        if not self.cfg.get("auto_locate_city", True):
            return

        def work():
            try:
                res = locate_by_ip()
            except Exception:
                res = None
            if res:
                res["src"] = "IP 自动刷新"
            self._locate_queue = (res, "", False, True)

        threading.Thread(target=work, daemon=True).start()

    def set_auto_locate_city(self, on):
        """启动时要不要按 IP 自动更新城市"""
        self.cfg["auto_locate_city"] = bool(on)
        self.save_config()
        self.say("启动时自动更新城市：%s" % ("开" if on else "关"))

    def _set_city_dialog(self):
        _cur_city = self.cfg.get("city", "")
        city, ok = QInputDialog.getText(
            self,
            "设置城市",
            "输入城市名:",
            QLineEdit.EchoMode.Normal,
            "" if is_placeholder_city(_cur_city) else _cur_city
        )

        print("输入框结果:", city, ok)

        if ok and city.strip():
            if is_placeholder_city(city.strip()):
                self.say("这看着还是占位符，填个真城市吧～")
                return
            self.cfg["city"] = city.strip()
            self.cfg["lat"] = self.cfg["lon"] = None      # 手动城市优先，清掉坐标免得打架
            self.cfg["loc_src"] = "手动设置"
            self.cfg["auto_locate_city"] = False          # 手动设过就不再自动覆盖
            print("cfg现在:", self.cfg["city"])
            self.save_config()
            self.say(f"城市已设置为{city}")

    def __init__(self):
        self.cfg = load_json(CONFIG_PATH, {
            "mode": "wander",
            "size": 0.7,
            "topmost": True,
            "passthrough": False,
            "autostart": False,
            "x": None,
            "y": None,
            "ds_api_key": "",
            "ds_base_url": DS_BASE_URL,
            "ds_model": DS_MODEL,
            "eye_rest_enabled": True,        # 护眼提醒总开关
            "eye_rest_interval_min": 120,    # 每 120 分钟骚扰一次
            "eye_rest_duration_min": 10,     # 缩小休息 10 分钟
            "eye_rest_shrink": True,         # 提醒时自动缩小自己
            "eye_rest_minimize_windows": True,   # 提醒时把你开的窗口全收起来
            "eye_rest_restore_windows": True,    # 到点自动放回来
            "eye_rest_overlay": True,            # 休息期间用大屏霸占屏幕中央
            "eye_rest_pending": [],              # 收起来的窗口（重启也能接着放回来）
            "eye_rest_restore_at": 0,            # 该放回来的时刻（毫秒时间戳）
            "task_model": "",                # 分身用哪个模型，空 = 跟 ds_model 一样
            "task_max_rounds": 4,            # 分身最多来回用几轮工具
            "proxy": "",                     # 留空=自动探测；也可写死 http://127.0.0.1:7890
            "proxy_list": [],                # 额外线路，如 ["http://127.0.0.1:7891"]
            "search_provider": "both",       # both=DDG+Bing 一起搜并合并；也可 ddg / bing
            "search_engine": "ddg",          # 内置浏览器用哪个引擎：ddg/bing/baidu/google
            "browser_search": True,          # DDG 抓取被拦时，用内嵌真浏览器补一次
            "login_wait_sec": 180,           # 遇到要登录的页面，最多等主人登录多久
            "video_anim": True,              # 视频动画（anim/ 里的透明 webm）；关了就是手绘立绘
            "theme": "pink",                 # 界面主题：pink（粉色）/ system（跟随系统明暗）
            "chrome_path": "",               # 留空=自动找；也可写死 chrome.exe / msedge.exe
            "chrome_search_dirs": [],        # 自动找不到时再扫这些目录（开源版默认不扫，免得扫你整块盘）
            "chrome_scan_depth": 3,
            "webengine_no_sandbox": True,    # 内嵌浏览器用（部分机器上 Chromium 沙箱起不来，实测必须关）
            "key_storage": "none",           # Key 存在哪：dpapi（已加密）/ plain（明文兜底）/ none
            "city": "北京"                    # 开源版默认值；你的城市请自己改（右键菜单或 config.json）
    })
        # Key 不在 config.json 里：从加密仓库取（兼容老版明文配置）
        self._key_plaintext = False
        _stored = load_key_from_store()
        if _stored and is_placeholder_key(self.cfg.get("ds_api_key")):
            self.cfg["ds_api_key"] = _stored
        if not is_placeholder_key(self.cfg.get("ds_api_key")) and not key_store_exists():
            self._key_plaintext = True       # DPAPI 不可用，只能明文存在 config.json 里
        apply_runtime_config(self.cfg)
        
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                 | Qt.WindowType.NoDropShadowWindowHint)
        if self.cfg.get("topmost", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("大肥鱼桌宠")
        self.setAutoFillBackground(False)
        self.setStyleSheet("PetWindow { background: transparent; border: none; }")
        
        # 精灵加载
        self.sprites = {}
        # 尺寸缓存只负责布局；绘制始终使用原图，避免先缩小再放大。
        self.original_sprites = {
            name: QPixmap(os.path.join(SPRITE_DIR, f"{name}.png"))
            for name in ["正面", "侧面", "背面"]
        }
        for label, mult in SIZE_LEVELS.items():
            h = int(340 * mult)
            for name in ["正面", "侧面", "背面"]:
                sized = os.path.join(SPRITE_DIR, f"{name}_{h}.png")
                if os.path.exists(sized):
                    pix = QPixmap(sized)
                else:
                    pix = QPixmap(os.path.join(SPRITE_DIR, f"{name}.png")).scaledToHeight(
                        h, Qt.TransformationMode.SmoothTransformation)
                self.sprites[(name, h)] = pix
        self.icon = QIcon(os.path.join(SPRITE_DIR, "icon.png"))

        self.cur_h = int(340 * self.cfg["size"])
        self.win_mx = int(self.cur_h * 0.062) + 6
        self.win_w = max(p.width() for k, p in self.sprites.items() if k[1] == self.cur_h) + self.win_mx * 2
        self.win_h = self.cur_h + BUBBLE_H + MARGIN * 2 + 10
        self._canvas_offset = QPoint(0, 0)
        self.setFixedSize(self.win_w, self.win_h)

        # 状态
        self.mode = self.cfg["mode"] if self.cfg["mode"] in ("wander", "follow", "still") else "wander"
        self.dir = "down"
        self.facing = 1
        self.target = None
        self.rest_until = 0
        self.cur_speed = 0.0
        self.prev_key = None
        self.cross_t = 0.0
        self.action = None
        self.action_t = 0.0
        self.action_left = 0          # 当前动作还剩几 tick
        self.action_total = 0
        self.vx = 0.0                 # 被甩出去的速度（px/tick）
        self.vy = 0.0
        self.flying = False
        self.drag_history = []        # 拖拽轨迹，用来算甩出去的初速度
        self._drag_started_at = 0.0
        self._edge_impact_latched = False
        self._edge_impact_until = 0.0
        self._edge_impact_cooldown_until = 0.0
        self._next_action = None      # 排队的下一个动作（比如点击：先挤压再回应）
        # 视频动画（106 个透明 webm，见 anim/）
        self.video = None
        self._anim_set = None
        self._video_failed = False
        self._locate_queue = None
        if self.cfg.get("auto_locate_city", True):
            QTimer.singleShot(7000, self._auto_locate_ip)   # 起来几秒后静默刷城市
        self.bubble_text = ""
        self.bubble_until = 0
        self.bubble_inner = False
        self.last_speak_tick = 0
        self.last_system_check = 0
        self.t = 0
        self.jump_t = 0
        self.dragging = False
        self._drag_content_rect = None
        self.drag_offset = None
        self.drag_start_pos = None
        self.last_line = ""
        self.last_press_pos = None
        
        # AI 相关
        self.ds_busy = False
        self.chat_history = []  # 对话历史
        self.max_history = 40   # 最多记录40条
        self._say_queue = []    # 后台线程→主线程的气泡消息队列
        
        # 聊天暂停标志
        self.chat_paused = False

        # 护眼提醒 / 关机道别
        self.next_eye_rest = int(self.cfg.get("eye_rest_interval_min", 120) * 60000)
        self.eye_rest_until = 0
        self._eye_rest_saved = []      # 护眼时收起来的窗口，等着放回来
        self.eye_overlay = None        # 护眼大屏（按需创建）
        self._eye_overlay_up = False   # 大屏是否正占着屏幕（决定要不要把小鱼放回来）
        self._said_bye = False
        self._last_shutdown_check = 0

        # 分身：就一个窗口（对话 / 任务 / 看网页都在这儿）
        self.avatar = AvatarWindow()
        self.avatar.on_send = self._on_avatar_send
        self.avatar.on_stop = self.stop_task
        self.avatar.on_selfcheck = self.net_selfcheck
        self.task_worker = None
        self._task_busy = False
        # 配置文件监听（开源版新增）：手改 config.json 或别的程序写它，也能免重启生效
        self._cfg_watcher = None
        self._cfg_sig = config_signature()
        # 真浏览器取页通道：给分身搜索用，和窗口里的浏览器共用 profile
        self.browser_fetcher = None
        _BROWSER_FETCH["fn"] = self._fetch_by_browser
        _LOGIN_HOOK["fn"] = self._open_login_for
        
        self.food_panel = FoodPanel(self.on_food)
        # 单击延迟判定（等双击）：单击=回嘴，双击=喂食
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._on_single_click)

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(FRAME_INTERVAL)

        self.bubble_font = QFont("Microsoft YaHei UI", 11)

        # 托盘
        self.tray = QSystemTrayIcon(self.icon, self)
        self.tray.setContextMenu(self._build_menu())
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        x, y = self.cfg.get("x"), self.cfg.get("y")
        if x is None or y is None:
            screen = QApplication.primaryScreen().availableGeometry()
            x = screen.right() - self.win_w - 80
            y = screen.bottom() - self.win_h - 60
        self._move_body(int(x), int(y))
        self.show()
        self.snap_into_screen()
        if self.cfg.get("passthrough", False):
            self._apply_passthrough(True)

        # 位置定期回写（只在真的移动过时才写盘，散步时也不会频繁写文件）
        self._pos_timer = QTimer(self)
        self._pos_timer.timeout.connect(self._autosave_pos)
        self._pos_timer.start(30000)

        self._resume_eye_rest_pending()      # 上次护眼没收完的窗口，重启后接着放回来

        # 开源版：让「改配置」彻底不需要重启
        #   1) 监听 config.json —— 手改、或用别的程序写，都会自动热加载
        #   2) 还没填 Key 时轻轻提示一次（不弹窗打断，不挡操作）
        self._setup_config_watcher()
        if is_placeholder_key(self.cfg.get("ds_api_key")):
            QTimer.singleShot(6000, lambda: self.say(
                "还没填 Key：右键我 →「设置 Key」，填完立刻生效，不用重启"))

    # ---------- 配置持久化 ----------
    def save_config(self):
        """立即把内存里的配置写回 config.json（先写临时文件再原子替换，防止写坏）

        以前只有「退出」菜单里才写盘，而重启 / 关机时进程是被系统直接结束的，
        所以 Key、城市、模式、大小、位置每次开机都被重置回默认值。

        开源版加强两点：
        1) ★ **绝不把 Key 写进 config.json** —— Key 只存在 key.bin（DPAPI 加密）。
           除非 DPAPI 用不了（_key_plaintext），才退回明文写这里，绝不弄丢用户的 Key。
        2) 写盘后记一个「指纹」，这样监听文件的逻辑能分清
           「这次是我自己写的」还是「别人/别的程序改的」，不会自己跟自己打架。
        """
        try:
            # 保护：自己手里没 Key（空 or 占位符）、加密仓库里却有真的 → 取回来，别冲掉
            if is_placeholder_key(self.cfg.get("ds_api_key")):
                stored = load_key_from_store()
                if not stored:
                    # 再兜一层：老版明文配置里可能还有
                    stored = normalize_key(_read_json_file(CONFIG_PATH).get("ds_api_key", ""))
                if stored and not is_placeholder_key(stored):
                    self.cfg["ds_api_key"] = stored
                    print("[配置] 加密仓库/磁盘上已有 Key，已取回，不覆盖")

            out = dict(self.cfg)
            if getattr(self, "_key_plaintext", False):
                out["key_storage"] = "plain"    # 没办法，DPAPI 不可用
            else:
                out["ds_api_key"] = ""          # ★ Key 永远不落 config.json
                out["key_storage"] = "dpapi" if key_store_exists() else "none"

            tmp = CONFIG_PATH + ".tmp"
            d = os.path.dirname(CONFIG_PATH)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            os.replace(tmp, CONFIG_PATH)
            self._cfg_sig = config_signature()      # 记指纹：这是我写的，监听那边请忽略
            return True
        except Exception as e:
            print("配置保存失败:", e)
            return False

    def _autosave_pos(self):
        """窗口位置只在变化时写盘"""
        if (self.cfg.get("x"), self.cfg.get("y")) != (self._body_pos().x(), self._body_pos().y()):
            self.cfg["x"], self.cfg["y"] = self._body_pos().x(), self._body_pos().y()
            self.save_config()

    # ---------- 配置文件热加载（开源版新增：改配置不用重启） ----------
    def _setup_config_watcher(self):
        """盯着 config.json：被外部改动就自动重载

        为什么要它：用户可能不通过右键菜单，而是直接拿记事本改 config.json，
        或者被别的工具/脚本写入。以前这必须重启桌宠才生效。
        """
        try:
            from PySide6.QtCore import QFileSystemWatcher
            self._cfg_watcher = QFileSystemWatcher(self)
            if os.path.exists(CONFIG_PATH):
                self._cfg_watcher.addPath(CONFIG_PATH)
            self._cfg_watcher.fileChanged.connect(self._on_config_file_changed)
        except Exception as e:
            # 装不上就算了 —— 只是少了个便利功能，绝不能影响桌宠本身
            self._cfg_watcher = None
            print("配置文件监听装不上（不影响使用）:", e)

    def _on_config_file_changed(self, _path=None):
        """config.json 变了：是自己写的就忽略，是别人改的就热加载"""
        try:
            if self._cfg_watcher is not None and CONFIG_PATH not in self._cfg_watcher.files():
                self._cfg_watcher.addPath(CONFIG_PATH)   # os.replace 会掉监听，重新挂上
        except Exception:
            pass
        sig = config_signature()
        if sig is not None and sig == self._cfg_sig:
            return                                        # 指纹一样 = 我自己刚写的，别理它
        QTimer.singleShot(120, self._reload_config_from_disk)

    def _reload_config_from_disk(self):
        """把磁盘上的 config.json 重新读进内存并立刻生效（不重启）

        安全底线和 save_config 一致：
        - 磁盘上 Key 是空的/占位符、而内存里有真的 → 保留内存里的，不被清掉
        - 只认已知字段，避免别人往文件里塞奇怪的东西带坏程序
        - ★ 手工在 config.json 里填了 Key → 收进来加密存好，再把配置里的明文抹掉
        """
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                disk = json.load(f)
        except Exception as e:
            print("配置重载失败（保持原设置）:", e)
            return
        if not isinstance(disk, dict):
            return
        sig = config_signature()
        if sig is not None:
            self._cfg_sig = sig                          # 认下这次改动，避免重复触发

        key_from_file = False
        changed = []
        for k, v in disk.items():
            if k not in self.cfg:
                continue                                 # 不认外来字段
            if k == "ds_api_key":
                v = normalize_key(v)
                if is_placeholder_key(v):
                    continue                             # 想用空值/占位符冲掉真 Key？不干
                if v == normalize_key(self.cfg.get("ds_api_key")):
                    continue                             # 和内存里一样，不用管
                # 用户在记事本里手填了 Key：收进加密仓库，稍后把 config.json 里的明文抹掉
                self.cfg["ds_api_key"] = v
                self._key_plaintext = (save_key_to_store(v) == "plain")
                key_from_file = True
                changed.append(k)
                continue
            if self.cfg.get(k) != v:
                changed.append(k)
                self.cfg[k] = v
        if not changed:
            return
        try:
            apply_runtime_config(self.cfg)
        except Exception:
            pass
        if key_from_file:
            self.save_config()      # 抹掉 config.json 里的明文 Key（并更新指纹）
        print("[配置] 检测到外部改动，已热加载:", ", ".join(sorted(changed))[:120])
        # 只报「安全」的字段名；Key 只报有没有，绝不回显内容
        shown = ["Key（已加密收好）" if c == "ds_api_key" else c for c in sorted(changed)[:4]]
        self.say("配置已自动更新：%s（不用重启）" % "、".join(shown))

    def _open_config_dir(self):
        """打开配置所在文件夹，并选中 config.json"""
        try:
            if os.path.exists(CONFIG_PATH):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(CONFIG_PATH)])
            else:
                os.startfile(CONFIG_DIR if os.path.isdir(CONFIG_DIR) else APP_DIR)
            self.say("配置在这儿，别把 Key 截图发出去")
        except Exception as e:
            self.say("打不开文件夹：%s" % str(e)[:30])

    # ---------- 绘制 ----------
    def paintEvent(self, _):
        dpr = self.devicePixelRatioF()
        now = self.t * TICK / 1000.0
        video = self.video
        cache_key = None
        if video is not None and video.frame_ready and video.frame_image is not None:
            r = video.render_rect
            cache_key = (video.frame_image.cacheKey(), r.x(), r.y(), r.width(), r.height(),
                         video.mirror, self.width(), self.height(), dpr,
                         self.bubble_text if now < self.bubble_until else "",
                         self.bubble_inner, self.bubble_font.toString(), self.cfg.get("theme"))
            if cache_key == getattr(self, "_video_paint_key", None):
                self._present_pet_frame(self._video_paint_image, None)
                return
        image = QImage(round(self.width() * dpr), round(self.height() * dpr),
                       QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(dpr)
        image.fill(Qt.GlobalColor.transparent)
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.bubble_text and now < self.bubble_until:
            _t = _theme()
            if self.bubble_inner:
                bfont = QFont(self.bubble_font)
                bfont.setItalic(True)
                bg, fg = QColor(*_t["bubble_inner_bg"]), QColor(*_t["bubble_inner_fg"])
            else:
                bfont = QFont(self.bubble_font)
                bg, fg = QColor(*_t["bubble_bg"]), QColor(*_t["bubble_fg"])
            fm = QFontMetrics(bfont)
            max_w = min(240, self.win_w - 16)
            words = self.bubble_text
            lines = []
            cur = ""
            for ch in words:
                if fm.horizontalAdvance(cur + ch) > max_w - 20:
                    lines.append(cur)
                    cur = ch
                else:
                    cur += ch
            lines.append(cur)
            bw = max(fm.horizontalAdvance(l) for l in lines) + 20
            bh = len(lines) * fm.height() + 14
            bx = self._canvas_offset.x() + (self.win_w - bw) / 2
            by = self._canvas_offset.y() + 6.0
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(bx, by, bw, bh), 10, 10)
            tail = QPointF(self._canvas_offset.x() + self.win_w / 2, by + bh)
            p.drawPolygon(QPolygonF([tail, QPointF(tail.x() - 6, tail.y() + 8), QPointF(tail.x() + 6, tail.y() + 8)]))
            p.setPen(fg)
            p.setFont(bfont)
            for i, l in enumerate(lines):
                p.drawText(QRectF(bx, by + 7 + i * fm.height(), bw, fm.height()),
                           Qt.AlignmentFlag.AlignCenter, l)

        cx = self._canvas_offset.x() + self.win_w / 2
        walking = self.target is not None and not self.dragging and not self.flying
        if walking:
            sway = math.sin(now * 9.0) * 3.5
            bob = -abs(math.sin(now * 4.5)) * 7.0
        else:
            sway = math.sin(now * 2.5) * 1.5
            bob = 0.0
        breath = 1.0 + 0.02 * math.sin(now * 2.5)
        scale = breath
        jump = -abs(math.sin(self.jump_t * 3.14159)) * 14 * self.jump_t if self.jump_t > 0 else 0
        # 动作表给的变换（动作名 → 每帧函数）
        act = {"rot": 0.0, "sx": 0.0, "sy": 0.0, "dx": 0.0, "dy": 0.0,
               "alpha": 1.0, "sprite": None, "facing": None, "pivot": "bottom"}
        if self.action:
            a = _ACTION_BY_KEY.get(self.action)
            if a:
                try:
                    act.update(a["fn"](self, self._action_progress()) or {})
                except Exception as e:
                    print("动作绘制出错(%s): %s" % (self.action, e))
        if self.flying:               # 被甩飞时按速度倾斜、拉长一点
            act["rot"] = act["rot"] + max(-22.0, min(22.0, self.vx * 1.6))
            act["sy"] = act["sy"] + min(0.10, abs(self.vy) * 0.004)

        def draw_one(key, opacity):
            if key is None:
                return
            name, h, facing = key
            pix = self.sprites[(name, h)]
            ph = pix.height() * scale * (1 + act["sy"])
            pw = max(8.0, pix.width() * scale * (1 + act["sx"]))
            dx = cx - pw / 2 + act["dx"]
            bottom = self._canvas_offset.y() + BUBBLE_H + MARGIN + self.cur_h
            dy = bottom - ph + jump + bob + act["dy"]
            p.save()
            p.setOpacity(opacity * act["alpha"])
            pivot_y = bottom - ph / 2 if act.get("pivot") == "center" else bottom
            p.translate(cx, pivot_y)
            p.rotate(sway + act["rot"])
            p.translate(-cx, -pivot_y)
            if facing < 0:
                p.translate(cx, 0)
                p.scale(-1, 1)
                p.translate(-cx, 0)
            source = self.original_sprites.get(name, pix)
            if source.isNull():
                source = pix
            p.drawPixmap(QRectF(dx, dy, pw, ph), source,
                         QRectF(0, 0, source.width(), source.height()))
            p.restore()

        cur_key = self._sprite_key(act.get("sprite"), act.get("facing"))
        if self.video is not None and self.video.frame_ready and self.video.frame_image is not None:
            # 在本体窗口绘制真实透明视频帧，鼠标直接命中角色，不再叠放浏览器窗口。
            rect = QRectF(self.video.render_rect)
            frame, frame_rect = self._quality_video_frame(rect, dpr)
            if self.dragging:
                if self._drag_content_rect is None:
                    self._drag_content_rect = QRectF(frame_rect)
                else:
                    # 悬空反馈素材会轻微改变角色的画面位置和轮廓尺寸。
                    # 拖动时把裁出的角色固定在首帧位置和大小，消除“越拖越缩”的错觉。
                    frame_rect = QRectF(self._drag_content_rect)
            p.save()
            if self.video.mirror:
                p.translate(rect.center().x(), 0)
                p.scale(-1, 1)
                p.translate(-rect.center().x(), 0)
            p.drawImage(frame_rect, frame)
            p.restore()
            self._video_paint_key = cache_key
            self._video_paint_image = image
            self._present_pet_frame(image, p)
            return
        if self.cross_t > 0:
            draw_one(self.prev_key, self.cross_t)
            draw_one(cur_key, 1.0 - self.cross_t)
        else:
            draw_one(cur_key, 1.0)
        self._video_paint_key = None
        self._present_pet_frame(image, p)

    def _quality_video_frame(self, rect, dpr):
        """绘制后台已处理好的帧；显示缩放改变时暂用原帧等待下一帧。"""
        source = self.video.frame_image
        key = (source.cacheKey(), rect.width(), rect.height(), dpr)
        if key != getattr(self, "_quality_frame_key", None):
            return source, rect
        x0, y0, x1, y1 = self._quality_bounds
        crop_rect = QRectF(round((rect.x()+x0*rect.width()/source.width())*dpr)/dpr,
                          round((rect.y()+y0*rect.height()/source.height())*dpr)/dpr,
                          self._quality_frame.width()/dpr, self._quality_frame.height()/dpr)
        return self._quality_frame, crop_rect

    @staticmethod
    def _build_quality_frame(source, rect, dpr):
        """后台每帧缩放一次；锐化只改变颜色，保留 Lanczos 缩放后的 alpha。"""
        default_bounds = (0, 0, source.width(), source.height())
        if PILImage is None or rect.isEmpty():
            return source, default_bounds
        rgba = source.convertToFormat(QImage.Format.Format_RGBA8888)
        pil = PILImage.frombytes("RGBA", (rgba.width(), rgba.height()), bytes(rgba.constBits()))
        # 解码器会在空白画幅留下 alpha=1 的噪点；不让这些噪点扩大缩放范围。
        bounds = pil.getchannel("A").point(lambda a: 255 if a > 4 else 0).getbbox()
        if not bounds:
            return source, default_bounds
        x0, y0, x1, y1 = bounds
        bounds = (max(0, x0-2), max(0, y0-2), min(source.width(), x1+2), min(source.height(), y1+2))
        x0, y0, x1, y1 = bounds
        size = (max(1, round((x1-x0)*rect.width()/source.width()*dpr)),
                max(1, round((y1-y0)*rect.height()/source.height()*dpr)))
        scaled = pil.crop(bounds).resize(size, PILImage.Resampling.LANCZOS)
        alpha = scaled.getchannel("A")
        scaled = scaled.convert("RGB").filter(ImageFilter.UnsharpMask(
            radius=0.55, percent=65, threshold=3)).convert("RGBA")
        scaled.putalpha(alpha)
        enhanced = QImage(scaled.tobytes(), size[0], size[1], size[0]*4,
                          QImage.Format.Format_RGBA8888).copy()
        return enhanced, bounds

    def _present_pet_frame(self, image, painter):
        if painter is not None:
            painter.end()
        output = QPainter(self)
        # 覆盖旧缓冲区的透明像素，防止轮廓移动后残留半透明底色。
        output.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        output.drawImage(0, 0, image)
        output.end()
        if image.cacheKey() == getattr(self, "_mask_image_key", None):
            return
        self._mask_image_key = image.cacheKey()
        # 窗口区域与实际角色/气泡轮廓一致，透明区域既不显示系统背景也不拦截点击。
        # QWidget 的区域使用逻辑坐标，不能把高 DPI 的物理像素直接交给 setMask。
        mask_image = image.scaled(self.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
        mask_image.setDevicePixelRatio(1.0)
        region = QRegion(QBitmap.fromImage(mask_image.createAlphaMask(
            Qt.ImageConversionFlag.ThresholdAlphaDither)))
        if region != getattr(self, "_paint_region", None):
            self._paint_region = region
            self.setMask(region)

    def _sprite_key(self, name_override=None, facing_override=None):
        if name_override:
            facing = facing_override
            if facing is None:
                facing = self.facing if name_override == "侧面" else 1
            return (name_override, self.cur_h, facing)
        name = {"left": "侧面", "right": "侧面", "up": "背面", "down": "正面"}[self.dir]
        return (name, self.cur_h, self.facing if self.dir in ("left", "right") else 1)

    def _set_dir(self, d, facing=None):
        if d != self.dir:
            self.prev_key = self._sprite_key()
            self.cross_t = 1.0
            self.dir = d
        if facing is not None and facing != self.facing:
            self.facing = facing

    def _body_pos(self):
        """持久化和移动使用角色原有坐标，扩展场景时不改变角色位置。"""
        return self.pos() + self._canvas_offset

    def _move_body(self, *args):
        position = QPoint(*args) if len(args) == 2 else QPoint(args[0])
        video = getattr(self, "video", None)
        if video is not None and video.clip and not video.render_rect.isEmpty():
            left, top, right, bottom = self._scene_body_limits()
            position = QPoint(max(left, min(right, position.x())),
                              max(top, min(bottom, position.y())))
        self.move(position - self._canvas_offset)

    def _fit_animation_canvas(self, scene=None):
        """扩大视频画幅显示更多动作环境；透明部分仍由原生 alpha 轮廓穿透。"""
        area = QRectF(0, 0, self.win_w, self.win_h)
        if scene is not None:
            area = area.united(scene.adjusted(-2, -2, 2, 2))
        area = area.toAlignedRect()
        offset = QPoint(-area.x(), -area.y())
        if self.size() != area.size() or offset != self._canvas_offset:
            body_position = self._body_pos()
            self._canvas_offset = offset
            self.setFixedSize(area.size())
            self._move_body(body_position)
            self._video_paint_key = None
        return offset

    def _scene_screen_rect(self):
        center = self._body_pos() + QPoint(self.win_w // 2, self.win_h // 2)
        screen = QApplication.screenAt(center) or self.screen() or QApplication.primaryScreen()
        return screen.availableGeometry()

    def _scene_body_limits(self):
        """角色坐标可移动的范围，同时给整个场景留出空间。"""
        geo = self._scene_screen_rect()
        offset = self._canvas_offset
        return (geo.left() + offset.x(), geo.top() + offset.y(),
                geo.left() + max(0, geo.width() - self.width()) + offset.x(),
                geo.top() + max(0, geo.height() - self.height()) + offset.y())

    def _desktop_body_limits(self):
        """桌面虚拟屏幕的外沿；相邻显示器之间可以正常拖动穿过。"""
        screens = QApplication.screens()
        if not screens:
            return self._scene_body_limits()
        geo = screens[0].availableGeometry()
        for screen in screens[1:]:
            geo = geo.united(screen.availableGeometry())
        offset = self._canvas_offset
        return (geo.left() + offset.x(), geo.top() + offset.y(),
                geo.left() + max(0, geo.width() - self.width()) + offset.x(),
                geo.top() + max(0, geo.height() - self.height()) + offset.y())

    def _trigger_edge_impact(self):
        """快速碰到显示器边界后，播放受惊揉头反馈并短暂抑制重复触发。"""
        now = time.monotonic()
        if now < self._edge_impact_cooldown_until:
            return False
        self._edge_impact_latched = True
        self._edge_impact_cooldown_until = now + 1.15
        self._edge_impact_until = now + 1.8
        self._drag_content_rect = None
        self.play_action("bump", force=True, bubble="💫")
        self._bubble_now("哎哟，撞到边边了！揉揉脑袋……", 1800)
        return True

    def _keep_scene_on_screen(self):
        left, top, right, bottom = self._scene_body_limits()
        position = self._movement_position()
        x = max(left, min(right, position.x()))
        y = max(top, min(bottom, position.y()))
        changed = (round(x), round(y)) != (self._body_pos().x(), self._body_pos().y())
        if changed:
            self._move_precise(x, y)
        if self.target is not None:
            self.target = (max(left + self.win_w / 2, min(right + self.win_w / 2, self.target[0])),
                           max(top + self.win_h / 2, min(bottom + self.win_h / 2, self.target[1])))
        return changed

    # ---------- 逻辑 ----------
    def _movement_position(self):
        # QWidget 位置是整数；保留小数余量，避免高刷新率下左右速度不一致。
        if getattr(self, "_movement_widget_pos", None) != self._body_pos():
            self._movement_float_pos = QPointF(self._body_pos())
        return self._movement_float_pos

    def _move_precise(self, x, y):
        video = getattr(self, "video", None)
        if video is not None and video.clip and not video.render_rect.isEmpty():
            left, top, right, bottom = self._scene_body_limits()
            x, y = max(left, min(right, x)), max(top, min(bottom, y))
        self._movement_float_pos = QPointF(x, y)
        self._move_body(round(x), round(y))
        self._movement_widget_pos = self._body_pos()

    def tick(self):
        time_step = FRAME_INTERVAL / TICK
        self.t += time_step

        # 处理后台线程（DeepSeek 等）排队的气泡消息，Qt 界面必须在主线程更新
        if self._say_queue:
            for text in self._say_queue:
                self.say(text)
            self._say_queue.clear()

        if self._locate_queue:            # 定位线程的结果（系统授权定位 / IP 兜底）
            res, why, auto, quiet = self._locate_queue
            self._locate_queue = None
            if res:
                old_city = self.cfg.get("city") or ""
                if res.get("city"):
                    self.cfg["city"] = res["city"]
                if res.get("lat") is not None:
                    self.cfg["lat"], self.cfg["lon"] = res["lat"], res["lon"]
                self.cfg["loc_src"] = res.get("src", "")
                self.save_config()
                where = res.get("city") or ("%.2f, %.2f" % (res["lat"], res["lon"]))
                if not quiet:
                    self.say("定位到 %s（%s）" % (where, res.get("src", "")))
                elif (self.cfg.get("city") or "") != old_city:
                    self.say("城市自动更新成 %s（%s）" % (self.cfg.get("city"), res.get("src", "")))
                if auto:
                    self._get_weather()
            elif not quiet:
                self.say("定位没成功：%s" % (why or "未知原因"))

        self.check_system_status()

        # 护眼骚扰 / 关机道别：放在 chat_paused 提前返回之前，聊天和拖拽时也照常生效
        now_ms = self.t * TICK
        self._check_eye_rest(now_ms)
        self._check_shutdown(now_ms)
        
        if self.jump_t > 0:
            self.jump_t = max(0.0, self.jump_t - 0.06 * time_step)
        if self.cross_t > 0:
            self.cross_t = max(0.0, self.cross_t - 0.15 * time_step)
        if self.action:
            self.action_left -= time_step
            self.action_t = self._action_progress()
            if self.action_left <= 0:
                self._finish_action()

        if self.flying:               # 被甩出去：抛物线 + 边缘反弹 + 摩擦停稳
            self._fly_step()
            self.update()
            return

        self._sync_video()            # 视频窗跟着本体走
        
        if self.chat_paused:
            self.update()
            return
        
        if self.dragging:
            self.update()
            return

        if self.mode == "follow":
            cursor = self.cursor().pos()
            screen = QApplication.screenAt(cursor) or self.screen() or QApplication.primaryScreen()
            geo = screen.availableGeometry()
            near = (self._body_pos().x() - 100 <= cursor.x() <= self._body_pos().x() + self.win_w + 100 and
                    self._body_pos().y() - 100 <= cursor.y() <= self._body_pos().y() + self.win_h + 100)
            if near:
                self.target = None
            else:
                tx = max(geo.left(), min(geo.right() - self.win_w, cursor.x() - self.win_w / 2))
                ty = max(geo.top(), min(geo.bottom() - self.win_h, cursor.y() - 90))
                self.target = (tx, ty)
        elif self.mode == "wander":
            if self.target is None:
                if now_ms < self.rest_until:
                    self._maybe_idle_action()
                    self.update()
                    return
                geo = (self.screen() or QApplication.primaryScreen()).availableGeometry()
                self.target = (random.randint(geo.left() + 40, geo.right() - self.win_w - 40),
                               random.randint(geo.top() + 40, geo.bottom() - self.win_h - 40))
        else:
            self._maybe_idle_action()
            self.update()
            return

        if self.target is not None:
            position = self._movement_position()
            cx, cy = position.x() + self.win_w / 2, position.y() + self.win_h / 2
            dx, dy = self.target[0] - cx, self.target[1] - cy
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < 12:
                self.target = None
                self.rest_until = self.t * TICK + random.randint(8000, 18000)
                self._set_dir("down")
            else:
                step = self.cur_speed * FRAME_INTERVAL / 1000.0
                nx, ny = cx + dx / dist * step, cy + dy / dist * step
                self._move_precise(nx - self.win_w / 2, ny - self.win_h / 2)
                if abs(dx) > abs(dy) * 1.15:
                    self._set_dir("left" if dx < 0 else "right", 1 if dx < 0 else -1)
                else:
                    self._set_dir("up" if dy < 0 else "down")
            if random.random() < 0.002 * time_step and self.jump_t == 0:
                self.jump_t = 0.5
        target_speed = SPEED if self.target is not None else 0.0
        self.cur_speed += (target_speed - self.cur_speed) * (1 - 0.7 ** time_step)
        self.update()

    # ---------- 视频动画 ----------
    def anim_names(self):
        if self._anim_set is None:
            self._anim_set = scan_anims()
        return self._anim_set

    def video_ready(self):
        """视频模式能用吗：开关开着 + 内嵌 Chromium 可用 + anim/ 里有素材"""
        if self._video_failed or not (VIDEO_FFMPEG or WEBENGINE_OK):
            return False
        if not self.cfg.get("video_anim", True):
            return False
        return bool(self.anim_names())

    def clip_for(self, key):
        """动作键 / 池名 → 实际存在的 clip 名（没有就返回空 → 退回手绘立绘）"""
        names = self.anim_names()
        if key in ANIM_POOLS:
            pool = [c for c in ANIM_POOLS[key] if c in names]
            return random.choice(pool) if pool else ""
        clip = ACTION_TO_CLIP.get(key, "")
        return clip if clip in names else ""

    def show_clip(self, clip, loop=False):
        if not self.video_ready() or not clip:
            return False
        if self.video is None:
            self.video = VideoBody(on_clip_end=self._on_clip_end)
            self.video.target_pet = self
        if not self.video.ensure():
            self._video_failed = True
            return False
        ok = self.video.play(clip, loop=loop)
        self._sync_video()
        self.update()
        return ok

    def _on_clip_end(self, clip):
        """一段演完 → 接回待机循环（和 dsh-pet 的动画链一个意思）"""
        if self.video is not None and self.video.clip and not self.flying:
            if self.dragging:
                self._drag_content_rect = None
                drag = self.clip_for("拖拽")
                if drag:
                    self.video.play(drag, loop=True)
                    return
            idle = self.clip_for("待机")
            if idle:
                self.video.play(idle, loop=True)

    def _video_idle(self):
        """没动作时就循环待机动画"""
        if not self.video_ready():
            return False
        return self.show_clip(self.clip_for("待机"), loop=True)

    def play_random_clip(self, say=False):
        pool = [c for c in (ANIM_POOLS["卖萌"] + ANIM_POOLS["玩耍"] + ANIM_POOLS["时节"])
                if c in self.anim_names()]
        if not pool:
            return False
        clip = random.choice(pool)
        if say:
            self.say("给你演一个：%s" % clip)
        return self.show_clip(clip, loop=False)

    def _sync_video(self):
        """更新视频帧在本体中的绘制位置，跟随走路、拖拽和飞行。"""
        if self.video is None or not self.video.clip:
            self._fit_animation_canvas()
            return
        if not self.isVisible():
            return                    # 本体藏起来了（护眼/显示隐藏）→ 视频也别冒出来
        anchor = self._body_pos()
        cx = anchor.x() + self.win_w / 2
        bottom = self._body_pos().y() + BUBBLE_H + MARGIN + self.cur_h
        self.video.fit_to(cx, bottom, self.cur_h, mirror=self.facing < 0)
        moved = self._keep_scene_on_screen()
        if moved or anchor != self._body_pos():
            # 更新记录的全局锚点，避免异步量到角色包围盒后使用旧位置重新摆放。
            cx = self._body_pos().x() + self.win_w / 2
            bottom = self._body_pos().y() + BUBBLE_H + MARGIN + self.cur_h
            self.video.fit_to(cx, bottom, self.cur_h, mirror=self.facing < 0)

    def set_video_anim(self, on):
        """切换视频动画 / 手绘立绘"""
        self.cfg["video_anim"] = bool(on)
        self.save_config()
        if on:
            if self._video_idle():
                self.say("视频动画开啦～")
            else:
                self.say("视频素材没找到（anim/ 目录），先用手绘立绘")
        else:
            if self.video is not None:
                self.video.stop()
            self._fit_animation_canvas()
            self.say("换回手绘立绘～")
        self.update()

    def _maybe_idle_action(self):
        """闲着的时候按权重随机接一个动作（有点 dsh-pet 那种「动画链」的意思）"""
        if self.action or self.flying or self.jump_t > 0 or self.dragging:
            return
        if (self.video is not None and self.video.clip
                and not self.video.loop):
            return                                       # 正在演一个动作 clip，别插队
        if (self.video_ready() and self.video is not None
                and self.video.bbox is None):
            return                                       # 还没量到角色位置 → 先让待机多播会儿
        if random.random() < 0.010 * FRAME_INTERVAL / TICK:
            if self.video_ready():
                self.play_random_clip()                  # 视频模式：随机抽一个 clip
            else:
                self.play_action(self._pick_action())
        if self.t - self.last_speak_tick >= 2400 and random.random() < 0.004 * FRAME_INTERVAL / TICK:
            self.last_speak_tick = self.t
            if random.random() < 0.75:
                self.say(random.choice(INNER_LINES), inner=True)
            else:
                self.say(random.choice(LINES))

    # ---------- 动作 ----------
    def _pick_action(self):
        pool = [a for a in ACTIONS if a.get("weight", 0) > 0]
        total = sum(a["weight"] for a in pool)
        r = random.random() * total
        for a in pool:
            r -= a["weight"]
            if r <= 0:
                return a["key"]
        return pool[0]["key"] if pool else "sway"

    def play_action(self, key, force=False, bubble=None):
        """播一个动作。force=True 时打断当前动作（菜单点播/任务联动用）

        视频模式下优先播对应的真·动画 clip；没有对应素材才退回手绘立绘变换。
        """
        a = _ACTION_BY_KEY.get(key)
        if not a:
            return
        if key != "squash" and self.video_ready():
            clip = ACTION_TO_CLIP.get(key, "")
            if clip and clip in self.anim_names() and self.show_clip(clip, loop=False):
                self._bubble_now(bubble or a.get("bubble"), 1400)
                return
        if self.action and not force:
            if self.action == key and self.action_left > 3:
                return                                   # 同一个动作别打断重来
            if self.action_left > 4:
                self._next_action = key                  # 先排队，等这个演完
                return
        self.action = key
        self.action_total = self.action_left = max(1, int(a["ticks"]))
        self.action_t = 0.0
        self._bubble_now(bubble or a.get("bubble"), 1300)
        self.update()

    def _finish_action(self):
        was = self.action
        self.action = None
        self.action_left = 0
        self.action_total = 0
        self.action_t = 0.0
        self.update()
        nxt = self._next_action                          # 排队的优先
        self._next_action = None
        if nxt:
            self.play_action(nxt, force=True)
            return
        # 首尾相接：有一定概率马上接下一个（像 dsh-pet 的动画链）
        if was not in ("squash", "droop", "think", "bump") and random.random() < 0.35:
            self.play_action(self._pick_action())

    def _action_progress(self):
        if not self.action or self.action_total <= 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - self.action_left / float(self.action_total)))

    def _bubble_now(self, text, ms=1300):
        """动作配的表情气泡：不走说话的冷却，说冒就冒"""
        if not text:
            return
        self.bubble_text = str(text)
        self.bubble_until = self.t * TICK / 1000.0 + ms / 1000.0

    # ---------- 甩抛物理 ----------
    def _throw(self, vx, vy):
        """松手时带速度 → 抛物线飞出去"""
        self.vx, self.vy = float(vx), float(vy)
        self.flying = True
        self.target = None
        self.dragging = False
        self._drag_content_rect = None
        self.drag_offset = None
        self.chat_paused = False
        if random.random() < 0.5:
            self.say(random.choice(FLY_LINES))
        self._bubble_now("💨", 900)

    def _fly_step(self):
        left, top, right, ground = self._scene_body_limits()
        time_step = FRAME_INTERVAL / TICK
        self.vy += 1.15 * time_step                        # 重力
        position = self._movement_position()
        nx = position.x() + self.vx * time_step
        ny = position.y() + self.vy * time_step
        if nx < left:
            impact_speed = abs(self.vx) * 1000.0 / TICK
            nx, self.vx = left, -self.vx * 0.55
            if impact_speed >= EDGE_IMPACT_SPEED:
                self._trigger_edge_impact()
        elif nx > right:
            impact_speed = abs(self.vx) * 1000.0 / TICK
            nx, self.vx = right, -self.vx * 0.55
            if impact_speed >= EDGE_IMPACT_SPEED:
                self._trigger_edge_impact()
        if ny < top:
            impact_speed = abs(self.vy) * 1000.0 / TICK
            ny, self.vy = top, -self.vy * 0.45
            if impact_speed >= EDGE_IMPACT_SPEED:
                self._trigger_edge_impact()
        if ny >= ground:
            ny = ground
            if abs(self.vy) < 2.2:
                self.vy = 0.0
                self.vx *= 0.55
                if abs(self.vx) < 0.7:
                    self._stop_flying()
                    return
            else:
                self.vy = -self.vy * 0.45                 # 落地弹一下
                self.vx *= 0.82
                self._bubble_now("💨", 600)
        self.vx *= 0.995 ** time_step                      # 空气阻力
        self._move_precise(nx, ny)
        self.cfg["x"], self.cfg["y"] = self._body_pos().x(), self._body_pos().y()
        self._sync_video()                                # 飞的时候视频也得跟着

    def _stop_flying(self):
        self.flying = False
        self.vx = self.vy = 0.0
        self.target = None
        self.rest_until = self.t * TICK + random.randint(4000, 9000)
        self.play_action("squash", force=True)            # 落地 Q 弹一下
        self._video_idle()
        if random.random() < 0.45:
            self.say(random.choice(LANDING_LINES))
        self.save_config()

    def _queue_say(self, text):
        """后台线程调用：只入队，由主线程 tick 统一弹出显示（线程安全）"""
        self._say_queue.append(text)

    def say(self, text, inner=False):
        if text == self.last_line and not text.startswith("天气"):
            return
        self.last_line = text
        self.bubble_inner = inner
        self.bubble_text = f"（{text}）" if inner else text
        self.bubble_until = self.t * TICK / 1000.0 + 2.8
        self.update()

    def check_system_status(self):
            now = self.t * TICK

            if now - getattr(self, "last_system_check", 0) < 10000:
                return

            self.last_system_check = now

            cpu = psutil.cpu_percent()

            if cpu >= 90:
                self.say("CPU跑满了，再这样下去我就卡死了")
                return

            ram = psutil.virtual_memory().percent

            if ram >= 95:
                self.say("内存爆了，快关掉几个没用的东西吧，注意，别把我关了")
                return

            if GPU_AVAILABLE:
                try:
                    handle = pynvml.nvmlDeviceGetHandleByIndex(0)

                    temp = pynvml.nvmlDeviceGetTemperature(
                        handle,
                        pynvml.NVML_TEMPERATURE_GPU
                    )

                    if temp > 80:
                        self.say("我感觉我的鱼鳍快熟了")

                except Exception as e:
                    print("GPU读取失败:", e)

    # ---------- 分身（就一个窗口：对话 / 任务 / 看网页）----------
    def open_avatar(self, text=None):
        """打开（或叫回）分身窗口；给了 text 就填进输入框"""
        try:
            if text:
                self.avatar.input.setPlainText(text)
            self.avatar.show()
            self.avatar.raise_()
            self.avatar.activateWindow()
            self.avatar.input.setFocus()
        except Exception as e:
            self.say("分身开不起来：%s" % str(e)[:40])

    def _on_avatar_send(self, text, already_logged=False):
        self.run_task(text, already_logged=already_logged)

    def _fetch_by_browser(self, url, timeout=30):
        """走内嵌真 Chromium 取页面（子线程调用 → 由信号转到主线程干活）"""
        if self.browser_fetcher is None:
            self.browser_fetcher = BrowserFetcher(self.avatar)
        return self.browser_fetcher.request(url, timeout)

    def _open_login_for(self, url):
        """遇到要登录的页面：把**网站自己的**登录页开到分身窗口里（跳转交给网站），
        登录完 Cookie 留在同一个 profile，分身后台自动重取、继续干活。

        桌宠本身不做登录界面、也不存账号密码 —— 登录页长什么样、要不要扫码，
        全归网站管。
        """
        try:
            self.open_avatar()
            self.avatar.set_status("等你登录…")
            self.avatar.append_note("这个页面要登录，我把网站的登录页打开了 —— "
                                    "你登录完我自动继续，不用重新说一遍")
            self.avatar.open_url(url)
            self.say("要登录一下，我在窗口里等你～")
        except Exception as e:
            print("打开登录页失败:", e)

    def run_task(self, text, already_logged=False):
        """把活儿交给分身：后台搜索 + 读网页 + 写总结，过程和结果都写进分身窗口"""
        text = (text or "").strip()
        if not text:
            return
        if is_placeholder_key(self.cfg.get("ds_api_key")):
            self.open_avatar()
            self.avatar.append_note("还没设置 Key：右键桌宠 →「设置 Key」"
                                    "（填完立刻生效，不用重启）")
            self.say("先设置 Key 我才能干活！填完就能用～")
            return
        if self._task_busy:
            self.open_avatar()
            self.avatar.append_note("上一件还没干完，等它跑完～")
            return
        self._task_busy = True
        if not already_logged:                 # 从菜单/剪贴板进来的，先记一笔
            self.avatar.append_user(text)
        self.avatar.show()
        self.avatar.raise_()
        self.avatar.begin_task(text)
        self.say(random.choice(TASK_START_LINES))

        worker = TaskWorker(self.cfg, text)
        worker.status.connect(self._on_task_status)
        worker.done.connect(self._on_task_done)
        worker.error.connect(self._on_task_error)
        self.task_worker = worker
        threading.Thread(target=worker.run, daemon=True).start()

    def stop_task(self):
        if self.task_worker is not None:
            self.task_worker.stop_flag.set()
            self.avatar.set_status("正在停止…")
            self.avatar.append_note("收到，正在停下…")

    def _on_task_status(self, text):
        self.avatar.set_status(text)
        self.avatar.append_note(text)          # 过程也写进窗口，看得见它在干什么
        self.play_action("think")              # 干活时鱼在思考（参考 dsh-pet 的工作状态联动）

    def _on_task_done(self, body, sources):
        self._task_busy = False
        urls = re.findall(r"\]\((https?://[^)\s]+)\)", sources or "")
        for u in re.findall(r"(https?://[^\s)）\]]+)", body or ""):
            if u not in urls:
                urls.append(u)
        self.avatar.set_result_urls(urls)       # 工具栏 ◀ ▶ 能逐个翻看
        self.avatar.show_result(body, sources)
        self.play_action("happy", force=True)   # 干完了开心一下
        self.say(random.choice(TASK_DONE_LINES))

    def _on_task_error(self, msg):
        self._task_busy = False
        self.avatar.show_error(msg)
        self.play_action("droop", force=True)   # 出错垂头叹气
        self.say("任务出问题了，分身窗口里写了原因")

    def task_from_clipboard(self):
        txt = QApplication.clipboard().text().strip()
        self.open_avatar()
        if not txt:
            self.avatar.append_note("剪贴板是空的")
            self.say("剪贴板是空的呀")
            return
        self.run_task("请总结下面这段内容：先一句话结论，再列要点，最后说一句值得注意的地方。\n\n" + txt)

    def net_selfcheck(self):
        """联网自检：线路 / 搜索通道 / 浏览器 / 渲染，结果直接写进分身窗口"""
        self.open_avatar()
        self._task_busy = True
        worker = NetCheckWorker(self.cfg)
        worker.status.connect(self._on_task_status)
        worker.done.connect(self._on_task_done)
        worker.error.connect(self._on_task_error)
        self.task_worker = worker
        threading.Thread(target=worker.run, daemon=True).start()

    # ---------- 护眼提醒（骚扰）----------
    def _eye_rest_interval_ms(self):
        try:
            mins = float(self.cfg.get("eye_rest_interval_min", 120))
        except Exception:
            mins = 120.0
        return max(60000, int(mins * 60000))   # 下限 1 分钟，方便自己调着玩

    def _check_eye_rest(self, now_ms):
        if not self.cfg.get("eye_rest_enabled", True):
            return
        if self.eye_rest_until:
            if now_ms >= self.eye_rest_until:
                self._end_eye_rest()
        elif now_ms >= self.next_eye_rest:
            self._start_eye_rest(now_ms)

    def _start_eye_rest(self, now_ms=None):
        if now_ms is None:
            now_ms = self.t * TICK
        try:
            rest_ms = int(float(self.cfg.get("eye_rest_duration_min", 10)) * 60000)
        except Exception:
            rest_ms = 600000
        rest_ms = max(10000, rest_ms)
        self.eye_rest_until = now_ms + rest_ms
        self.next_eye_rest = now_ms + self._eye_rest_interval_ms()
        # 关键动作：把桌面上你开着的窗口全收起来，逼你离开屏幕
        if self.cfg.get("eye_rest_minimize_windows", True):
            try:
                self._eye_rest_saved = minimize_windows()
            except Exception as e:
                self._eye_rest_saved = []
                print("收窗口失败:", e)
            self.cfg["eye_rest_pending"] = [list(x) for x in self._eye_rest_saved]
            self.cfg["eye_rest_restore_at"] = int((time.time() + rest_ms / 1000.0) * 1000)
        else:
            self._eye_rest_saved = []
        if self._eye_rest_saved:
            self.say(random.choice(EYE_REST_WINDOW_LINES) % len(self._eye_rest_saved))
        else:
            self.say(random.choice(EYE_REST_LINES))
        if self.cfg.get("eye_rest_shrink", True):
            # 临时缩小，persist=False：你选的尺寸记在配置里，到点原样变回来
            self.set_size(SIZE_LEVELS["小"], persist=False)
        self._show_eye_overlay(int(rest_ms / 1000))
        self.save_config()

    def _overlay_pixmap(self):
        try:
            hs = sorted({k[1] for k in self.sprites if k[0] == "正面"})
            if hs:
                return self.sprites[("正面", hs[-1])]
        except Exception:
            pass
        return None

    def _show_eye_overlay(self, seconds):
        """休息期间用一块大屏霸占屏幕中央（鱼在中间），只留一个输入框当逃生门"""
        if not self.cfg.get("eye_rest_overlay", True):
            return
        try:
            if self.eye_overlay is None:
                self.eye_overlay = EyeRestOverlay(self._overlay_pixmap(), self._on_overlay_finish)
            else:
                self.eye_overlay.canvas.set_pixmap(self._overlay_pixmap())
            n = len(self._eye_rest_saved)
            note = ("我把你 %d 个窗口先收起来了，到点自动放回来 —— 现在去看看窗外、站起来走两步～"
                    % n) if n else "去看看窗外、站起来走两步～"
            screen = self.screen() or QApplication.primaryScreen()
            self.eye_overlay.start(seconds, screen.availableGeometry(), note)
            self._eye_overlay_up = True
            self.hide()                     # 小鱼先躲起来，大屏中间有只大的
        except Exception as e:
            print("护眼大屏没起来:", e)

    def _on_overlay_finish(self, reason):
        if reason == "busy":
            self.say("行吧，你去忙，回头记得让眼睛歇会儿！")
        elif reason == "closed":
            self.say("行吧，那你自己注意眼睛～")
        self._end_eye_rest()

    def _end_eye_rest(self):
        self.eye_rest_until = 0
        # 注意：大屏是先自己隐藏、再回调进来的，所以这里不能靠 isVisible 判断，
        # 得用自己记的标记，否则小鱼就放不出来了
        was_overlay = self._eye_overlay_up
        self._eye_overlay_up = False
        if self.eye_overlay is not None:
            try:
                self.eye_overlay.stop()               # 关掉大屏（不会再回调）
            except Exception:
                pass
        if self.cfg.get("eye_rest_shrink", True):
            self.set_size(self.cfg.get("size", 0.7), persist=False)
        back = 0
        if self._eye_rest_saved and self.cfg.get("eye_rest_restore_windows", True):
            try:
                back = restore_windows(self._eye_rest_saved)
            except Exception as e:
                print("放回窗口失败:", e)
        self._eye_rest_saved = []
        self.cfg["eye_rest_pending"] = []
        self.cfg["eye_rest_restore_at"] = 0
        if was_overlay:                               # 之前藏起来的小鱼放出来
            try:
                self.show()
                self.raise_()
            except Exception:
                pass
        self.save_config()
        if back:
            self.say("休息好了！%d 个窗口给你放回来了～" % back)
        else:
            self.say(random.choice(EYE_REST_DONE_LINES))

    def _resume_eye_rest_pending(self):
        """上次护眼收起来的窗口还没到点（比如中途重启了）→ 接着管，到点放回来"""
        pend = self.cfg.get("eye_rest_pending") or []
        at = int(self.cfg.get("eye_rest_restore_at") or 0)
        self._eye_rest_saved = [tuple(x) for x in pend if isinstance(x, (list, tuple))]
        if not self._eye_rest_saved:
            return
        left = at - int(time.time() * 1000)
        if left <= 0:
            self._end_eye_rest()                       # 早该放回来了，立刻放
        else:
            self.eye_rest_until = self.t * TICK + left
            print("[护眼] 还有 %d 个窗口，%d 秒后自动放回来"
                  % (len(self._eye_rest_saved), left // 1000))

    def set_eye_rest(self, on):
        self.cfg["eye_rest_enabled"] = bool(on)
        if on:
            self.next_eye_rest = self.t * TICK + self._eye_rest_interval_ms()
            self.say("好，我盯着你休息眼睛！")
        else:
            if self.eye_rest_until:
                self._end_eye_rest()                   # 手动关掉 → 立刻把窗口放回来
            self.say("行吧，那我不唠叨了……")
        self.save_config()

    # ---------- 关机道别 ----------
    def _check_shutdown(self, now_ms):
        if self._said_bye or now_ms - self._last_shutdown_check < 1000:
            return
        self._last_shutdown_check = now_ms
        try:
            if ctypes.windll.user32.GetSystemMetrics(SM_SHUTTINGDOWN):
                self._say_goodbye()
        except Exception as e:
            print("关机检测失败:", e)

    def _say_goodbye(self):
        """关机 / 注销前：先把设置落盘，再道个别（同时记一行日志作证）"""
        if self._said_bye:
            return
        self._said_bye = True
        line = random.choice(BYE_LINES)
        try:
            self.cfg["x"], self.cfg["y"] = self._body_pos().x(), self._body_pos().y()
            self.save_config()
        except Exception as e:
            print("关机前保存失败:", e)
        try:
            with open(os.path.join(APP_DIR, "bye.log"), "a", encoding="utf-8") as f:
                f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), line))
        except Exception as e:
            print("写 bye.log 失败:", e)
        try:
            self.show()
            self.raise_()
            self.say(line)
            self.update()
        except Exception:
            pass

    # ---------- 鼠标事件 ----------
    def hideEvent(self, e):
        if self.video is not None:            # 本体藏起来（护眼/显示隐藏）时视频也藏
            self.video.stop()
        super().hideEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        self._disable_native_decoration()
        if self.video_ready() and (self.video is None or not self.video.clip):
            QTimer.singleShot(400, self._video_idle)     # 一出来就播待机动画

    def _disable_native_decoration(self):
        """透明工具窗口不使用 Windows 的矩形背景、圆角及非客户区边框。"""
        if sys.platform != "win32":
            return
        try:
            setter = ctypes.windll.dwmapi.DwmSetWindowAttribute
            setter.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
            setter.restype = ctypes.c_long
            hwnd = int(self.winId())
            # NCRENDERING_POLICY=DISABLED, CORNER=DONOTROUND,
            # BORDER_COLOR=NONE, SYSTEMBACKDROP_TYPE=NONE。
            for attr, value in ((2, 1), (33, 1), (34, 0xfffffffe), (38, 1)):
                native_value = ctypes.c_uint(value)
                setter(hwnd, attr, ctypes.byref(native_value), ctypes.sizeof(native_value))
        except (AttributeError, OSError):
            pass   # 旧 Windows 不支持这些属性时仍使用 Qt 的透明轮廓。

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.last_press_pos = e.globalPosition().toPoint()
            self.dragging = False
            self.drag_start_pos = e.globalPosition().toPoint()
            self.drag_history = []
            self._drag_started_at = time.monotonic()
            self._edge_impact_latched = False
            self.flying = False          # 抓住就不飞了
            self.chat_paused = True

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton and self.drag_start_pos is not None:
            delta = e.globalPosition().toPoint() - self.drag_start_pos
            if not self.dragging and delta.manhattanLength() > 6:
                self.dragging = True
                self._drag_content_rect = None
                body_pos = self._body_pos()
                self.drag_offset = e.globalPosition().toPoint() - QPoint(body_pos.x(), body_pos.y())
                self.drag_history = [(body_pos.x(), body_pos.y(), self._drag_started_at)]
                if self.video_ready():
                    self.show_clip(self.clip_for("拖拽"), loop=True)   # 悬空反馈动画
            if self.dragging and self.drag_offset is not None:
                pos = e.globalPosition().toPoint() - self.drag_offset
                now = time.monotonic()
                previous = self.drag_history[-1] if self.drag_history else (pos.x(), pos.y(), now)
                dx, dy = pos.x() - previous[0], pos.y() - previous[1]
                elapsed = max(0.001, now - previous[2])
                speed = math.hypot(dx, dy) / elapsed
                left, top, right, bottom = self._desktop_body_limits()
                hit_edge = ((dx < 0 and pos.x() < left) or (dx > 0 and pos.x() > right) or
                            (dy < 0 and pos.y() < top) or (dy > 0 and pos.y() > bottom))
                returned_inside = (left + 20 <= pos.x() <= right - 20 and
                                   top + 20 <= pos.y() <= bottom - 20)
                if returned_inside:
                    self._edge_impact_latched = False
                if hit_edge and speed >= EDGE_IMPACT_SPEED and not self._edge_impact_latched:
                    self._trigger_edge_impact()
                clamped_pos = QPoint(max(left, min(right, pos.x())),
                                     max(top, min(bottom, pos.y())))
                self._move_body(clamped_pos)
                actual_pos = self._body_pos()
                self.drag_history.append((actual_pos.x(), actual_pos.y(), now))
                if len(self.drag_history) > 6:
                    self.drag_history.pop(0)
                if abs(delta.x()) > 10:
                    self._set_dir("left" if delta.x() < 0 else "right", 1 if delta.x() < 0 else -1)
                self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self.dragging:
                self.dragging = False
                self._drag_content_rect = None
                self.drag_offset = None
                self.drag_start_pos = None
                self.target = None
                self.rest_until = self.t * TICK + random.randint(6000, 14000)
                vx = vy = 0.0
                if len(self.drag_history) >= 2:
                    (x0, y0, t0), (x1, y1, t1) = self.drag_history[0], self.drag_history[-1]
                    dt = max(0.03, t1 - t0)
                    vx = (x1 - x0) / dt * (TICK / 1000.0)      # px/tick
                    vy = (y1 - y0) / dt * (TICK / 1000.0)
                self.drag_history = []
                self._edge_impact_latched = False
                if (vx * vx + vy * vy) ** 0.5 > 6.0:           # 甩出去 → 抛物线飞
                    self._throw(vx, vy)
                else:                                          # 温柔放下 → 原地停住
                    self._set_dir("down", 1)
                    if time.monotonic() >= self._edge_impact_until:
                        self.play_action("squash", force=True)
                        self._video_idle()
                    if random.random() < 0.5:
                        self.say(random.choice(DRAG_LINES))
                    self.cfg["x"], self.cfg["y"] = self._body_pos().x(), self._body_pos().y()
                    self.save_config()
                    self.chat_paused = False
            else:
                self._click_timer.start(280)  # 等双击判定；单击则回嘴
            self.last_press_pos = None
            self.drag_start_pos = None

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._click_timer.stop()
            self.food_panel.popup_at(self._body_pos().x() + self.win_w / 2, self._body_pos().y() + BUBBLE_H)

    def _on_single_click(self):
        """单击：先 Q 弹挤压、再随机回应一个动作，同时回嘴。"""
        key = random.choice(CLICK_ACTIONS)
        self.play_action("squash", force=True)
        self._next_action = key
        self.jump_t = 0.6
        if random.random() < 0.6:
            self.say(random.choice(REACT_LINES))

    def on_food(self, food):
        self.food_panel.hide()
        self.eat_t = 1.0
        self.jump_t = 0.6
        lines = FOOD_LINES.get(food, ["好吃！"])
        self.say(random.choice(lines))

    """def _get_city_by_ip(self):
        try:
            r = requests.get("http://ip-api.com/json/?fields=city&lang=zh-CN", timeout=5)
            if r.status_code == 200:
                city = r.json().get("city", "")
                if city:
                    return city
        except:
            pass
        return "汕头" """

    def _get_weather(self):
        try:
            city = self.cfg.get("city", "")
            lat, lon = self.cfg.get("lat"), self.cfg.get("lon")
            if (lat is None or lon is None) and is_placeholder_city(city):
                self.say("先告诉我你在哪个城市呀～右键「设置城市」")
                return
            if lat is not None and lon is not None:
                city = "%s,%s" % (lat, lon)          # 有定位坐标就用坐标，比城市名准
            print("当前城市/坐标:", city)

            url = f"https://wttr.in/{city}?format=j1"

            r = requests.get(
                url,
                timeout=10,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )

            print("状态:", r.status_code)
            print(r.text[:500])

            data = r.json()

            weather = data["current_condition"][0]

            temp = weather["temp_C"]

            weather_map = {
                "Sunny": "晴",
                "Clear": "晴",
                "Partly cloudy": "多云",
                "Cloudy": "阴",
                "Light rain": "小雨",
                "Moderate rain": "中雨",
                "Heavy rain": "大雨"
            }

            raw_weather = weather["weatherDesc"][0]["value"]

            desc = weather_map.get(raw_weather, raw_weather)

            self.say(f"{city}今天{temp}°，天气{desc}")

        except Exception as e:
            print("天气错误:", repr(e))
            self.say("天气获取失败")
    

    def set_theme(self, key):
        """换主题：粉色 / 跟随系统（中性色）。颜色立刻换，重开分身窗口后更彻底"""
        key = key if key in THEMES else "pink"
        self.cfg["theme"] = key
        _RUNTIME["theme"] = key
        self.save_config()
        try:
            QApplication.instance().setPalette(_ui_palette())
            QApplication.instance().setStyleSheet(_theme_native_style())
        except Exception as e:
            print("换主题失败:", e)
        self.say("换成%s主题啦～重开一下分身窗口更彻底" % THEMES[key]["name"])

    def _build_menu(self):
        m = QMenu(self)
        m.setStyleSheet(_theme_native_style())     # 原生菜单不吃调色板，得单独上色
        mode_menu = m.addMenu("模式")
        for label, key in [("自由散步", "wander"), ("跟随鼠标", "follow"), ("原地待着", "still")]:
            a = mode_menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.mode == key)
            a.triggered.connect(lambda _, k=key: self.set_mode(k))
        size_menu = m.addMenu("大小")
        for label, mult in SIZE_LEVELS.items():
            a = size_menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(abs(self.cur_h - 340 * mult) < 2)
            a.triggered.connect(lambda _, v=mult: self.set_size(v))
        theme_menu = m.addMenu("主题")
        for key in ("pink", "system"):
            a = theme_menu.addAction(THEMES[key]["name"])
            a.setCheckable(True)
            a.setChecked(str(self.cfg.get("theme", "pink")).lower() == key)
            a.triggered.connect(lambda _, k=key: self.set_theme(k))
        act_menu = m.addMenu("动作")
        if self.video_ready():                     # 视频模式：直接点播真·动画
            act_menu.addAction("随机来一个", lambda: self.play_random_clip(True))
            for pool in ("点击回应", "卖萌", "玩耍", "吃什么", "时节", "工作状态", "文字", "碎碎念"):
                items = [c for c in ANIM_POOLS.get(pool, []) if c in self.anim_names()]
                if not items:
                    continue
                sub = act_menu.addMenu(pool)
                for c in items:
                    sub.addAction(c, lambda _=False, n=c: self.show_clip(n, loop=False))
            act_menu.addSeparator()
            act_menu.addAction("回到待机", lambda: self._video_idle())
        else:
            act_menu.addAction("随机来一个",
                               lambda: self.play_action(self._pick_action(), force=True))
            for cat in ("idle", "play", "emote", "fun"):
                items = [x for x in ACTIONS if x["cat"] == cat and x.get("menu", True)]
                if not items:
                    continue
                sub = act_menu.addMenu(CATEGORY_NAMES.get(cat, cat))
                for x in items:
                    sub.addAction(x["name"],
                                  lambda _=False, k=x["key"]: self.play_action(k, force=True))
        va = m.addAction("视频动画（透明 webm）")
        va.setCheckable(True)
        va.setChecked(bool(self.cfg.get("video_anim", True)))
        va.triggered.connect(lambda on: self.set_video_anim(on))
        m.addAction("🌍 用系统定位（授权）", lambda: self.locate_me(auto=True))
        m.addAction("设置城市（手动）", self._set_city_dialog)
        al = m.addAction("启动时自动更新城市（IP）")
        al.setCheckable(True)
        al.setChecked(bool(self.cfg.get("auto_locate_city", True)))
        al.triggered.connect(lambda on: self.set_auto_locate_city(on))
        # Key 相关（开源版：填完即生效，且随时能查到自己的配置存在哪）
        _has_key = not is_placeholder_key(self.cfg.get("ds_api_key"))
        m.addAction(("设置 Key（当前 %s）" % key_hint(self.cfg.get("ds_api_key")))
                    if _has_key else "设置 Key（还没填 ← 点这里）",
                    self._set_key_dialog)
        m.addAction("测试 Key 连通性", self._verify_key_async)
        m.addAction("我的配置存在哪？（看路径）", self._show_config_path)
        m.addAction("打开配置文件所在文件夹", self._open_config_dir)
        m.addSeparator()
        m.addAction("查看天气", self._get_weather)
        m.addSeparator()
        m.addAction("显示/隐藏", self.toggle_visible)
        m.addAction("回到屏幕内", self.snap_into_screen)
        pa = m.addAction("鼠标穿透（点不到它）")
        pa.setCheckable(True)
        pa.setChecked(self.cfg["passthrough"])
        pa.triggered.connect(lambda on: self.set_passthrough(on))
        ta = m.addAction("窗口置顶")
        ta.setCheckable(True)
        ta.setChecked(self.cfg["topmost"])
        ta.triggered.connect(lambda on: self.set_topmost(on))
        aa = m.addAction("开机自启")
        aa.setCheckable(True)
        aa.setChecked(self.cfg["autostart"])
        aa.triggered.connect(lambda on: self.set_autostart(on))
        m.addSeparator()
        ea = m.addAction("护眼提醒（每 2 小时）")
        ea.setCheckable(True)
        ea.setChecked(self.cfg.get("eye_rest_enabled", True))
        ea.triggered.connect(lambda on: self.set_eye_rest(on))
        m.addSeparator()
        m.addAction("分身（打开窗口）", lambda: self.open_avatar())
        m.addAction("分身：总结剪贴板", self.task_from_clipboard)
        m.addSeparator()
        m.addAction("退出", self.quit_app)
        return m

    # ---------- Key：填完即生效，不用重启（开源版重点） ----------
    def apply_key(self, key, save=True, verify=True):
        """把 Key 装进内存 + **加密**存盘，全程不重启

        为什么这样就「免重启」：
          1) 写进 self.cfg —— 分身对新任务是从 self.cfg 复制配置的，下一条消息就用新 Key
          2) 正在跑的那个分身吃的是自己的副本，所以这里把新 Key 直接塞给它
          3) apply_runtime_config() 让联网设置一起跟上，并清掉代理/线路缓存
          4) Key 用 DPAPI 加密落进 key.bin；config.json 里只留空字符串

        返回 (是否成功, 给用户看的一句话)
        """
        key = normalize_key(key)
        if is_placeholder_key(key):
            return False, "还没填内容（或者填的是模板占位符）"
        self.cfg["ds_api_key"] = key
        try:
            apply_runtime_config(self.cfg)
        except Exception:
            pass
        _PROXY_CACHE["time"] = 0.0
        _LINES_CACHE["time"] = 0.0
        # 正在跑的分身：它的 cfg 是自己的一份拷贝，必须主动递过去
        try:
            worker = getattr(self, "task_worker", None)
            if worker is not None and isinstance(getattr(worker, "cfg", None), dict):
                worker.cfg["ds_api_key"] = key
        except Exception:
            pass

        how = "cleared"
        if save:
            how = save_key_to_store(key)               # ★ 加密写进 key.bin
            self._key_plaintext = (how == "plain")    # 加密不可用才退回明文
        ok = self.save_config() if save else True
        if not ok:
            return False, "没能存进 %s，检查文件夹是否只读" % os.path.basename(CONFIG_DIR)
        if how == "plain":
            return True, "已存盘、立刻生效（这台机器上 DPAPI 不可用，只能明文存 Key）"
        return True, "已加密存进 key.bin、立刻生效（不用重启）"

    def _set_key_dialog(self):
        """右键「设置 Key」：填完 → 存盘 → 后台验一次 → 全程不重启"""
        cur = self.cfg.get("ds_api_key", "")
        key, ok = QInputDialog.getText(
            self,
            "设置 DeepSeek Key（填完即生效）",
            "粘贴 API Key（在 platform.deepseek.com 获取）\n"
            "确定后立刻生效，并用系统加密存进 key.bin，不用重启桌宠：",
            QLineEdit.EchoMode.Normal,
            "" if is_placeholder_key(cur) else cur
        )
        if not ok:
            return
        key = normalize_key(key)
        if is_placeholder_key(key):
            self.say("Key 不能为空（也别填占位符）")
            return
        if not key.startswith("sk-"):
            self.say("这串不太像 Key（DeepSeek 的一般以 sk- 开头）")
        good, msg = self.apply_key(key)
        if not good:
            self.say("Key 没存上：%s" % msg)
            return
        self.say("Key 设置成功，%s" % msg)
        if verify:
            self._verify_key_async()

    def _verify_key_async(self):
        """后台真连一次 API 验证 Key，结果用气泡报出来

        为什么要验：Key 粘错 / 粘多了空格 / 余额没了，报错长得都一样。
        这里当场问一次，用户马上就知道是「Key 错了」还是「网络不通」。
        验证失败**不会**清掉已经存好的 Key —— 网络问题不该罚用户重填。
        """
        key = normalize_key(self.cfg.get("ds_api_key"))
        if is_placeholder_key(key):
            return
        base = str(self.cfg.get("ds_base_url") or DS_BASE_URL).rstrip("/")

        def work():
            try:
                r = requests.get(base + "/models",
                                 headers={"Authorization": "Bearer " + key},
                                 timeout=15)
                if r.status_code == 200:
                    self._queue_say("Key 验过了 ✓ 现在就能使唤我")
                elif r.status_code in (401, 403):
                    self._queue_say("Key 被拒了（%d），检查有没有粘错" % r.status_code)
                else:
                    self._queue_say("Key 测试返回 %d，可能是地址写错了" % r.status_code)
            except Exception as e:
                self._queue_say("Key 没验成（%s），但不影响使用" % type(e).__name__)

        threading.Thread(target=work, daemon=True).start()

    def _show_config_path(self):
        """「我的个人配置在哪？」—— 把路径和状态一次说清楚（不显示 Key 本身）"""
        has = not is_placeholder_key(self.cfg.get("ds_api_key"))
        if getattr(self, "_key_plaintext", False):
            store_desc = "明文存在 config.json（这台机器 DPAPI 不可用）"
        elif key_store_exists():
            store_desc = "已用 Windows DPAPI 加密，存在 key.bin"
        else:
            store_desc = "还没有 Key"
        where = "便携模式（跟程序文件夹走）" if is_portable() else "系统用户目录 %APPDATA%（按 Windows 账户隔离）"
        box = QMessageBox(self)
        box.setWindowTitle("我的个人配置在哪")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText("你的个人设置存在你自己的 Windows 账户下：")
        box.setInformativeText(
            "配置位置：\n%s\n\n"
            "Key 仓库：\n%s\n\n"
            "当前模式：%s\n"
            "Key 状态：%s（%s）\n"
            "API 地址：%s\n"
            "模型：%s\n\n"
            "• 这两样都在你自己的电脑、你自己的 Windows 账户里，不会上传到任何服务器。\n"
            "• key.bin 换了电脑或换了 Windows 账户就解不开 —— 别人拷走也没用。\n"
            "• 开源仓库的 .gitignore 已排除它们，分享源码不会带走你的 Key。\n"
            "• 别的用户在自己的电脑上填自己的 Key，各存各的、互不影响。\n"
            "• 改 config.json（城市 / 模型 / 主题…）会**立刻生效**，不用重启。"
            % (CONFIG_PATH, KEY_PATH, where,
               key_hint(self.cfg.get("ds_api_key")) if has else "未设置",
               store_desc,
               self.cfg.get("ds_base_url", DS_BASE_URL),
               self.cfg.get("ds_model", DS_MODEL)))
        btn_open = box.addButton("打开所在文件夹", QMessageBox.ButtonRole.ActionRole)
        box.addButton("知道了", QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        if box.clickedButton() is btn_open:
            self._open_config_dir()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Context:
            self.tray.setContextMenu(self._build_menu())
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visible()

    def contextMenuEvent(self, e):
        self._build_menu().exec(e.globalPos())

    # ---------- 功能 ----------
    def set_mode(self, mode):
        self.mode = mode
        self.target = None
        self.cfg["mode"] = mode
        self.save_config()

    def set_size(self, mult, persist=True):
        """persist=False：护眼提醒的临时缩小，只改窗口大小，不动你选的尺寸"""
        self.cur_h = int(340 * mult)
        self.cross_t = 0.0
        self.prev_key = None
        self.win_mx = int(self.cur_h * 0.062) + 6
        self.win_w = max(p.width() for k, p in self.sprites.items() if k[1] == self.cur_h) + self.win_mx * 2
        self.win_h = self.cur_h + BUBBLE_H + MARGIN * 2 + 10
        self._sync_video()
        self.snap_into_screen()
        if persist:
            self.cfg["size"] = mult
            self.save_config()

    def snap_into_screen(self):
        geo = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        x = max(geo.left(), min(geo.right() - self.win_w, self._body_pos().x()))
        y = max(geo.top(), min(geo.bottom() - self.win_h, self._body_pos().y()))
        self._move_body(x, y)

    def _apply_passthrough(self, on):
        hwnd = int(self.winId())
        GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT = -20, 0x80000, 0x20
        style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        style = style | WS_EX_LAYERED
        if on:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)

    def set_passthrough(self, on):
        self.cfg["passthrough"] = bool(on)
        self._apply_passthrough(bool(on))
        self.save_config()
        if on:
            self.say("我隐身了！右键托盘图标解除～")

    def set_topmost(self, on):
        self.cfg["topmost"] = bool(on)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(on))
        self.show()
        self.save_config()

    def _startup_dirs(self):
        """系统里可能放启动快捷方式的目录（用户 + 公共，含被 OneDrive 重定向的情况）"""
        dirs = []
        try:
            import winreg as _w
            with _w.OpenKey(_w.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as k:
                dirs.append(_w.QueryValueEx(k, "Startup")[0])
        except Exception:
            pass
        dirs.append(os.path.join(os.environ.get("APPDATA", ""),
                                 "Microsoft", "Windows", "Start Menu", "Programs", "Startup"))
        dirs.append(os.path.join(os.environ.get("ProgramData", ""),
                                 "Microsoft", "Windows", "Start Menu", "Programs", "Startup"))
        return [d for d in dirs if d and os.path.isdir(d)]

    @staticmethod
    def _lnk_text(path):
        """粗略读出快捷方式里的文字（只为认路，不求精解）"""
        try:
            raw = open(path, "rb").read()
            return raw.decode("utf-16-le", "ignore") + raw.decode("latin-1", "ignore")
        except Exception:
            return ""

    def _existing_autostart(self):
        """系统里是否已经有启动桌宠的入口。返回 (来源描述, 是不是桌宠自己建的)"""
        marks = ("桌宠", "dafeiyu", "启动桌宠", "dafeiyu-pet")
        for d in self._startup_dirs():
            try:
                for f in os.listdir(d):
                    if not f.lower().endswith(".lnk"):
                        continue
                    txt = f + self._lnk_text(os.path.join(d, f))
                    if any(m.lower() in txt.lower() for m in marks):
                        return ("启动文件夹「%s」" % f, f == "大肥鱼桌宠.lnk")
            except Exception:
                continue
        try:
            import winreg as _w
            with _w.OpenKey(_w.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                i = 0
                while True:
                    try:
                        name, val, _t = _w.EnumValue(k, i)
                    except OSError:
                        break
                    i += 1
                    txt = "%s %s" % (name, val)
                    if any(m.lower() in txt.lower() for m in marks):
                        return ("注册表启动项「%s」" % name, "大肥鱼桌宠" in name)
        except Exception:
            pass
        return (None, False)

    def set_autostart(self, on):
        self.cfg["autostart"] = bool(on)
        src, mine = self._existing_autostart()
        if on and src and not mine:
            self.save_config()          # 系统里已经有入口（比如你自己放的快捷方式）→ 不重复建
            self.say("已经有自启入口了（%s），我就不重复建了" % src)
            return
        lnk = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                           "Start Menu", "Programs", "Startup", "大肥鱼桌宠.lnk")
        try:
            if on:
                ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{}');"
                      "$s.TargetPath='{}';$s.Arguments='\"{}\"';$s.WorkingDirectory='{}';$s.Save()"
                      .format(lnk, PYTHONW,
                              "" if getattr(sys, "frozen", False) else os.path.join(APP_DIR, "桌宠.py"),
                              APP_DIR))
                subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=True)
                self.say("已开机自启，明天见～")
            else:
                if os.path.exists(lnk):
                    os.remove(lnk)
                self.say("已取消开机自启")
            self.save_config()
        except Exception as ex:
            QMessageBox.warning(self, "开机自启", f"设置失败：{ex}")

    def toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()

    def quit_app(self):
        self.cfg["x"], self.cfg["y"] = self._body_pos().x(), self._body_pos().y()
        self.save_config()
        self.tray.hide()
        QApplication.quit()


_PET_MUTEX = None


class _MSG(ctypes.Structure):
    _fields_ = [("hWnd", ctypes.c_void_p), ("message", ctypes.c_uint),
                ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_ssize_t),
                ("time", ctypes.c_uint), ("pt_x", ctypes.c_long), ("pt_y", ctypes.c_long)]


class ShutdownWatcher(QAbstractNativeEventFilter):
    """Windows 说「要关机 / 注销了」时通知桌宠道别

    主路径：WM_QUERYENDSESSION / WM_ENDSESSION；
    tick 里还会轮询 SM_SHUTTINGDOWN 作为兜底。出任何问题都只是道别不灵，不影响桌宠本身。
    """
    WM_QUERYENDSESSION = 0x0011
    WM_ENDSESSION = 0x0016

    def __init__(self, on_shutdown):
        super().__init__()
        self._on_shutdown = on_shutdown

    def nativeEventFilter(self, eventType, message):
        try:
            if bytes(eventType) == b"windows_generic_MSG":
                msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
                if msg.message in (self.WM_QUERYENDSESSION, self.WM_ENDSESSION):
                    self._on_shutdown()
        except Exception as e:
            print("关机消息处理失败:", e)
        return False, 0


def single_instance_guard():
    """命名互斥体：同一时间只允许一只大肥鱼在跑

    两只同时跑会互相覆盖 config.json（Key、位置、模式会被来回冲掉，
    这正是「重启后 Key 又没了」的元凶）。
    这里任何异常都放行，绝不因为这个小功能导致桌宠起不来。

    防御性加固（不是修 bug）：
    上游写法 `ctypes.windll.kernel32` + `GetLastError() == 183` 在实测中是**对的**
    （全新名字返回 0、重复名字返回 183，均已验证）。但 `ctypes.windll` 默认不跟踪
    last-error，而 `GetLastError()` 读的是本线程**上一次**留下的错误码 —— 理论上
    只要中间夹了别的 Win32 调用就可能被带偏。所以这里按 MSDN 推荐的稳妥写法收一下：
    用 use_last_error=True 让 ctypes 自己接住错误码，并在调用前 SetLastError(0) 清零。
    行为与上游一致，只是不再依赖「线程错误码恰好没被覆盖」这个前提。
    """
    global _PET_MUTEX
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel32.SetLastError(0)                 # 先清掉线程里残留的错误码
        handle = kernel32.CreateMutexW(None, False, "Local\\dafeiyu_pet_single_instance")
        err = ctypes.get_last_error()            # 只认这次调用自己的错误码
        if not handle:
            return True                          # 建不出来就放行，绝不让守卫挡住桌宠
        if err == 183:                           # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(ctypes.c_void_p(handle))
            return False
        _PET_MUTEX = handle  # 一直持有，进程结束系统自动释放
        return True
    except Exception as e:
        print("单实例检查跳过:", e)
        return True


def _prepare_webengine_process_path():
    """让 QtWebEngine 的独立 Chromium 子进程也能找到 Qt/Conda DLL。"""
    if os.name != "nt" or not WEBENGINE_OK:
        return
    try:
        candidates = [
            QLibraryInfo.path(QLibraryInfo.LibraryPath.BinariesPath),
            os.path.join(getattr(sys, "base_prefix", sys.prefix), "Library", "bin"),
        ]
        current = os.environ.get("PATH", "").split(os.pathsep)
        normalize = lambda p: os.path.normcase(os.path.normpath(p.strip('"'))) if p else ""
        known = {normalize(p) for p in current}
        add = []
        for path in candidates:
            if path and os.path.isdir(path) and normalize(path) not in known:
                add.append(path)
                known.add(normalize(path))
        if add:
            os.environ["PATH"] = os.pathsep.join(add + current)
            print("[视频] 已加入 Chromium 子进程 DLL 路径：", "; ".join(add))
    except Exception as e:
        print("[视频] 设置 Chromium 子进程 DLL 路径失败：", e)


def main():
    global _BOOT_NOTE
    # ★ 最先做：定配置位置（%APPDATA% / 便携）→ 搬迁老配置 → 把明文 Key 收进加密仓库。
    #   必须在读 _boot_cfg 之前，因为它决定了 CONFIG_PATH 指向哪。
    try:
        _BOOT_NOTE = bootstrap_config()
    except Exception as e:
        print("配置初始化失败（继续用默认位置）:", e)
        _BOOT_NOTE = ""
    _prepare_webengine_process_path()
    try:      # QtWebEngine（内嵌 Chromium）需要这个属性，必须在 QApplication 之前设
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    except Exception:
        pass
    try:      # 个别机器上 Chromium 自带沙箱起不来，配置里可开这个开关兜底
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _boot_cfg = json.load(f) or {}
        if _boot_cfg.get("webengine_no_sandbox"):
            os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    except Exception:
        _boot_cfg = {}
    try:      # 主题要在建窗口之前定下来，右键菜单这类原生部件才会跟着走
        apply_runtime_config(_boot_cfg)
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("dafeiyu")     # 让 QtWebEngine 的 profile 目录落在可写位置
    app.setQuitOnLastWindowClosed(False)
    try:
        app.setPalette(_ui_palette())
        app.setStyleSheet(_theme_native_style())   # 菜单/提示/消息框也跟主题
    except Exception as e:
        print("应用主题失败:", e)
    if not single_instance_guard():
        QMessageBox.information(
            None, "大肥鱼桌宠",
            "已经有一只大肥鱼在跑了～\n她可能藏在托盘里：右键托盘图标可以显示/隐藏。")
        return
    w = PetWindow()
    if _BOOT_NOTE:                              # 搬过家 / 收编过明文 Key 就说一声
        QTimer.singleShot(3500, lambda: w.say(_BOOT_NOTE))
    app.aboutToQuit.connect(w.save_config)      # 兜底：不管怎么退，设置都写回去
    try:
        watcher = ShutdownWatcher(w._say_goodbye)
        app.installNativeEventFilter(watcher)
        w._shutdown_watcher = watcher           # 保住引用，别被回收
    except Exception as e:
        print("装不上关机监听，靠轮询兜底:", e)
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        try:
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "大肥鱼桌宠出错", str(ex))
        except Exception:
            pass
        raise
