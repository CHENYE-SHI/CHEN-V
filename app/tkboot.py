# -*- coding: utf-8 -*-
"""Tcl/Tk 引导：Tcl 解释器不接受中文路径下的 tcl_library，这里镜像到 ASCII 目录再指过去。"""
import os
import sys


def setup_tcl():
    home = os.path.dirname(sys.executable)
    tcl = os.path.join(home, "tcl")
    if not os.path.isdir(tcl):
        return
    try:
        tcl.encode("ascii")
        base = tcl
    except Exception:
        try:
            import paths
            base = paths.ascii_mirror(tcl, "tcl")
        except Exception:
            base = tcl
    os.environ.setdefault("TCL_LIBRARY", os.path.join(base, "tcl8.6"))
    os.environ.setdefault("TK_LIBRARY", os.path.join(base, "tk8.6"))
