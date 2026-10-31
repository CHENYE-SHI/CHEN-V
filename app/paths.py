# -*- coding: utf-8 -*-
"""路径与资源定位：所有模型 / ffmpeg / 运行时都在本地搜索。"""
import procutil
import os
import sys
import json
import shutil
import glob
import subprocess
import tempfile

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP_DIR)                      # ...\画质工厂
STATION = os.path.dirname(ROOT)                      # ...\工具箱大师中转站
MODELS = os.path.join(ROOT, "models")
ASSETS = os.path.join(ROOT, "assets")                # 图标 / 收款码等静态素材
SETTINGS = os.path.join(APP_DIR, "settings.json")

# 临时文件 / 补帧缓存全部放进程序目录，别写 C 盘
WORK_DIR = os.path.join(ROOT, "work")
TEMP_DIR = os.path.join(WORK_DIR, "temp")
CACHE_DIR = os.path.join(WORK_DIR, "cache")
ASCII_DIR = os.path.join(WORK_DIR, "ascii")

SR_ONNX_NAME = "AnimeJaNai_V2_Compact_2x_nc_test_only.onnx"
SR_PTH_NAME = "2x_AnimeJaNai_V2_Compact_36k.pth"


def _mkdir(d):
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        return None
    return d if os.path.isdir(d) else None


def ensure_work_dirs():
    for d in (WORK_DIR, TEMP_DIR, CACHE_DIR, ASCII_DIR):
        _mkdir(d)


def temp_root():
    """抽帧/插帧的临时目录（程序目录优先，建不了才退回系统临时目录）"""
    return _mkdir(TEMP_DIR) or tempfile.gettempdir()


def cache_root(*parts):
    """补帧缓存目录，默认 <程序目录>\\work\\cache\\vfi_cache"""
    base = _mkdir(CACHE_DIR) or os.path.join(
        os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "HuazhiFactory", "cache")
    d = os.path.join(base, *parts) if parts else base
    return _mkdir(d) or base


def ascii_home():
    """第三方扩展用的纯 ASCII 目录：程序目录是 ASCII 就放 work\\ascii，否则退回 LOCALAPPDATA"""
    if is_ascii(WORK_DIR):
        d = _mkdir(ASCII_DIR)
        if d:
            return d
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("ProgramData") or "C:\\ProgramData"
    return _mkdir(os.path.join(base, "HuazhiFactory")) or base


def dir_size(path):
    total = 0
    try:
        if os.path.isfile(path):
            return os.path.getsize(path)
        for base, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(base, f))
                except Exception:
                    pass
    except Exception:
        pass
    return total


def legacy_cache_paths():
    """老版本留在 C 盘的补帧缓存 / 抽帧临时目录"""
    out = []
    base = os.environ.get("LOCALAPPDATA")
    if base:
        p = os.path.join(base, "HuazhiFactory", "vfi_cache")
        if os.path.isdir(p):
            out.append(p)
    for p in glob.glob(os.path.join(tempfile.gettempdir(), "huazhi_*")):
        if os.path.isdir(p):
            out.append(p)
    return out


def purge_caches():
    """清理程序目录的临时/补帧缓存 + 老版本留在 C 盘的缓存，返回释放的字节数"""
    targets = []
    for root in (TEMP_DIR, CACHE_DIR):
        try:
            targets += [os.path.join(root, n) for n in os.listdir(root)]
        except Exception:
            pass
    targets += legacy_cache_paths()
    freed = 0
    for p in targets:
        try:
            freed += dir_size(p)
            if os.path.islink(p):
                os.remove(p)
            elif os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.isfile(p):
                os.remove(p)
        except Exception:
            pass
    return freed


def _first(paths):
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None


def is_ascii(s):
    try:
        s.encode("ascii")
        return True
    except Exception:
        return False


def ascii_mirror(src_dir, name):
    """把目录镜像到纯 ASCII 位置（Tcl 等第三方库对中文路径无解）。

    已存在且文件数一致就直接复用，否则同步复制。
    """
    if is_ascii(src_dir):
        return src_dir
    base = ascii_home()
    dst = os.path.join(base, name)
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        need = True
        if os.path.isdir(dst):
            try:
                a = sum(len(f) for _, _, f in os.walk(src_dir))
                b = sum(len(f) for _, _, f in os.walk(dst))
                need = a != b
            except Exception:
                need = True
        if need:
            shutil.copytree(src_dir, dst, dirs_exist_ok=True)
        return dst
    except Exception:
        return src_dir


def find_ffmpeg():
    cands = [
        os.path.join(ROOT, "ffmpeg", "ffmpeg.exe"),
        os.path.join(STATION, "提升画质", "ffmpeg.exe"),
        os.path.join(STATION, "补帧", "ffmpeg.exe"),
        shutil.which("ffmpeg"),
    ]
    return _first(cands)


def find_sr_models():
    """返回 {显示名: onnx 路径}。只收本工具 models\\sr 下的模型，
    避免把外部工具里不同 IO 约定的 TRT 导出模型混进来。"""
    found = {}
    d = os.path.join(MODELS, "sr")
    if os.path.isdir(d):
        for f in glob.glob(os.path.join(d, "*.onnx")):
            found[os.path.splitext(os.path.basename(f))[0]] = f
    order = [os.path.splitext(SR_ONNX_NAME)[0]]
    rest = sorted(k for k in found if k not in order)
    return {k: found[k] for k in order + rest if k in found}


def find_tariff_models():
    """返回 {显示名: (model_type, model_dir)}，只收 MNN 动态版（可独立运行）"""
    out = {}
    roots = [
        os.path.join(MODELS, "vfi"),
        os.path.join(STATION, "补帧", "model"),
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for d in sorted(glob.glob(os.path.join(root, "Tariff*_mnn"))):
            feat = os.path.join(d, "feature_dynamic.mnn")
            fusi = os.path.join(d, "fusion_dynamic.mnn")
            if not (os.path.isfile(feat) and os.path.isfile(fusi)):
                continue
            sub = os.path.basename(d)
            mt = "nb202" if "nb202" in sub.lower() else "pwr"
            label = sub.replace("Tariff_neu2_", "").replace("_mnn", "")
            out.setdefault(label, (mt, d))
    return out


def find_tariff_pyd():
    """tariff_mnn 扩展模块所在目录（cp311）"""
    cands = [
        os.path.join(MODELS, "vfi", "tariff_mnn.cp311-win_amd64.pyd"),
        os.path.join(STATION, "补帧", "model", "tariff_mnn.cp311-win_amd64.pyd"),
    ]
    p = _first(cands)
    return os.path.dirname(p) if p else None


def ascii_alias(path, name):
    """Tariff 原生扩展用 ANSI 路径打开模型，中文路径会失败。

    这里在程序目录 work\\ascii（或 LOCALAPPDATA 兜底）下建一个纯 ASCII 的目录联接（junction）
    指回真实目录；建联接失败时退化为复制。返回可用于加载模型的路径。
    """
    if is_ascii(path):
        return path
    home = ascii_home()
    link = os.path.join(home, name)
    try:
        os.makedirs(home, exist_ok=True)
    except Exception:
        return path
    try:
        if os.path.isdir(link):
            if os.listdir(link):
                return link
            os.rmdir(link)
    except Exception:
        pass
    try:
        procutil.run(["cmd", "/c", "mklink", "/J", link, path],
                       capture_output=True, creationflags=0x08000000)
        if os.path.isdir(link) and os.listdir(link):
            return link
    except Exception:
        pass
    try:
        shutil.copytree(path, link, dirs_exist_ok=True)
        return link
    except Exception:
        return path


def load_settings():
    try:
        with open(SETTINGS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data):
    try:
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def find_rife_engines():
    """返回 {显示名: {"model": model_dir}}（ncnn 格式 RIFE 模型，供内置加速内核使用）"""
    out = {}
    bases = [os.path.join(MODELS, "vfi_rife"), os.path.join(STATION, "补帧", "model")]
    for b in bases:
        for d in sorted(glob.glob(os.path.join(b, "rife-v*"))):
            if "lite" in os.path.basename(d).lower():   # lite 版用了不支持的 ConvolutionDepthWise 层，跳过
                continue
            if os.path.isfile(os.path.join(d, "flownet.bin")):
                out.setdefault(os.path.basename(d), {"model": d})
    return out
