# -*- coding: utf-8 -*-
"""CHEN-V 自研安装器打包脚本（Python 版，避免 cmd 编码问题）。

把「引导 exe + installer_py + payload」组装成可分发的目录：
    dist/CHEN-V_Setup_v1.01/
      ├── CHEN-V_Setup.exe
      ├── CHEN-V_Setup.exe.config
      ├── installer_py/installer.py
      ├── app/ runtime/ models/ vrt/ ffmpeg/ assets/ tools/
      └── CHEN-V.exe 命令行.bat README.md LICENSE announce.json

用法：
    runtime/py311/python.exe installer_py/build_installer.py
    （或任意 Python 3）
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VER = "1.01"
OUT = os.path.join(ROOT, "dist", "CHEN-V_Setup_v%s" % VER)

ROOT_FILES = ["CHEN-V.exe", "命令行.bat", "README.md", "LICENSE", "announce.json"]
DIRS = ["app", "runtime", "models", "vrt", "ffmpeg", "assets", "tools"]
LAUNCHER_FILES = ["CHEN-V_Setup.exe", "CHEN-V_Setup.exe.config"]


def _log(msg):
    print(msg, flush=True)


def _copytree(src, dst):
    """逐文件复制，打印进度（每 2000 文件报一次）。"""
    n = 0
    for root, _dirs, files in os.walk(src):
        for name in files:
            s = os.path.join(root, name)
            rel = os.path.relpath(s, src)
            d = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)
            n += 1
            if n % 2000 == 0:
                _log("    已复制 %d 个文件…" % n)
    return n


def main():
    if os.path.isdir(OUT):
        _log("[1/4] 清理旧产物…")
        shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(os.path.join(OUT, "installer_py"), exist_ok=True)

    _log("[2/4] 复制引导器与安装器…")
    for f in LAUNCHER_FILES:
        src = os.path.join(ROOT, f)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(OUT, f))
            _log("      %s" % f)
        else:
            _log("  [警告] 缺少 %s" % f)
    shutil.copy2(os.path.join(HERE, "installer.py"),
                 os.path.join(OUT, "installer_py", "installer.py"))
    _log("      installer_py/installer.py")

    _log("[3/4] 复制根文件…")
    for f in ROOT_FILES:
        src = os.path.join(ROOT, f)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(OUT, f))
            _log("      %s" % f)
        else:
            _log("  [警告] 缺少 %s" % f)

    _log("[4/4] 复制 payload（约 2.4GB，请耐心等待）…")
    for d in DIRS:
        src = os.path.join(ROOT, d)
        if os.path.isdir(src):
            _log("  复制 %s …" % d)
            n = _copytree(src, os.path.join(OUT, d))
            _log("      %s 完成（%d 文件）" % (d, n))
        else:
            _log("  [警告] 缺少目录 %s" % d)

    # 校验
    _log("")
    _log("=" * 46)
    _log("打包完成！")
    _log("分发目录：%s" % OUT)
    key = os.path.join(OUT, "CHEN-V_Setup.exe")
    _log("引导器存在：%s" % os.path.isfile(key))
    _log("双击 %s 即可开始安装" % os.path.join(OUT, "CHEN-V_Setup.exe"))
    _log("=" * 46)


if __name__ == "__main__":
    main()
