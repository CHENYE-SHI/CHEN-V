# -*- coding: utf-8 -*-
"""补帧引擎：Tariff（MNN 动态图 + OpenCL 后端）。

模型目录内是 feature_dynamic.mnn / fusion_dynamic.mnn，
时间步张量形状：pwr -> [B,T,H,W]，nb202 -> [B,T,H/2,W/2]（由原生扩展内部处理 padding）。
"""
import os
import sys
import numpy as np


class TariffEngine(object):
    def __init__(self, model_type, model_dir, pyd_dir=None, log=print):
        if pyd_dir and pyd_dir not in sys.path:
            sys.path.insert(0, pyd_dir)
        import tariff_mnn                       # cp311 原生扩展
        self._mod = tariff_mnn
        self.model_type = model_type
        self.model_dir = model_dir
        # 原生扩展内部按 ANSI 打开文件，中文路径会失败 -> 走 ASCII 目录联接
        try:
            import paths
            usable = paths.ascii_alias(model_dir, "tariff_" + model_type)
        except Exception:
            usable = model_dir
        self.feat = os.path.join(usable, "feature_dynamic.mnn")
        self.fusi = os.path.join(usable, "fusion_dynamic.mnn")
        if not (os.path.isfile(self.feat) and os.path.isfile(self.fusi)):
            raise RuntimeError("Tariff 模型文件缺失：%s" % model_dir)
        self._proc = None
        self._shape = None
        self.log = log

    def _ensure(self, h, w):
        # 原生扩展是"单分辨率"的，分辨率变了必须重建
        if self._proc is None or self._shape != (h, w):
            self.log("加载 Tariff 模型（%s, %dx%d）…" % (self.model_type, w, h))
            self._proc = self._mod.TariffProcessor(self.feat, self.fusi, self.model_type)
            self._shape = (h, w)

    def interpolate(self, a_rgb, b_rgb, timesteps):
        """a_rgb / b_rgb: HxWx3 uint8；timesteps: 0~1 浮点列表；返回同尺寸 uint8 列表"""
        h, w = a_rgb.shape[:2]
        self._ensure(h, w)
        A = (a_rgb.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
        B = (b_rgb.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
        if self.model_type.startswith("nb"):
            th, tw = h // 2, w // 2
        else:
            th, tw = h, w
        T = np.empty((1, len(timesteps), th, tw), np.float32)
        for i, t in enumerate(timesteps):
            T[0, i] = float(t)
        outs = self._proc.process(A, B, T)
        res = []
        for o in outs:
            arr = np.clip(np.asarray(o, np.float32)[0].transpose(1, 2, 0), 0.0, 1.0)
            res.append((arr * 255.0 + 0.5).astype(np.uint8))
        return res

    def close(self):
        self._proc = None
