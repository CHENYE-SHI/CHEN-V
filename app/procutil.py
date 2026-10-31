# -*- coding: utf-8 -*-
"""子进程统一不弹黑框：Windows 下给所有 subprocess 调用加 CREATE_NO_WINDOW。"""
import os
import subprocess

CREATE_NO_WINDOW = 0x08000000

if os.name == "nt":
    _si = subprocess.STARTUPINFO()
    _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _si.wShowWindow = 0          # SW_HIDE
    KW = {"creationflags": CREATE_NO_WINDOW, "startupinfo": _si}
else:
    KW = {}


def popen(*args, **kw):
    for k, v in KW.items():
        kw.setdefault(k, v)
    return subprocess.Popen(*args, **kw)


def run(*args, **kw):
    for k, v in KW.items():
        kw.setdefault(k, v)
    return subprocess.run(*args, **kw)
