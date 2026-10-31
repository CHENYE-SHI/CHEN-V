
def _preload_cuda():
    """把 pip 装的 CUDA/cuDNN DLL 目录挂上，否则 CUDAExecutionProvider 会初始化失败退回 CPU"""
    import glob
    import os
    import sys
    sp = os.path.join(sys.prefix, "Lib", "site-packages")
    dirs = []
    for pat in ("nvidia/*/bin", "nvidia/*/lib", "nvidia/*/lib/x64"):
        dirs += glob.glob(os.path.join(sp, pat))
    if not dirs:
        return
    os.environ["PATH"] = os.pathsep.join(dirs) + os.pathsep + os.environ.get("PATH", "")
    for d in dirs:
        try:
            os.add_dll_directory(d)
        except Exception:
            pass


# -*- coding: utf-8 -*-
"""超分引擎：AnimeJaNai 系列 ONNX，走 onnxruntime（优先 DirectML，其次 CPU）。

模型 IO 约定（nc_test_only 版本）：
    input  : float16 [1,3,H,W]，取值 0~1
    output : float16 [1,3,H*scale,W*scale]
"""
_NP = None


def _npl():
    """numpy 延迟导入。

    它要 0.15s，而界面启动时只是 import 本模块拿类定义；放在顶层会把这段
    时间压在启动过渡页上（动画定住）。真正推理时再付这笔账，用户看不见。
    """
    global _NP
    if _NP is None:
        import numpy
        _NP = numpy
    return _NP


class SrEngine(object):
    def __init__(self, model_path, device="auto", tile=0, pad=16, log=print):
        import onnxruntime as ort
        self._ort = ort
        self.log = log
        self.model_path = model_path
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        so.log_severity_level = 3
        _preload_cuda()
        avail = ort.get_available_providers()
        providers = []
        # 优先级：CUDA（onnxruntime-gpu）→ DirectML → CPU
        if device in ("auto", "cuda", "dml") and "CUDAExecutionProvider" in avail:
            providers.append("CUDAExecutionProvider")
        if device in ("auto", "dml") and "DmlExecutionProvider" in avail:
            providers.append("DmlExecutionProvider")
        providers.append("CPUExecutionProvider")
        self.sess = ort.InferenceSession(model_path, so, providers=providers)
        np = _npl()
        self.providers = self.sess.get_providers()
        i = self.sess.get_inputs()[0]
        o = self.sess.get_outputs()[0]
        self.in_name, self.in_type = i.name, i.type
        self.out_name, self.out_type = o.name, o.type
        self.dtype = np.float16 if "float16" in self.in_type else np.float32
        self.tile = int(tile or 0)
        self.pad = int(pad)
        self.native_scale = None

    # ---------------------------------------------------------------- 内部
    def _run(self, tile_f32):
        np = _npl()
        y = self.sess.run([self.out_name], {self.in_name: tile_f32.astype(self.dtype)})[0]
        return np.asarray(y, np.float32)

    def _tiled(self, x, h, w):
        np = _npl()
        T, P = self.tile, self.pad
        out = None
        scale = None
        while T >= 128:
            try:
                for y0 in range(0, h, T):
                    for x0 in range(0, w, T):
                        y1, x1 = min(y0 + T, h), min(x0 + T, w)
                        py0, px0 = max(0, y0 - P), max(0, x0 - P)
                        py1, px1 = min(h, y1 + P), min(w, x1 + P)
                        tile = x[:, :, py0:py1, px0:px1]
                        o = self._run(tile)[0]
                        s = o.shape[-2] // tile.shape[-2]
                        if scale is None:
                            scale = s
                            out = np.empty((3, h * s, w * s), np.float32)
                        oy, ox = (y0 - py0) * s, (x0 - px0) * s
                        out[:, y0 * s:y1 * s, x0 * s:x1 * s] = \
                            o[:, oy:oy + (y1 - y0) * s, ox:ox + (x1 - x0) * s]
                return out[None], scale
            except Exception as e:                                  # 显存不足等
                self.tile = T = T // 2
                self.log("分块推理失败（%s），缩小分块到 %d 重试" % (str(e)[:80], T))
        raise RuntimeError("超分推理失败：分块已缩到最小仍报错")

    # ---------------------------------------------------------------- 对外
    def upscale(self, img_rgb):
        """img_rgb: HxWx3 uint8 -> HxWx3 uint8（放大 native_scale 倍）"""
        np = _npl()
        h, w = img_rgb.shape[:2]
        x = (img_rgb.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
        if self.tile and (h > self.tile or w > self.tile):
            out, s = self._tiled(x, h, w)
        else:
            try:
                out = self._run(x)
                s = out.shape[-2] // h
            except Exception as e:
                if not self.tile:
                    self.log("整帧推理失败（%s），自动切换分块模式" % str(e)[:80])
                    self.tile = 768
                    out, s = self._tiled(x, h, w)
                else:
                    raise
        self.native_scale = s
        out = np.clip(out[0].transpose(1, 2, 0), 0.0, 1.0)
        return (out * 255.0 + 0.5).astype(np.uint8)

    def close(self):
        self.sess = None
