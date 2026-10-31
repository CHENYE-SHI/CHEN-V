# -*- coding: utf-8 -*-
"""画质工厂入口：优先用 Qt 界面（支持半透明面板），没有 PySide6 就退回 Tk 界面。"""
import os
import sys
import traceback

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


def _start_splash():
    """先起过渡页：只依赖 PySide6，能在 import gui_main（含 numpy/PIL）之前显示。"""
    try:
        import splash
        return splash.start()
    except Exception:
        return None


def _close_splash(splash):
    if splash is None:
        return
    try:
        splash.close()
    except Exception:
        pass


def main():
    # 完整性校验：核心文件被篡改则拒绝运行（防「改品牌拿去卖」）。
    # 没有 manifest（源码开发环境）时静默放行，不影响开发。
    try:
        import integrity
        _ok, _reason = integrity.bootstrap()
        if not _ok:
            _show_tamper_error(_reason)
            return 1
    except Exception:
        pass

    # 先把编码器列表 / 显卡名丢到后台去探（子进程约 0.15s）——这段正好和
    # 下面 import PySide6（约 0.6s）重叠掉，等界面构建到要显示它们时已经就绪
    try:
        import envprobe
        envprobe.start()
    except Exception:
        pass
    splash = _start_splash()
    try:
        import gui_main
    except ImportError:
        gui_main = None
    except Exception:
        _log_error()
        gui_main = None
    if gui_main is not None:
        try:
            return gui_main.run(splash)
        except Exception:
            _log_error()
            _close_splash(splash)
    else:
        _close_splash(splash)
    try:
        import gui_qt
        return gui_qt.run()
    except ImportError:
        pass
    except Exception:
        _log_error()
    import tkboot
    tkboot.setup_tcl()
    import gui
    gui.run()
    return 0


def _log_error():
    log_dir = os.path.join(os.path.dirname(APP_DIR), "logs")
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, "error.log"), "a", encoding="utf-8") as f:
        f.write(traceback.format_exc() + "\n")


def _show_tamper_error(reason):
    """核心文件被篡改时，用最轻量的方式提示（此时 GUI 可能已被破坏，不依赖它）。"""
    msg = ("检测到程序核心文件被篡改，已停止运行。\n"
           "请从官方渠道重新下载 CHEN-V。\n"
           "（%s）" % (reason or "integrity check failed"))
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "CHEN-V", 0x10)
    except Exception:
        pass
    try:
        print("[CHEN-V] " + msg)
    except Exception:
        pass


if __name__ == "__main__":
    main()
