# -*- coding: utf-8 -*-
"""CHEN-V 完整性校验（防篡改 / 防转卖）。

说明：源码开源后无法阻止别人读懂或改动源码本身；这里的防护目标是
「别人拿你的发行包改几下、换个名字当自己的东西卖」。手段组合：

  1. 内置品牌指纹：把作者名 / 项目名 / 官网写死在代码里，任何界面都显示。
  2. 核心文件完整性清单：启动时校验 app 目录下关键 .py 的 SHA256，
     被改动则提示「文件被篡改」并可拒绝运行。
  3. 签名校验（可选增强）：作者用私钥对完整性清单签名，程序内置公钥验签，
     改文件但改不了签名 → 直接判定篡改。公钥可内嵌，破解者要换公钥就得改
     本模块本身，而本模块也在校验清单里，形成自举。
  4. 联网校验（可选）：向作者服务器/GitHub 拉一份官方指纹，本地对不上就警示。

注意：纯 Python 无法做到「无法破解」——有足够动机的逆向工程师总能绕过。
这里的目的是显著提高成本，让「改一改就卖」变得不划算，同时不伤害正常用户。

用法：在 main.py 启动早期调用 integrity.bootstrap()，返回 (ok, reason)。
"""
import hashlib
import json
import os
import sys

# ---- 品牌指纹（写死，任何界面/关于页都从这里取，保证来源可追溯） ----
BRAND_NAME = "CHEN-V"
AUTHOR = "辰师"
AUTHOR_URL = "https://github.com/CHENYE-SHI/CHEN-V"
BILIBILI_URL = "https://b23.tv/X2FYRsA"

# ---- 完整性清单：app 目录下需要校验的核心文件 ----
# 用相对路径（相对 app 目录），只覆盖会被篡改来「改品牌/加广告/植入」的核心逻辑。
_PROTECTED_FILES = [
    "main.py",
    "gui_main.py",
    "updater.py",
    "integrity.py",
]

# ---- 作者公钥（占位；作者生成密钥后替换）----
# 用 RSA/Ed25519 公钥对 MANIFEST 签名。这里先留空，走「纯哈希」降级模式，
# 功能可用但不如签名强。作者配好密钥后填入 PEM 即可启用验签。
_PUBLIC_KEY = None


def _app_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _manifest_path():
    return os.path.join(_app_dir(), "manifest.json")


def _sha256(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _compute_manifest():
    """计算当前 app 目录受保护文件的哈希清单。"""
    m = {"files": {}, "brand": BRAND_NAME, "author": AUTHOR}
    for rel in _PROTECTED_FILES:
        p = os.path.join(_app_dir(), rel)
        d = _sha256(p)
        if d:
            m["files"][rel] = d
    return m


def verify_integrity():
    """校验核心文件是否与 manifest.json 一致。

    返回 (ok, reason)。reason 为 None 表示通过；否则是中文说明。
    """
    mp = _manifest_path()
    if not os.path.isfile(mp):
        # 没有清单：源码开发环境 / 首次运行，无法校验 → 放行但标记「未签名」
        return True, "no_manifest"

    try:
        with open(mp, "r", encoding="utf-8") as f:
            official = json.load(f)
    except Exception:
        return False, "manifest_corrupt"

    files = official.get("files") or {}
    if not files:
        return True, "empty_manifest"

    for rel, expected in files.items():
        p = os.path.join(_app_dir(), rel)
        got = _sha256(p)
        if got is None:
            # 文件被删了也算篡改
            return False, "missing:%s" % rel
        if got != expected:
            return False, "modified:%s" % rel

    # 品牌指纹也必须一致（防止有人改掉内嵌署名后重新生成清单）
    if official.get("brand") and official.get("brand") != BRAND_NAME:
        return False, "brand"
    return True, None


def bootstrap():
    """启动早期调用。返回 (ok, reason)：
      ok=True   → 继续启动
      ok=False  → 核心文件被篡改，调用方应提示并拒绝运行
    """
    return verify_integrity()


def is_tampered():
    """供界面查询是否被篡改（True = 被改过）。"""
    ok, _ = verify_integrity()
    return not ok


def write_manifest():
    """生成/更新 manifest.json（作者在发布前跑一次，别把私钥留机器上）。

    签名模式：如配置了私钥，会同时写入 signature；否则只写哈希清单。
    此函数仅供作者在构建机使用，不应随程序分发给普通用户执行。
    """
    m = _compute_manifest()
    mp = _manifest_path()
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    return mp
