# -*- coding: utf-8 -*-
"""内置加速内核：启动一次运行时（vrt）的 Python worker，之后每个视频只发任务，不再重起引擎。"""
import json
import os
import queue
import subprocess
import threading
import time

import paths
import procutil
import video as vd


def _clean(text):
    try:
        return str(text).encode("utf-8", "replace").decode("utf-8")
    except Exception:
        return str(text)

VS_PY = os.path.join(paths.ROOT, "vrt", "python", "python.exe")
VS_PLUGINS = os.path.join(paths.ROOT, "vrt", "plugins")
WORKER = os.path.join(paths.APP_DIR, "kernel_worker.py")


class Cancelled(Exception):
    pass


def _plug_ok(d):
    return all(os.path.isfile(os.path.join(d, n)) for n in
               ("librife.dll", "lsmashsource.dll", "slv_ncnn_models.dll", "vsncnn.dll"))


def has_vmaf():
    return os.path.isfile(os.path.join(VS_PLUGINS, "vmaf.dll"))


def has_nvidia():
    """本机是不是 NVIDIA 显卡（探测没跑起来时按 True 处理，退回旧行为）。"""
    try:
        import envprobe
        return envprobe.has_nvidia(default=True)
    except Exception:
        return True


def _trt_libs_ok():
    """vstrt.dll 与它依赖的 TensorRT / CUDA 运行库是否齐全。"""
    if not os.path.isfile(os.path.join(VS_PLUGINS, "vstrt.dll")):
        return False
    for d in (os.path.join(VS_PLUGINS, "vsmlrt-cuda"), VS_PLUGINS,
              os.path.dirname(VS_PY)):
        if any(os.path.isfile(os.path.join(d, n))
               for n in ("nvinfer_10.dll", "nvinfer.dll")):
            return True
    return False


def _trt_dirs():
    return (os.path.join(VS_PLUGINS, "vsmlrt-cuda"), VS_PLUGINS)


def _trt_resource_ok():
    """当前显卡架构的 builder resource 是否在包里。

    TensorRT 10.16 起把构建资源按架构拆成了独立 DLL
    （nvinfer_builder_resource_sm86_10.dll 这种，单个 100~430MB），
    缺了当前架构那一份，第一次构建引擎就会失败（虽有 ptx 资源可兜底 JIT，
    但包里不一定有）。架构拿不到时不阻拦，交给运行时自己回退。
    """
    for d in _trt_dirs():
        if os.path.isfile(os.path.join(d, "nvinfer_builder_resource_ptx_10.dll")):
            return True
    try:
        import envprobe
        cap = envprobe.compute_cap()
    except Exception:
        cap = None
    if not cap:
        return True
    try:
        tag = int(round(float(cap) * 10))
    except Exception:
        return True
    name = "nvinfer_builder_resource_sm%d_10.dll" % tag
    return any(os.path.isfile(os.path.join(d, name)) for d in _trt_dirs())


def trt_status():
    """(能不能用, 原因) —— 原因是 None / "no_nvidia" / "no_libs" / "no_resource"。

    界面按原因显示不同提示，用户才知道到底缺什么（而不是笼统地「不可用」）。
    """
    if not has_nvidia():
        return False, "no_nvidia"
    if not _trt_libs_ok():
        return False, "no_libs"
    if not _trt_resource_ok():
        return False, "no_resource"
    return True, None


def has_trt():
    """TensorRT 加速后端是否可用。

    文件布局（与 vs-mlrt 官方包一致）：vstrt.dll 在 plugins 目录，
    它依赖的 TensorRT / CUDA 运行库在 plugins/vsmlrt-cuda/ 下（含 trtexec.exe）。

    光有文件不够——打包发给别人时这些 DLL 是跟着走的，但对方可能压根没有
    NVIDIA 显卡（或者驱动太旧，nvidia-smi 都报不出来），也可能只是没带他那块卡
    对应架构的 builder resource。三项都算进来，界面上就不会出现「勾得上、跑起来
    却回退 ncnn」的假可用状态。
    """
    return trt_status()[0]


def available():
    return os.path.isfile(WORKER) and os.path.isfile(VS_PY) and _plug_ok(VS_PLUGINS)


def _paths():
    return VS_PY, VS_PLUGINS


def _infer_scale(name):
    """从模型文件名精确推断超分倍率（避免 denoise3x 里的 3x 干扰）。"""
    import re
    base = os.path.basename(name).lower()
    # 优先匹配 up{N}x- 前缀（Real-CUGAN：up2x-latest-... / up3x-latest-... / up4x-latest-...）
    m = re.search(r"(?:^|[-_])up(\d)x(?:[-_]|$)", base)
    if m:
        return int(m.group(1))
    # 再匹配 {N}x_ 前缀（AnimeJaNai：2x_AnimeJaNai...）
    m = re.search(r"(?:^|[-_])(\d)x[_]", base)
    if m:
        return int(m.group(1))
    # 再匹配 x{N} 结尾（realesr-animevideov3-x4 / x4plus 等）
    m = re.search(r"x(\d)(?:plus)?(?:\.onnx|\.param|$)", base)
    if m:
        return int(m.group(1))
    return 2


def sr_param(label):
    """把超分模型映射到内核能用的 spec。

    - (kind, model) 元组：kind='onnx' -> {"kind":"onnx","param":onnx路径,"scale":N}
                          kind='realesr'/'waifu2x' -> {"kind":"ncnn","param":.param路径,"scale":N}
    - 旧的中文/带后缀显示名：内部再查一次 ncnn 模型
    - 直接的 .onnx 文件路径：按文件名推断 scale，返回 onnx spec
    """
    kind = None
    model = None
    if isinstance(label, (tuple, list)):
        if len(label) == 2:
            kind, model = label
    elif isinstance(label, str) and label.lower().endswith(".onnx") and os.path.isfile(label):
        # 直接给了 ONNX 文件路径
        return {"kind": "onnx", "param": label, "scale": _infer_scale(label)}
    else:
        try:
            import sr_ncnn
            info = sr_ncnn.list_ncnn_sr().get(label)
        except Exception:
            info = None
        if not info:
            return None
        kind, model = info
    if kind == "onnx":
        # onnx 超分模型：model 是 .onnx 文件路径
        p = model if (isinstance(model, str) and model.lower().endswith(".onnx")) else None
        if not p or not os.path.isfile(p):
            return None
        return {"kind": "onnx", "param": p, "scale": _infer_scale(p)}
    if kind == "realesr":
        # model 三种情况：
        #   1) 绝对 .param 路径（SVFI 模型）—— 直接使用
        #   2) "<dir>/<x>"（Real-CUGAN ncnn 版：一个目录装多个 .param）
        #   3) "<m>"（常规单模型目录）
        if isinstance(model, str) and model.lower().endswith(".param") and os.path.isfile(model):
            p = model
        elif isinstance(model, str) and "/" in model:
            p = os.path.join(paths.MODELS, "sr_ncnn", "ncnnRealESR", "models",
                             model + ".param")
        else:
            p = os.path.join(paths.MODELS, "sr_ncnn", "ncnnRealESR", "models",
                             model, model + ".param")
    else:
        root = os.path.join(paths.MODELS, "sr_ncnn", "waifu2x", "models", model)
        p = os.path.join(root, model + ".param")
        if not os.path.isfile(p):
            try:
                cand = [f for f in os.listdir(root) if f.endswith(".param")]
                p = os.path.join(root, sorted(cand)[0]) if cand else p
            except Exception:
                pass
    if not os.path.isfile(p):
        return None
    scale = _infer_scale(model if model else p)
    return {"kind": "ncnn", "param": p, "scale": scale}


def codec_args(encoder, rate_mode, crf, bitrate, preset, turbo, out_pix, image_seq, fmt):
    if image_seq:
        if fmt == "JPG":
            return ["-c:v", "mjpeg", "-q:v", "2", "-pix_fmt", "yuvj420p"]
        if fmt == "WEBP":
            return ["-c:v", "libwebp", "-quality", "95", "-pix_fmt", "yuv420p"]
        return ["-c:v", "png", "-pix_fmt", "rgb24", "-compression_level", "3"]
    codec, pix, family = vd.ENCODERS.get(encoder) or vd.ENCODERS["H265"]
    args = ["-pix_fmt", out_pix]
    if family == "nvenc":
        args += ["-preset", "p1" if turbo else ("p3" if preset in ("fast", "medium") else "p5"),
                 "-tune", "hq", "-rc", "vbr"]
        if rate_mode == "bitrate":
            k = max(int(bitrate * 1000), 100)
            args += ["-b:v", "%dk" % k, "-maxrate", "%dk" % int(k * 1.5),
                     "-bufsize", "%dk" % (k * 2)]
        else:
            args += ["-cq", str(crf), "-b:v", "0"]
    elif family == "amf":
        args += ["-quality", "speed" if turbo else
                 {"fast": "speed", "medium": "speed", "balanced": "balanced",
                  "slow": "quality"}.get(preset, "balanced")]
        if rate_mode == "bitrate":
            k = max(int(bitrate * 1000), 100)
            args += ["-rc", "vbr_peak", "-b:v", "%dk" % k,
                     "-maxrate", "%dk" % int(k * 1.5), "-bufsize", "%dk" % (k * 2)]
        else:
            qp = str(vd._amf_qp(codec, crf))
            args += ["-rc", "cqp", "-qp_i", qp, "-qp_p", qp]
            if codec == "h264_amf":
                args += ["-qp_b", qp]
    elif family == "qsv":
        if rate_mode == "bitrate":
            k = max(int(bitrate * 1000), 100)
            args += ["-b:v", "%dk" % k, "-maxrate", "%dk" % int(k * 1.5),
                     "-bufsize", "%dk" % (k * 2)]
        else:
            args += ["-global_quality", str(crf)]
    elif family == "svtav1":
        args += ["-preset", "8"]
        if rate_mode == "bitrate":
            args += ["-b:v", "%dk" % max(int(bitrate * 1000), 100)]
        else:
            args += ["-crf", str(crf)]
    elif family == "aom":
        args += ["-cpu-used", "6"]
        if rate_mode == "bitrate":
            args += ["-b:v", "%dk" % max(int(bitrate * 1000), 100)]
        else:
            args += ["-crf", str(crf), "-b:v", "0"]
    elif family == "vp9":
        if rate_mode == "bitrate":
            args += ["-b:v", "%dk" % max(int(bitrate * 1000), 100)]
        else:
            args += ["-crf", str(crf), "-b:v", "0"]
    else:
        xp = {"fast": "medium", "medium": "medium", "balanced": "slow",
              "slow": "slow"}.get(preset, "slow")
        args += ["-preset", xp]
        if rate_mode == "bitrate":
            k = max(int(bitrate * 1000), 100)
            args += ["-b:v", "%dk" % k, "-maxrate", "%dk" % int(k * 1.5),
                     "-bufsize", "%dk" % (k * 2)]
        elif family == "x265":
            args += ["-crf", str(crf), "-x265-params", "log-level=error"]
        else:
            args += ["-crf", str(crf)]
    if family == "x265":
        args += ["-tag:v", "hvc1"]
    return args


class KernelBackend(object):
    def __init__(self):
        self.proc = None
        self.q = None
        self.lock = threading.Lock()
        self.tmp = None

    def _reader(self, proc, q):
        try:
            for line in proc.stdout:
                q.put(line)
        except Exception:
            pass
        q.put(None)

    def _start(self):
        if self.proc and self.proc.poll() is None:
            return
        py, plugins = _paths()
        self.q = queue.Queue()
        self.proc = procutil.popen(
            [py, WORKER, "--plugins", plugins],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
            cwd=paths.APP_DIR)
        threading.Thread(target=self._reader, args=(self.proc, self.q), daemon=True).start()
        try:
            line = self.q.get(timeout=30)
        except queue.Empty:
            self.stop()
            raise RuntimeError("加速内核启动超时")
        if not line:
            self.stop()
            raise RuntimeError("加速内核启动失败")
        try:
            ev = json.loads(line)
        except Exception:
            self.stop()
            raise RuntimeError("加速内核启动返回异常：%s" % line[:200])
        if ev.get("ev") != "ready":
            self.stop()
            raise RuntimeError("加速内核未就绪：%s" % ev)

    def run_video(self, spec, progress=None, log=None, cancel_event=None):
        progress = progress or (lambda cur, total, fps: None)
        log = log or (lambda s: None)
        with self.lock:
            self._start()
            cancel = spec.get("cancel") or ""
            if cancel and os.path.exists(cancel):
                os.remove(cancel)
            if cancel_event is not None and cancel_event.is_set():
                raise Cancelled()
            cmd = dict(spec)
            cmd["cmd"] = "run"
            try:
                self.proc.stdin.write(json.dumps(cmd, ensure_ascii=True) + "\n")
                self.proc.stdin.flush()
            except Exception as e:
                self.stop()
                raise RuntimeError("加速内核写入失败：%s" % e)
            info = {}
            t0 = time.time()
            while True:
                if cancel_event is not None and cancel_event.is_set() and cancel:
                    try:
                        open(cancel, "w").close()
                    except Exception:
                        pass
                try:
                    line = self.q.get(timeout=1.0)
                except queue.Empty:
                    if self.proc.poll() is not None:
                        self.stop()
                        raise RuntimeError("加速内核已退出")
                    continue
                if line is None:
                    self.stop()
                    raise RuntimeError("加速内核连接断开")
                try:
                    ev = json.loads(line)
                except Exception:
                    log(_clean(line.rstrip()))
                    continue
                kind = ev.get("ev")
                if kind == "info":
                    info.update(ev)
                elif kind == "progress":
                    progress(int(ev.get("current", 0)), int(ev.get("total", 0)),
                             float(ev.get("fps", 0) or 0))
                elif kind == "log":
                    log(_clean(ev.get("msg", "")))
                elif kind == "done":
                    info.update(ev)
                    info["elapsed"] = time.time() - t0
                    if cancel and os.path.exists(cancel):
                        try:
                            os.remove(cancel)
                        except Exception:
                            pass
                    return info
                elif kind == "cancelled":
                    raise Cancelled()
                elif kind == "error":
                    raise RuntimeError(_clean(ev.get("msg") or "加速内核处理失败"))

    def stop(self):
        p = self.proc
        self.proc = None
        if not p:
            return
        try:
            if p.poll() is None:
                p.stdin.write('{"cmd":"quit"}\n')
                p.stdin.flush()
        except Exception:
            pass
        try:
            p.wait(timeout=2)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass


BACKEND = KernelBackend()
