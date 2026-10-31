# -*- coding: utf-8 -*-
"""离屏 GUI 测试：验证安装向导的进度条会真的推进、完成后切到完成页。

这正好覆盖之前那个 bug：非主线程调 QTimer.singleShot 静默失效，
导致界面永远停在「准备中 0%」。
"""
import os
import sys
import tempfile
import shutil

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["CHENV_NO_ELEVATE"] = "1"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

import installer

# 缩短范围加速测试，并屏蔽系统写操作
installer.INSTALL_DIRS = ["app", "installer_py"]
installer.INSTALL_FILES = ["CHEN-V.exe", "README.md"]
installer.Installer._write_registry = lambda self: None
installer.Installer._create_shortcut = lambda self: None

app = QApplication(sys.argv)
win = installer.InstallerWindow()
win.show()

target = os.path.join(tempfile.mkdtemp(prefix="cv_gui_"), "CHEN-V")
state = {"vals": [], "done": False, "finish_ok": None}

QTimer.singleShot(100, lambda: win._start_install(target))


def poll():
    v = win.page_progress.bar.value()
    if not state["vals"] or state["vals"][-1] != v:
        state["vals"].append(v)

    cur = win.stack.currentWidget()
    if isinstance(cur, installer.FinishPage):
        state["done"] = True
        state["finish_ok"] = cur.title.text()
        QTimer.singleShot(50, app.quit)


t = QTimer()
t.timeout.connect(poll)
t.start(120)

QTimer.singleShot(90000, app.quit)   # 兜底超时
app.exec()

print("进度值序列:", state["vals"])
print("是否到达完成页:", state["done"])
print("完成页标题:", state["finish_ok"])
print("目标目录已生成:", os.path.isdir(os.path.join(target, "app")))
print("卸载入口:", os.path.isfile(os.path.join(target, "卸载CHEN-V.bat")))

shutil.rmtree(os.path.dirname(target), ignore_errors=True)

ok = state["done"] and len(set(state["vals"])) >= 3 and max(state["vals"] or [0]) >= 99
print("结论:", "通过" if ok else "不通过")
sys.exit(0 if ok else 1)
