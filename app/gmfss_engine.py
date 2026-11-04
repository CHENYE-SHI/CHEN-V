# -*- coding: utf-8 -*-
"""GMFSS Fortuna Union 推理封装（PyTorch / CUDA）。

模型结构取自 98mxr/GMFSS_Fortuna（MIT），权重为 GMFSS_Fortuna Union 的
state_dict（feat / metric / flownet / fusionnet / rife）。
本文件只做工程封装：numpy <-> tensor、64 倍数补边、按帧对复用光流与特征。

依赖 torch（可选组件）。没装 torch 或没放权重时 available() 返回 False，
主程序照常运行，只是补帧模型列表里不会出现 GMFSS。
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))          # .../app
ROOT = os.path.dirname(HERE)                               # 程序根目录
PLUGIN_DIR = os.path.join(ROOT, "vrt", "plugins", "gmfss")  # 第三方模型代码
WEIGHTS_DIR = os.path.join(PLUGIN_DIR, "weights")
for _p in (PLUGIN_DIR, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

WEIGHT_FILES = ("feat.pkl", "metric.pkl", "flownet.pkl", "fusionnet.pkl", "rife.pkl")
_IMPORT_ERR = ""


def _torch():
    global _IMPORT_ERR
    try:
        import torch  # noqa: F401
        return torch
    except Exception as e:      # 未安装或 DLL 缺失
        _IMPORT_ERR = "%s: %s" % (type(e).__name__, e)
        return None


def torch_dir():
    """torch 实际装在哪：vrt/python/Lib/site-packages/torch。"""
    return os.path.join(ROOT, "vrt", "python", "Lib", "site-packages", "torch")


def available():
    """返回 (是否可用, 原因)。

    注意：这里不能靠 import torch 判断——界面进程用的是 runtime/py311，
    本来就没装 torch；真正跑推理的是 vrt/python。所以看磁盘上有没有。
    """
    if not os.path.isdir(torch_dir()):
        return False, "未安装 PyTorch（可选组件）"
    miss = [n for n in WEIGHT_FILES
            if not os.path.isfile(os.path.join(WEIGHTS_DIR, n))]
    if miss:
        return False, "缺少模型权重：" + "、".join(miss)
    return True, ""


def _pad_to(t, mult=64):
    """把 (1,C,H,W) 右侧/下侧复制补齐到 mult 的整数倍，返回 (t, h, w)。"""
    h, w = int(t.shape[-2]), int(t.shape[-1])
    ph, pw = (-h) % mult, (-w) % mult
    if ph or pw:
        t = torch_pad(t, pw, ph)
    return t, h, w


def torch_pad(t, pw, ph):
    import torch.nn.functional as F
    return F.pad(t, (0, pw, 0, ph), mode="replicate")


class GmfssUnion(object):
    """一对帧 -> 若干中间帧。首次调用会加载 5 个网络（约 2~4 秒）。"""

    def __init__(self, device=None, fp16=True):
        torch = _torch()
        if torch is None:
            raise RuntimeError("未安装 PyTorch（%s）" % _IMPORT_ERR)
        from model.FeatureNet import FeatureNet
        from model.MetricNet import MetricNet
        from model.FusionNet_u import GridNet
        from model.gmflow.gmflow import GMFlow
        from model.IFNet_HDv3 import IFNet

        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.torch = torch
        self.device = torch.device(device)
        # 只有 CUDA 才用半精度；CPU 上半精度又慢又容易出错
        self.fp16 = bool(fp16 and self.device.type == "cuda")

        self.flownet = GMFlow()
        self.ifnet = IFNet()
        self.metricnet = MetricNet()
        self.feat_ext = FeatureNet()
        self.fusionnet = GridNet()

        for mod, name in ((self.flownet, "flownet"), (self.ifnet, "rife"),
                          (self.metricnet, "metric"), (self.feat_ext, "feat"),
                          (self.fusionnet, "fusionnet")):
            sd = torch.load(os.path.join(WEIGHTS_DIR, name + ".pkl"),
                            map_location="cpu", weights_only=True)
            mod.load_state_dict(sd)
            mod.eval()
            mod.to(self.device)
        for p in (list(self.flownet.parameters()) + list(self.ifnet.parameters())
                  + list(self.metricnet.parameters())
                  + list(self.feat_ext.parameters())
                  + list(self.fusionnet.parameters())):
            p.requires_grad_(False)

    # ---------------------------------------------------------------- 内部
    def _to_tensor(self, img_u8):
        """(H,W,3) uint8 RGB -> (1,3,H,W) float32 [0,1]。"""
        arr = np.array(img_u8, dtype=np.uint8, copy=True)   # torch 不接受只读数组
        t = self.torch.from_numpy(arr)
        t = t.permute(2, 0, 1).unsqueeze(0).to(self.device).float() / 255.0
        return t

    def _to_u8(self, t, h, w):
        t = t[:, :, :h, :w].clamp(0, 1).float().mul(255.0).round()
        arr = t[0].permute(1, 2, 0).contiguous().to("cpu").numpy()
        return arr.astype(np.uint8)

    def _reuse(self, img0, img1):
        """按 GMFSS_infer_u.reuse()：特征 + 双向光流 + metric（与时间步无关）。"""
        torch = self.torch
        import torch.nn.functional as F
        feat0 = self.feat_ext(img0)
        feat1 = self.feat_ext(img1)
        h0 = F.interpolate(img0, scale_factor=0.5, mode="bilinear", align_corners=False)
        h1 = F.interpolate(img1, scale_factor=0.5, mode="bilinear", align_corners=False)
        flow01 = self.flownet(h0, h1)
        flow10 = self.flownet(h1, h0)
        metric0, metric1 = self.metricnet(h0, h1, flow01, flow10)
        return {"flow01": flow01, "flow10": flow10, "metric0": metric0,
                "metric1": metric1, "feat0": feat0, "feat1": feat1,
                "h0": h0, "h1": h1}

    def _forward(self, cache, timestep):
        import torch.nn.functional as F
        from model.softsplat_torch import softsplat as warp

        flow01, flow10 = cache["flow01"], cache["flow10"]
        metric0, metric1 = cache["metric0"], cache["metric1"]
        feat11, feat12, feat13 = cache["feat0"]
        feat21, feat22, feat23 = cache["feat1"]
        h0, h1 = cache["h0"], cache["h1"]

        f1t = timestep * flow01
        f2t = (1 - timestep) * flow10
        z1t = timestep * metric0
        z2t = (1 - timestep) * metric1

        i1t = warp(h0, f1t, z1t, strMode="soft")
        i2t = warp(h1, f2t, z2t, strMode="soft")

        rife = self.ifnet(self.torch.cat((h0, h1), 1), timestep, scale_list=[8, 4, 2, 1])

        feat1t1 = warp(feat11, f1t, z1t, strMode="soft")
        feat2t1 = warp(feat21, f2t, z2t, strMode="soft")

        f1d = F.interpolate(f1t, scale_factor=0.5, mode="bilinear", align_corners=False) * 0.5
        z1d = F.interpolate(z1t, scale_factor=0.5, mode="bilinear", align_corners=False)
        feat1t2 = warp(feat12, f1d, z1d, strMode="soft")
        f2d = F.interpolate(f2t, scale_factor=0.5, mode="bilinear", align_corners=False) * 0.5
        z2d = F.interpolate(z2t, scale_factor=0.5, mode="bilinear", align_corners=False)
        feat2t2 = warp(feat22, f2d, z2d, strMode="soft")

        f1dd = F.interpolate(f1t, scale_factor=0.25, mode="bilinear", align_corners=False) * 0.25
        z1dd = F.interpolate(z1t, scale_factor=0.25, mode="bilinear", align_corners=False)
        feat1t3 = warp(feat13, f1dd, z1dd, strMode="soft")
        f2dd = F.interpolate(f2t, scale_factor=0.25, mode="bilinear", align_corners=False) * 0.25
        z2dd = F.interpolate(z2t, scale_factor=0.25, mode="bilinear", align_corners=False)
        feat2t3 = warp(feat23, f2dd, z2dd, strMode="soft")

        out = self.fusionnet(
            self.torch.cat([i1t, rife, i2t], dim=1),
            self.torch.cat([feat1t1, feat2t1], dim=1),
            self.torch.cat([feat1t2, feat2t2], dim=1),
            self.torch.cat([feat1t3, feat2t3], dim=1))
        return self.torch.clamp(out, 0, 1)

    # ---------------------------------------------------------------- 对外
    def interpolate(self, img0_u8, img1_u8, timesteps):
        """两帧 uint8 RGB -> 若干中间帧 uint8 RGB（与原图同尺寸）。"""
        torch = self.torch
        t0 = self._to_tensor(img0_u8)
        t1 = self._to_tensor(img1_u8)
        t0, h, w = _pad_to(t0)
        t1, _, _ = _pad_to(t1)
        if self.fp16:
            import contextlib
            ctx = torch.autocast(device_type="cuda", dtype=torch.float16)
        else:
            import contextlib
            ctx = contextlib.nullcontext()
        with torch.inference_mode(), ctx:
            cache = self._reuse(t0, t1)
            outs = [self._forward(cache, float(ts)) for ts in timesteps]
            return [self._to_u8(o, h, w) for o in outs]
