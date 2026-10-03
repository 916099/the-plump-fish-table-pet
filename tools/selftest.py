# -*- coding: utf-8 -*-
"""开源版自检：验证「Key 免重启」相关的纯函数和关键行为。

用法：python tools/selftest.py
退出码：0 = 全部通过

注意：本文件里用的都是**假 Key**（sk-abcdefg...），不会碰到任何人的真 Key。
"""
import importlib.util
import os
import shutil
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TARGET = os.path.join(REPO, "桌宠.py")

FAKE_KEY = "sk-abcdefghijklmnopqrstuvwxyz0123456789"     # 假的，长度 39

spec = importlib.util.spec_from_file_location("dafeiyu_pet", TARGET)
mod = importlib.util.module_from_spec(spec)
sys.modules["dafeiyu_pet"] = mod
spec.loader.exec_module(mod)

fails = []
passed = 0


def check(name, got, want):
    global passed
    if got != want:
        fails.append("%s: got %r want %r" % (name, got, want))
        print("  FAIL %s" % name)
    else:
        passed += 1
        print("  ok   %s" % name)


print("== is_placeholder_key（认出「还没填」）==")
check("空字符串 = 没填", mod.is_placeholder_key(""), True)
check("None = 没填", mod.is_placeholder_key(None), True)
check("模板占位符 = 没填", mod.is_placeholder_key("我的API key 填充sk……"), True)
check("带空格的占位符 = 没填", mod.is_placeholder_key("  我的API key 填充sk……  "), True)
check("sk-xxxxxxxx = 没填", mod.is_placeholder_key("sk-xxxxxxxxxxxxxxxx"), True)
check("真 Key ≠ 没填", mod.is_placeholder_key(FAKE_KEY), False)

print("== normalize_key（洗干净粘贴进来的 Key）==")
check("去首尾空格", mod.normalize_key("  sk-abc123  "), "sk-abc123")
check("去双引号", mod.normalize_key('"sk-abc123"'), "sk-abc123")
check("去单引号", mod.normalize_key("'sk-abc123'"), "sk-abc123")
check("去 Bearer 前缀", mod.normalize_key("Bearer sk-abc123"), "sk-abc123")
check("去尾部换行", mod.normalize_key("sk-abc123\n"), "sk-abc123")

print("== key_hint（绝不回显完整 Key）==")
hint = mod.key_hint(FAKE_KEY)
check("不回显 Key 中段", "abcdefghijklmnop" in hint, False)
check("以位数结尾", hint.endswith("（%d 位）" % len(FAKE_KEY)), True)
check("空值时显示未设置", mod.key_hint(""), "未设置")
check("占位符时显示未设置", mod.key_hint("我的API key 填充sk……"), "未设置")

print("== is_placeholder_city（认出占位符城市）==")
check("模板城市 = 没填", mod.is_placeholder_city("你的城市，例如：北京"), True)
check("空城市 = 没填", mod.is_placeholder_city(""), True)
check("真城市 ≠ 没填", mod.is_placeholder_city("成都"), False)

print("== TaskWorker 拿的是 cfg 拷贝（所以必须主动热更新）==")
live = {"ds_api_key": "OLD"}
worker = mod.TaskWorker(live, "test")
live["ds_api_key"] = "NEW"
check("worker 不跟着外部 dict 变（证明是拷贝）", worker.cfg["ds_api_key"], "OLD")
worker.cfg["ds_api_key"] = "PUSHED"
check("主动塞进去才生效（apply_key 的做法）", worker.cfg["ds_api_key"], "PUSHED")

print("== Key 加密仓库（Windows DPAPI）往返 ==")
# 全部在临时目录里做，绝不碰用户真正的 %APPDATA%
# 用固定名字 + os.makedirs 自建自删：比 tempfile.mkdtemp 更稳
# （某些受限沙箱里 mkdtemp 建出的目录 ACL 异常，连自己都写不进去）
_tmp = os.path.join(REPO, "_selftest_tmp")
try:
    shutil.rmtree(_tmp, ignore_errors=True)
    os.makedirs(_tmp, exist_ok=True)
except Exception:
    import tempfile as _tf
    _tmp = os.path.join(_tf.gettempdir(), "dafeiyu_selftest")
    os.makedirs(_tmp, exist_ok=True)
_old_key, _old_cfg = mod.KEY_PATH, mod.CONFIG_PATH
try:
    mod.KEY_PATH = os.path.join(_tmp, "key.bin")
    mod.CONFIG_PATH = os.path.join(_tmp, "config.json")

    check("一开始没有 key.bin", mod.key_store_exists(), False)
    check("空仓库读出来是空串", mod.load_key_from_store(), "")

    how = mod.save_key_to_store(FAKE_KEY)
    check("保存方式是 dpapi 加密", how, "dpapi")
    check("key.bin 确实生成了", mod.key_store_exists(), True)
    check("能原样解回来", mod.load_key_from_store(), FAKE_KEY)

    with open(mod.KEY_PATH, "rb") as _f:
        _raw = _f.read()
    check("文件里看不到明文 Key", FAKE_KEY.encode("utf-8") in _raw, False)
    check("带本程序的 MAGIC 头", _raw.startswith(mod.KEY_BLOB_MAGIC), True)

    _bad = bytearray(_raw)
    _bad[-1] ^= 0xFF
    with open(mod.KEY_PATH, "wb") as _f:
        _f.write(bytes(_bad))
    check("被篡改后拒绝解密（返回空串，不崩）", mod.load_key_from_store(), "")

    check("清空返回 cleared", mod.save_key_to_store(""), "cleared")
    check("清空后 key.bin 没了", mod.key_store_exists(), False)

    check("占位符不会被当成 Key 存起来", mod.save_key_to_store("我的API key 填充sk……"), "cleared")
    check("占位符存完还是没有文件", mod.key_store_exists(), False)
finally:
    mod.KEY_PATH, mod.CONFIG_PATH = _old_key, _old_cfg
    shutil.rmtree(_tmp, ignore_errors=True)

print()
if fails:
    print("失败 %d 项（通过 %d 项）：" % (len(fails), passed))
    for f in fails:
        print("  ✗", f)
    sys.exit(1)
print("全部通过 ✓（%d 项）" % passed)
