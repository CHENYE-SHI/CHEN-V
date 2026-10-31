# -*- coding: utf-8 -*-
"""CHEN-V 自研安装器（PySide6）。

复用 CHEN-V 的粒子过渡页风格，做一套完整的安装向导：
  欢迎 → 选择安装目录 → 复制文件（带进度 + 粒子动画）→ 写入注册表/快捷方式 → 完成。

设计要点：
  - 安装器本身用「绿色便携」方式运行：由引导器调用项目自带的 runtime/py311
    解释器来执行本脚本，因此用户机器上无需预装 Python。
  - 界面完全自包含（内嵌简化版粒子系统），不 import app/splash.py——
    因为安装发生时 app 目录尚未就位。
  - 所有耗时操作（文件复制、注册表、快捷方式）都放进后台线程，
    通过信号回主线程刷新进度，主界面绝不卡死。
"""

import os
import sys
import math
import shutil
import subprocess
import threading
import ctypes
import winreg

from PySide6.QtCore import Qt, QEasingCurve, QPointF, QRectF, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QLinearGradient, QRadialGradient
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QLineEdit, QFileDialog, QProgressBar,
                               QMessageBox, QStackedWidget)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
APP_NAME = "CHEN-V"
APP_VERSION = "1.01"
APP_PUBLISHER = "辰师"
APP_URL = "https://github.com/CHENYE-SHI/CHEN-V"
APP_EXE = "CHEN-V.exe"

# 安装器所在目录（payload 根目录 = installer.py 的上一级）
HERE = os.path.dirname(os.path.abspath(__file__))
PAYLOAD_ROOT = os.path.dirname(HERE)

# 要安装的目录清单（相对 payload 根目录）
INSTALL_DIRS = ["app", "runtime", "models", "vrt", "ffmpeg", "assets", "tools"]
INSTALL_FILES = ["CHEN-V.exe", "命令行.bat", "README.md", "LICENSE", "announce.json"]

DEFAULT_INSTALL_DIR = os.path.join(
    os.environ.get("ProgramFiles", r"C:\Program Files"), APP_NAME)


def is_admin():
    """当前进程是否管理员。写 Program Files / HKLM 注册表都需要。"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def default_install_dir():
    """有管理员权限装 Program Files；否则退回用户目录，避免必然失败。"""
    if is_admin():
        return os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), APP_NAME)
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Programs", APP_NAME)


def relaunch_as_admin():
    """用 UAC 提权重新启动本安装器。返回 True 表示已拉起提权实例。"""
    try:
        params = '"%s"' % os.path.abspath(__file__)
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1)
        return rc > 32          # >32 表示成功
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 粒子背景组件（自包含，风格对齐 app/splash.py）
# ---------------------------------------------------------------------------
class ParticleBackdrop(QWidget):
    """深色渐变 + 环绕流动彩色粒子。用作安装向导每一页的背景。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._parts = []
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._advance)
        n = 26
        for i in range(n):
            import random
            rnd = random.Random(i)
            self._parts.append((
                rnd.random() * math.tau,                         # 相位
                (0.7 + rnd.random() * 0.8) * (1 if i % 2 else -1),  # 角速度
                0.28 + rnd.random() * 0.5,                        # 轨道 rx (归一)
                0.18 + rnd.random() * 0.35,                       # 轨道 ry (归一)
                1.1 + rnd.random() * 1.6,                         # 半径
                0.5 + rnd.random() * 0.5,                         # 亮度
            ))

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _advance(self):
        self._t += 0.016
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        # 深蓝紫渐变底
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0.0, QColor(20, 24, 40))
        g.setColorAt(1.0, QColor(12, 14, 24))
        p.fillRect(self.rect(), g)

        cx, cy = w / 2.0, h / 2.0
        for ph, wv, rx, ry, rad, lum in self._parts:
            ang = ph + self._t * wv
            x = cx + math.cos(ang) * rx * w
            y = cy + math.sin(ang) * ry * h
            # 青→蓝→紫→品红 色相范围（对齐 splash）
            hue = 188.0 + (ang % math.tau) / math.tau * 152.0
            c = self._hue(hue)
            c.setAlphaF(lum * 0.9)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawEllipse(QPointF(x, y), rad, rad)
        p.end()

    @staticmethod
    def _hue(hue_deg):
        # 简易 HSV→RGB（S=V=1）
        h = (hue_deg % 360) / 60.0
        i = int(h) % 6
        f = h - int(h)
        q = 1 - f
        t = f
        v = 1
        r, g, b = {
            0: (v, t, 0), 1: (q, v, 0), 2: (0, v, t),
            3: (0, q, v), 4: (t, 0, v), 5: (v, 0, q),
        }[i]
        return QColor(int(r * 255), int(g * 255), int(b * 255))


class Card(QWidget):
    """半透明圆角卡片容器。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(
            "QWidget#card{background:rgba(255,255,255,14);"
            "border:1px solid rgba(255,255,255,28);border-radius:14px;}"
        )


# ---------------------------------------------------------------------------
# 安装逻辑（后台线程）
# ---------------------------------------------------------------------------
class Installer:
    """执行真正的安装动作，进度通过回调回报。"""

    def __init__(self, target_dir):
        self.target_dir = target_dir
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    @property
    def cancelled(self):
        return self._cancel.is_set()

    def _scan(self):
        """预扫描所有待复制文件，返回 [(src, rel), ...] 与总字节数。"""
        items = []
        total = 0
        for f in INSTALL_FILES:
            src = os.path.join(PAYLOAD_ROOT, f)
            if os.path.isfile(src):
                items.append((src, f))
                total += os.path.getsize(src)
        for d in INSTALL_DIRS:
            base = os.path.join(PAYLOAD_ROOT, d)
            if not os.path.isdir(base):
                continue
            for root, _dirs, files in os.walk(base):
                for name in files:
                    src = os.path.join(root, name)
                    rel = os.path.relpath(src, PAYLOAD_ROOT)
                    items.append((src, rel))
                    try:
                        total += os.path.getsize(src)
                    except Exception:
                        pass
        return items, total

    def run(self, on_progress, on_done):
        def _work():
            try:
                items, total = self._scan()
                if not items:
                    on_done(False, "没有找到要安装的文件。")
                    return
                copied = 0
                last_pct = -1
                try:
                    os.makedirs(self.target_dir, exist_ok=True)
                except PermissionError:
                    on_done(False,
                            "没有权限写入 %s。\n请右键安装程序→「以管理员身份运行」，"
                            "或换一个安装目录（如 D:\\CHEN-V）。" % self.target_dir)
                    return
                for src, rel in items:
                    if self.cancelled:
                        on_done(False, "已取消")
                        return
                    dst = os.path.join(self.target_dir, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                    copied += os.path.getsize(src)
                    # 按百分比节流：1.3 万个文件逐个发信号会把事件队列刷爆
                    pct = int(copied * 100 / total) if total else 0
                    if pct != last_pct:
                        last_pct = pct
                        on_progress(copied, total, rel)
                on_progress(total, total, "完成")
                # 运行期空目录
                for d in ("work", "logs"):
                    os.makedirs(os.path.join(self.target_dir, d), exist_ok=True)
                # 注册表 + 快捷方式
                self._write_registry()
                self._create_shortcut()
                self._write_uninstaller()
                # 若本次是从自解压包的临时目录运行，安装完成后清理那份 2.4GB 副本
                self._schedule_temp_cleanup()
                on_done(True, "")
            except PermissionError as e:
                on_done(False,
                        "没有权限写入目标目录。\n请以管理员身份运行，或换个安装目录。\n（%s）" % e)
            except Exception as e:
                on_done(False, str(e))
        threading.Thread(target=_work, daemon=True).start()

    def _schedule_temp_cleanup(self):
        """安装成功后，删除自解压包留在临时目录的 payload 副本。

        只在「payload 位于系统临时目录下」时才动手，避免误删用户自己的目录。
        用独立 bat 延迟删除：安装器自身正运行在这个目录里，无法立刻删掉。
        """
        try:
            root = os.path.abspath(PAYLOAD_ROOT).lower()
            tmp = os.path.abspath(os.environ.get("TEMP") or os.environ.get("TMP") or "").lower()
            if not tmp or not root.startswith(tmp):
                return          # 不是从临时目录运行（例如作者本地调试），不动
            bat = os.path.join(os.environ.get("TEMP", ""), "_chenv_cleanup.bat")
            with open(bat, "w", encoding="utf-8") as f:
                f.write("@echo off\r\n")
                f.write("timeout /t 3 /nobreak >nul\r\n")
                f.write('rmdir /s /q "%s"\r\n' % PAYLOAD_ROOT)
                f.write('del "%%~f0"\r\n')
            subprocess.Popen(["cmd", "/c", bat],
                             creationflags=0x08000000,   # CREATE_NO_WINDOW
                             close_fds=True)
        except Exception:
            pass

    def _write_registry(self):
        key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\CHEN-V"
        data_dir = os.path.join(
            os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP", "."), "CHEN-V")
        uninst_bat = os.path.join(data_dir, "uninstall.bat")
        try:
            with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
                winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
                winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
                winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, APP_PUBLISHER)
                winreg.SetValueEx(k, "DisplayIcon", 0, winreg.REG_SZ,
                                  os.path.join(self.target_dir, "app", "icon.ico"))
                winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ,
                                  '"%s"' % uninst_bat)
                winreg.SetValueEx(k, "URLInfoAbout", 0, winreg.REG_SZ, APP_URL)
                winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
        except Exception:
            pass
        # 安装目录定位（供升级）
        try:
            with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, r"Software\CHEN-V") as k:
                winreg.SetValueEx(k, "InstallDir", 0, winreg.REG_SZ, self.target_dir)
                winreg.SetValueEx(k, "Version", 0, winreg.REG_SZ, APP_VERSION)
        except Exception:
            pass

    def _create_shortcut(self):
        """创建桌面快捷方式。

        runtime 里没有 pywin32，所以走系统自带的 VBScript（cscript）。
        VBS 用 SpecialFolders("Desktop") 取桌面，能正确处理 OneDrive 重定向。
        """
        exe = os.path.join(self.target_dir, APP_EXE)
        work = self.target_dir
        icon = os.path.join(self.target_dir, "app", "icon.ico")

        # 优先 pywin32（开发机可能有）
        try:
            from win32com.client import Dispatch
            shell = Dispatch("WScript.Shell")
            desktop = shell.SpecialFolders("Desktop")
            lnk = shell.CreateShortCut(os.path.join(desktop, "CHEN-V.lnk"))
            lnk.Targetpath = exe
            lnk.WorkingDirectory = work
            lnk.IconLocation = icon
            lnk.save()
            return
        except Exception:
            pass

        # 兜底：VBScript
        try:
            vbs = os.path.join(os.environ.get("TEMP", "."), "_chenv_lnk.vbs")
            with open(vbs, "w", encoding="utf-8") as f:
                f.write('Set sh = CreateObject("WScript.Shell")\r\n')
                f.write('desk = sh.SpecialFolders("Desktop")\r\n')
                f.write('Set lnk = sh.CreateShortcut(desk & "\\CHEN-V.lnk")\r\n')
                f.write('lnk.TargetPath = "%s"\r\n' % exe)
                f.write('lnk.WorkingDirectory = "%s"\r\n' % work)
                f.write('lnk.IconLocation = "%s"\r\n' % icon)
                f.write('lnk.Save\r\n')
            subprocess.run(["cscript", "//nologo", vbs],
                           capture_output=True, creationflags=0x08000000, timeout=20)
            try:
                os.remove(vbs)
            except Exception:
                pass
        except Exception:
            pass

    def _write_uninstaller(self):
        """生成卸载器。

        关键点：卸载脚本必须放在【安装目录之外】，否则删除到一半会把自己锁住，
        残留空目录。这里放到 %LOCALAPPDATA%\\CHEN-V\\uninstall.bat，注册表指向它。
        """
        target = self.target_dir
        data_dir = os.path.join(
            os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP", "."), "CHEN-V")
        os.makedirs(data_dir, exist_ok=True)
        reg_bat = os.path.join(data_dir, "uninstall.bat")

        body = (
            "@echo off\r\n"
            "chcp 65001 >nul\r\n"
            "echo 正在卸载 CHEN-V ...\r\n"
            "timeout /t 1 /nobreak >nul\r\n"
            'rmdir /s /q "%s" 2>nul\r\n' % target
            + 'reg delete "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\CHEN-V" /f >nul 2>nul\r\n'
            + 'reg delete "HKLM\\Software\\CHEN-V" /f >nul 2>nul\r\n'
            + 'del /q "%LOCALAPPDATA%\\CHEN-V\\uninstall.bat" >nul 2>nul\r\n'
            + 'echo CHEN-V 已卸载。\r\n'
            + "timeout /t 2 /nobreak >nul\r\n"
        )
        with open(reg_bat, "w", encoding="utf-8") as f:
            f.write(body)

        # 安装目录里也放一个入口，方便用户直接双击（转调真正的卸载脚本）
        local_bat = os.path.join(target, "卸载CHEN-V.bat")
        with open(local_bat, "w", encoding="utf-8") as f:
            f.write("@echo off\r\n")
            f.write("chcp 65001 >nul\r\n")
            f.write("echo 正在卸载 CHEN-V ...\r\n")
            f.write("copy /y \"%s\" \"%%TEMP%%\\_chenv_uninst.bat\" >nul\r\n" % reg_bat)
            f.write('start "" "%%TEMP%%\\_chenv_uninst.bat"\r\n')
            f.write("exit\r\n")

        self._uninstall_cmd = reg_bat
        # 卸载引导 bat（双击即可，无需 Python 环境也能删）
# ---------------------------------------------------------------------------
# 向导页面
# ---------------------------------------------------------------------------
class WelcomePage(QWidget):
    next_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 40, 48, 40)
        lay.setSpacing(16)

        title = QLabel("欢迎安装 %s" % APP_NAME)
        title.setObjectName("h1")
        lay.addWidget(title)

        sub = QLabel("视频补帧 · 超分增强工具\n版本 V%s  ·  %s" % (APP_VERSION, APP_PUBLISHER))
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        desc = QLabel(
            "本向导将把 CHEN-V 安装到您的计算机。\n\n"
            "安装包含：程序本体、Python 运行时、补帧/超分模型、\n"
            "VapourSynth 与 FFmpeg 运行环境（合计约 2.4 GB）。\n\n"
            "点击「下一步」继续。")
        desc.setObjectName("body")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        lay.addStretch(1)
        btn = QPushButton("下一步")
        btn.setObjectName("primary")
        btn.setMinimumHeight(40)
        btn.clicked.connect(self.next_clicked)
        lay.addWidget(btn)


class DirPage(QWidget):
    next_clicked = Signal(str)
    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 40, 48, 40)
        lay.setSpacing(16)

        title = QLabel("选择安装位置")
        title.setObjectName("h1")
        lay.addWidget(title)

        sub = QLabel("将安装到以下目录：")
        sub.setObjectName("muted")
        lay.addWidget(sub)

        self.edit = QLineEdit(default_install_dir())
        self.edit.setMinimumHeight(36)
        lay.addWidget(self.edit)

        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse)
        lay.addWidget(browse)

        lay.addStretch(1)

        nav = QHBoxLayout()
        back = QPushButton("上一步")
        back.clicked.connect(self.back_clicked)
        nxt = QPushButton("安装")
        nxt.setObjectName("primary")
        nxt.setMinimumHeight(40)
        nxt.clicked.connect(lambda: self.next_clicked.emit(self.edit.text().strip()))
        nav.addWidget(back)
        nav.addStretch(1)
        nav.addWidget(nxt)
        lay.addLayout(nav)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择安装目录", self.edit.text())
        if d:
            self.edit.setText(d)


class ProgressPage(QWidget):
    cancel_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 40, 48, 40)
        lay.setSpacing(16)

        self.title = QLabel("正在安装…")
        self.title.setObjectName("h1")
        lay.addWidget(self.title)

        self.stage = QLabel("准备中")
        self.stage.setObjectName("muted")
        self.stage.setWordWrap(True)
        lay.addWidget(self.stage)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(True)
        lay.addWidget(self.bar)

        lay.addStretch(1)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.cancel_clicked)
        nav = QHBoxLayout()
        nav.addStretch(1)
        nav.addWidget(self.cancel_btn)
        lay.addLayout(nav)

    def set_progress(self, copied, total, rel):
        pct = int(copied * 100 / total) if total else 0
        self.bar.setValue(pct)
        self.stage.setText("正在复制：%s" % rel)


class FinishPage(QWidget):
    finish_clicked = Signal()

    def __init__(self, ok, message, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 40, 48, 40)
        lay.setSpacing(16)

        self.title = QLabel("安装完成" if ok else "安装失败")
        self.title.setObjectName("h1")
        lay.addWidget(self.title)

        msg = QLabel(message or "CHEN-V 已成功安装到您的计算机。\n\n您可以在桌面双击快捷方式启动。")
        msg.setObjectName("body")
        msg.setWordWrap(True)
        lay.addWidget(msg)

        lay.addStretch(1)
        btn = QPushButton("完成")
        btn.setObjectName("primary")
        btn.setMinimumHeight(40)
        btn.clicked.connect(self.finish_clicked)
        lay.addWidget(btn)


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------
class InstallerWindow(QWidget):
    # 后台线程 → 主线程 用信号（QueuedConnection 自动跨线程）。
    # 注意：非主线程调用 QTimer.singleShot 会静默失效，进度就一直停在 0%。
    sig_progress = Signal(int, int, str)
    sig_done = Signal(bool, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("%s 安装程序" % APP_NAME)
        self.setFixedSize(640, 460)
        self._center_on_screen()

        # 背景粒子
        self._bg = ParticleBackdrop(self)
        self._bg.setGeometry(self.rect())
        self._bg.start()

        # 卡片 + 页面栈
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        self.card = Card(self)
        outer.addWidget(self.card)

        self.stack = QStackedWidget(self.card)
        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(4, 4, 4, 4)
        card_lay.addWidget(self.stack)

        self._installer = None
        self._target = None

        self.page_welcome = WelcomePage()
        self.page_dir = DirPage()
        self.page_progress = ProgressPage()

        self.stack.addWidget(self.page_welcome)
        self.stack.addWidget(self.page_dir)
        self.stack.addWidget(self.page_progress)

        # 连接
        self.page_welcome.next_clicked.connect(lambda: self.stack.setCurrentWidget(self.page_dir))
        self.page_dir.next_clicked.connect(self._start_install)
        self.page_dir.back_clicked.connect(lambda: self.stack.setCurrentWidget(self.page_welcome))
        self.page_progress.cancel_clicked.connect(self._cancel_install)

        self._apply_style()

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.center().x() - self.width() // 2,
                      geo.center().y() - self.height() // 2)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._bg.setGeometry(self.rect())

    def _apply_style(self):
        self.setStyleSheet("""
            QLabel#h1 { color:#f0f5fa; font-size:24px; font-weight:600; }
            QLabel#muted { color:#96a5b6; font-size:13px; }
            QLabel#body { color:#d6dfe8; font-size:14px; line-height:1.5; }
            QLineEdit {
                background:rgba(255,255,255,18); border:1px solid rgba(255,255,255,32);
                border-radius:8px; color:#eaf1f8; padding:8px 12px; font-size:14px;
            }
            QPushButton {
                background:rgba(255,255,255,22); border:1px solid rgba(255,255,255,34);
                border-radius:8px; color:#e6eef6; padding:10px 22px; font-size:14px;
            }
            QPushButton:hover { background:rgba(255,255,255,40); }
            QPushButton#primary {
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #3a7bd5, stop:1 #6a5acd); color:#ffffff; border:none; font-weight:600;
            }
            QPushButton#primary:hover { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #4a8be5, stop:1 #7a6add); }
            QProgressBar {
                background:rgba(255,255,255,16); border:none; border-radius:7px;
                height:14px; text-align:center; color:#eaf1f8; font-size:12px;
            }
            QProgressBar::chunk {
                border-radius:7px;
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #3a7bd5, stop:1 #6a5acd);
            }
        """)

    # --------------------------------------------------------- 安装流程
    def _start_install(self, target):
        if not target:
            QMessageBox.warning(self, "提示", "请选择安装目录。")
            return
        target = os.path.abspath(target)
        self._target = target
        self.stack.setCurrentWidget(self.page_progress)
        self.page_progress.title.setText("正在安装…")
        self.page_progress.stage.setText("准备中")
        self.page_progress.bar.setValue(0)
        self.page_progress.cancel_btn.setEnabled(True)

        self.sig_progress.connect(self._apply_progress)
        self.sig_done.connect(self._apply_done)

        self._installer = Installer(target)
        self._installer.run(
            on_progress=lambda c, t, r: self.sig_progress.emit(c, t, r),
            on_done=lambda ok, msg: self.sig_done.emit(ok, msg),
        )

    # 下面两个槽由信号在【主线程】调用，可以安全操作控件
    def _apply_progress(self, copied, total, rel):
        self.page_progress.set_progress(copied, total, rel)

    def _apply_done(self, ok, message):
        self._bg.stop()
        page = FinishPage(ok, message)
        page.finish_clicked.connect(self.close)
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)

    def _cancel_install(self):
        if self._installer:
            self._installer.cancel()
            self.page_progress.cancel_btn.setEnabled(False)
            self.page_progress.stage.setText("正在取消…")


def main():
    # 写 Program Files 与 HKLM 注册表需要管理员；没有就请求一次 UAC 提权。
    # 用户拒绝提权时继续运行，安装目录会自动退回用户可写目录。
    # CHENV_NO_ELEVATE=1 供自动化测试跳过提权。
    if not is_admin() and not os.environ.get("CHENV_NO_ELEVATE"):
        if relaunch_as_admin():
            return          # 提权实例接管，本进程退出

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    win = InstallerWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
