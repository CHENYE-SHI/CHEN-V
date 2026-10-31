# -*- coding: utf-8 -*-
"""ncnn + Vulkan 超分（waifu2x / RealESRGAN 系列），模型来自本地模型包。

不需要 onnxruntime：只用到两个包装模块
（waifu2x_ncnn_vulkan.py / realesrgan_ncnn_vulkan.py）和它们各自的 .pyd 绑定。
"""
import os
import sys
import types

_NP = None


def _npl():
    """numpy 延迟导入（0.15s）：界面启动只需要本模块的类定义，别压在过渡页上。"""
    global _NP
    if _NP is None:
        import numpy
        _NP = numpy
    return _NP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR_DIR = os.path.join(ROOT, "models", "sr_ncnn")
W2X_DIR = os.path.join(SR_DIR, "waifu2x")
ESR_DIR = os.path.join(SR_DIR, "ncnnRealESR")

# 注意：不再扫描 SVFI 等外部软件目录里的模型，只保留本项目 models 目录内
# 真实存在的模型，避免下拉框列出程序文件夹里没有的模型。


def _install_utils_stub(models_dir):
    """两个包装模块都会 import Utils.StaticParameters，这里给个假的"""
    if "Utils.StaticParameters" in sys.modules:
        try:
            sys.modules["Utils.StaticParameters"].modelsDir = models_dir
        except Exception:
            pass
        return
    u = types.ModuleType("Utils")
    sp = types.ModuleType("Utils.StaticParameters")
    sp.modelsDir = models_dir
    sp.runningEnv = "windows"
    sp.StaticModelsDir = models_dir
    u.StaticParameters = sp
    sys.modules["Utils"] = u
    sys.modules["Utils.StaticParameters"] = sp


def list_ncnn_sr():
    """返回 {显示名: (kind, model_name)}；kind = 'waifu2x' | 'realesr'

    model_name 说明：
      - waifu2x：模型子目录名（目录内一个 .param/.bin）
      - realesr：分两种情况
          * 常规：models/<m>/<m>.param —— model_name 就是 <m>
          * Real-CUGAN 等「一个目录装多个 .param」：models/<dir>/<x>.param
            —— model_name 写成 "<dir>/<x>"，便于 sr_param 直接定位
    """
    out = {}
    w2x = os.path.join(W2X_DIR, "models")
    if os.path.isdir(w2x):
        for m in sorted(os.listdir(w2x)):
            if os.path.isdir(os.path.join(w2x, m)):
                out["%s（ncnn）" % m] = ("waifu2x", m)
    esr = os.path.join(ESR_DIR, "models")
    if os.path.isdir(esr):
        for m in sorted(os.listdir(esr)):
            d = os.path.join(esr, m)
            if not os.path.isdir(d):
                continue
            # Real-CUGAN 的 .param 版（up2 目录）含 Pooling（全局平均池化）算子，
            # 当前 slvncnn 内核不支持，加载必然崩溃（layer Pooling not exists）。
            # 同名模型在 models\\sr 下已有 onnx 版（走 vsncnn，已验证可跑），
            # 这里跳过 .param 版，避免下拉框列出会崩的冗余项。
            if m.lower() == "up2":
                continue
            # 目录内是否直接放了 .param 文件（Real-CUGAN ncnn 版就是这种结构）
            params = sorted(f[:-6] for f in os.listdir(d)
                            if f.lower().endswith(".param"))
            if params:
                # 若存在与目录同名的 <m>.param，按常规单模型处理，其余作为附加模型
                if ("%s.param" % m) in [f for f in os.listdir(d) if f.lower().endswith(".param")]:
                    out["%s（ncnn）" % m] = ("realesr", m)
                    rest = [p for p in params if p != m]
                else:
                    rest = params
                for p in rest:
                    out["%s（ncnn）" % p] = ("realesr", "%s/%s" % (m, p))
            else:
                # 目录内没有 .param（例如只有子目录），按老逻辑当作模型名
                out["%s（ncnn）" % m] = ("realesr", m)
    return out


class SrNcnn(object):
    """和 sr.SrEngine 同接口：upscale(HxWx3 uint8) -> uint8"""

    def __init__(self, kind, model, gpuid=0, log=print):
        np = _npl()
        self.log = log
        self.kind = kind
        self.model = model
        self.providers = ["ncnn-vulkan"]
        if kind == "waifu2x":
            _install_utils_stub(os.path.join(W2X_DIR, "models"))
            if W2X_DIR not in sys.path:
                sys.path.insert(0, W2X_DIR)
            import waifu2x_ncnn_vulkan as w2x
            self._net = w2x.Waifu2x(gpuid=gpuid, scale=0, denoise=0, tilesize=0, model=model)
            self.scale = 2 if "scale2x" in model or "x2" in model else 1
        else:
            _install_utils_stub(os.path.join(ESR_DIR, "models"))
            if ESR_DIR not in sys.path:
                sys.path.insert(0, ESR_DIR)
            if "cv2" not in sys.modules:
                # 这个包装只是 import cv2，并没有真的用到；给个空壳免得装 OpenCV
                cv2 = types.ModuleType("cv2")
                cv2.INTER_LINEAR = 1
                cv2.resize = lambda img, size, interpolation=1: np.asarray(img)
                sys.modules["cv2"] = cv2
            import realesrgan_ncnn_vulkan as esr
            cls = (getattr(esr, "Realesrgan", None) or getattr(esr, "RealESRGAN", None)
                   or getattr(esr, "RealESR"))
            try:
                self._net = cls(gpuid=gpuid, tilesize=0, model=model, tta_mode=False)
            except TypeError:
                self._net = cls(gpuid=gpuid, model=model)
            if "x4" in model:
                self.scale = 4
            elif "x3" in model:
                self.scale = 3
            else:
                self.scale = 2
        self.log("超分后端：ncnn-vulkan（%s）" % model)

    def upscale(self, img):
        np = _npl()
        fn = getattr(self._net, "enhance", None) or getattr(self._net, "process", None)
        if fn is None:
            raise RuntimeError("这个 ncnn 包装没有 enhance/process 方法")
        out = fn(np.ascontiguousarray(img))
        arr = np.asarray(out)
        if arr.ndim == 2:
            arr = np.stack([arr] * 3, -1)
        if arr.shape[-1] != 3 and arr.shape[0] == 3:
            arr = arr.transpose(1, 2, 0)
        return np.clip(arr, 0, 255).astype(np.uint8)
