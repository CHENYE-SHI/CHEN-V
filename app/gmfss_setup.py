# -*- coding: utf-8 -*-
"""安装 GMFSS 可选组件（PyTorch CUDA 12.8）。

GMFSS 走 PyTorch 推理，主程序不自带 torch（约 2.7GB）。
运行本脚本 = 给 vrt\\python 装 pip + 装 torch(cu128) + 自检。

用法：双击根目录的「安装GMFSS组件.bat」，或
      runtime\\py311\\python.exe app\\gmfss_setup.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VRT_PY = os.path.join(ROOT, "vrt", "python", "python.exe")
HOST_PY = os.path.join(ROOT, "runtime", "py311", "python.exe")
APP = os.path.join(ROOT, "app")


def run(args, **kw):
    print("  >", " ".join(args))
    return subprocess.call(args, **kw)


def has_pip():
    p = subprocess.run([VRT_PY, "-m", "pip", "--version"],
                       capture_output=True, text=True)
    return p.returncode == 0


def has_torch():
    p = subprocess.run([VRT_PY, "-c", "import torch;print(torch.__version__)"],
                       capture_output=True, text=True)
    if p.returncode == 0:
        print("已安装 torch:", p.stdout.strip())
        return True
    return False


def main():
    print("=" * 60)
    print("CHEN-V · GMFSS 组件安装")
    print("=" * 60)
    if not os.path.isfile(VRT_PY):
        print("找不到 vrt\\python\\python.exe，请在程序安装目录里运行。")
        return 1

    if not has_pip():
        print("[1/3] 给内置 Python 装 pip …")
        if run([HOST_PY, "-m", "pip", "install", "--quiet", "--target",
                os.path.join(ROOT, "vrt", "python", "Lib", "site-packages"),
                "pip"]) != 0:
            print("pip 安装失败。")
            return 1
    else:
        print("[1/3] pip 已就绪")

    print("[2/3] 安装 numpy（约 15MB）…")
    run([VRT_PY, "-m", "pip", "install", "--no-cache-dir", "numpy"])

    if has_torch():
        print("      torch 已安装，跳过下载")
    else:
        print("      下载并安装 torch cu128（约 2.8GB，视网速 10~40 分钟）…")
        if run([VRT_PY, "-m", "pip", "install", "--no-cache-dir",
                "--index-url", "https://download.pytorch.org/whl/cu128",
                "torch"]) != 0:
            print("torch 安装失败，请检查网络后重试。")
            return 1

    print("[3/3] 自检 …")
    code = ("import sys;sys.path.insert(0, r'%s');import numpy, torch;"
            "import gmfss_engine as g;"
            "print('numpy', numpy.__version__, '| torch', torch.__version__,"
            "'| cuda', torch.cuda.is_available()); print(g.available())" % APP)
    run([VRT_PY, "-c", code])
    print("\n完成。重启 CHEN-V，补帧模型里会出现「GMFSS Fortuna Union（光流·动漫）」。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
