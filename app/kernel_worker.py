# -*- coding: utf-8 -*-
"""常驻加速内核 worker：在 VapourSynth 进程内做 RIFE + 超分，模型只加载一次。

由 CHEN-V 用 vrt\\python\\python.exe 启动，stdin 收 JSON 任务，stdout 回 JSON 事件。
不依赖 numpy / PIL：帧直接从 VapourSynth 缓冲写进 ffmpeg 的 rawvideo 管道。
"""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback

import vapoursynth as vs

try:
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CORE = vs.core

# 程序根目录（app 的上一级），用于定位 TensorRT 引擎缓存
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_DIR = os.path.join(ROOT, "work", "engines")


def _clean(text):
    try:
        return str(text).encode("utf-8", "replace").decode("utf-8")
    except Exception:
        return str(text)


class Cancelled(Exception):
    pass


class Y4MWriter(object):
    """把 VapourSynth 的 Y4M 输出转发给 ffmpeg，顺便按帧计数报进度。"""

    def __init__(self, pipe, w, h, total, pix, cancel, emit):
        self.pipe = pipe
        self.total = total
        self.cancel = cancel
        self.emit = emit
        self.payload = w * h * 3 if "10" in pix else w * h * 3 // 2
        self.frame_size = 6 + self.payload
        self.header_done = False
        self.hbuf = b""
        self.body = 0
        self.frames = 0
        self.t0 = time.time()

    def write(self, b):
        if self.cancel and os.path.exists(self.cancel):
            raise Cancelled()
        self.pipe.write(b)
        if not self.header_done:
            self.hbuf += b
            i = self.hbuf.find(b"\n")
            if i >= 0:
                self.header_done = True
                self.body += len(self.hbuf) - i - 1
                self.hbuf = b""
        else:
            self.body += len(b)
        n = min(self.total, self.body // self.frame_size)
        if n > self.frames:
            self.frames = n
            if n % 4 == 0 or n == self.total:
                self.emit({"ev": "progress", "current": n, "total": self.total,
                           "fps": n / max(time.time() - self.t0, 1e-6)})
        return len(b)

    def flush(self):
        try:
            self.pipe.flush()
        except Exception:
            pass

    def close(self):
        try:
            self.pipe.close()
        except Exception:
            pass



def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=True) + "\n")
    sys.stdout.flush()

def load_plugins(folder):
    names = ("vmaf.dll", "librife.dll", "lsmashsource.dll", "slv_ncnn_models.dll",
             "vsncnn.dll", "vstrt.dll")
    loaded = []
    for name in names:
        p = os.path.join(folder, name)
        if not os.path.isfile(p):
            continue
        try:
            CORE.std.LoadPlugin(p)
            loaded.append(name)
        except Exception as e:
            emit({"ev": "log", "msg": "插件加载失败 %s：%s" % (name, e)})
    return loaded


def source_clip(path, cache_dir):
    try:
        cache = os.path.join(cache_dir, "src.lwi")
        return CORE.lsmas.LWLibavSource(path, cachefile=cache, cache=1)
    except Exception:
        return CORE.lsmas.LibavSMASHSource(path)


def forward_dedup(clip, threshold):
    """真正删除相邻重复源帧，并保持选帧后的总时长不变。

    SelectEvery 默认 modify_duration=1，会把 fps 调整为 原fps * 保留数/原帧数；
    后续 RIFE 再按目标 fps 插帧，就能在原始时长内重建时间轴。
    """
    total = int(clip.num_frames)
    if threshold <= 0 or total < 3:
        return clip, total, total
    sw = min(240, int(clip.width))
    sh = max(1, int(round(int(clip.height) * sw / float(max(int(clip.width), 1)))))
    scan = CORE.resize.Bicubic(clip, width=sw, height=sh, format=vs.GRAY8,
                               matrix_in_s="709", matrix_s="709", range_in_s="limited")

    def plane(frame):
        return ctypes.string_at(frame.get_read_ptr(0), frame.get_stride(0) * sh)

    first = scan.get_frame(0)
    stride = first.get_stride(0)
    prev = plane(first)
    kept = [0]
    for n in range(1, total):
        cur = plane(scan.get_frame(n))
        acc = 0
        for y in range(sh):
            a = prev[y * stride:y * stride + sw]
            b = cur[y * stride:y * stride + sw]
            acc += sum(abs(p - q) for p, q in zip(a, b))
        if acc / float(sw * sh) >= threshold:
            kept.append(n)
            prev = cur
    if len(kept) < 2:
        return clip, total, total
    return CORE.std.SelectEvery(clip, cycle=total, offsets=kept), total, len(kept)


def frame_bytes(frame):
    h = frame.height
    for p in range(frame.format.num_planes):
        ph = h >> (frame.format.subsampling_h if p else 0)
        stride = frame.get_stride(p)
        yield ctypes.string_at(frame.get_read_ptr(p), stride * ph)


PLUGIN_DIR = ""


def _load_vsmlrt():
    """导入 vs-mlrt 自带的 vsmlrt.py（GPL-3.0，单独放在插件目录，不与主程序代码混布）。"""
    if PLUGIN_DIR and PLUGIN_DIR not in sys.path:
        sys.path.insert(0, PLUGIN_DIR)
    import vsmlrt
    # trtexec 与 TensorRT 运行库同放 python.exe 目录，DLL 依赖自然能找到
    for cand in (os.path.join(os.path.dirname(sys.executable), "trtexec.exe"),
                 os.path.join(PLUGIN_DIR, "vsmlrt-cuda", "trtexec.exe")):
        if os.path.isfile(cand):
            vsmlrt.trtexec_path = cand
            break
    return vsmlrt


def _trt_clip(clip, sr, log):
    """TensorRT 超分。

    TensorRT 引擎与 GPU 架构、TensorRT 版本、模型指纹绑定，不能跨机器复用，
    因此引擎缓存在本机 work/engines 下：首次按「模型 + 分块尺寸 + 精度」构建
    （几分钟），之后同配置直接加载，秒开。
    """
    if not hasattr(CORE, "trt"):
        raise RuntimeError("vstrt 插件未加载（缺少 vstrt.dll 或 TensorRT 运行库）")
    vsmlrt = _load_vsmlrt()
    w, h = int(clip.width), int(clip.height)
    tile = int(sr.get("tile", 160) or 160)
    # 分块尺寸必须小于画面，否则插件直接崩（与 vsncnn 同样的边界问题）
    if tile <= 0 or tile >= w or tile >= h:
        tile = 0
    shape = (tile, tile) if tile else (w, h)
    fp16 = bool(int(sr.get("fp16", 0)))
    os.makedirs(ENGINE_DIR, exist_ok=True)
    log("TensorRT：%s（%s，%d×%d 分块）" % (
        os.path.basename(str(sr.get("param", ""))),
        "fp16" if fp16 else "fp32", shape[0], shape[1]))
    t0 = time.time()
    engine = vsmlrt.trtexec(
        sr["param"], channels=3,
        opt_shapes=shape, max_shapes=shape, min_shapes=shape,
        fp16=fp16, device_id=int(sr.get("gpu", 0)),
        static_shape=True, input_format=0, output_format=0,
        engine_folder=ENGINE_DIR, log=False,
    )
    log("TensorRT：引擎就绪，用时 %.1fs（缓存于 work/engines）" % (time.time() - t0))
    # 实测（1080p / CUGAN 2x / RTX 5060 Laptop）：分块 160 + 2 流 + CUDA Graph 最快，
    # 约 0.19s/帧（ncnn 同参数 0.55s/帧）；分块 256/320 反而更慢（块少但单块更大，占用上升）。
    kw = dict(device_id=int(sr.get("gpu", 0)), num_streams=2, verbosity=2)
    if tile:
        kw["tilesize"] = tile
    try:
        return CORE.trt.Model(clip, engine, use_cuda_graph=True, **kw)
    except Exception:
        return CORE.trt.Model(clip, engine, **kw)



def process(cmd):
    input_path = cmd["input"]
    output = cmd["output"]
    image_seq = bool(cmd.get("image_seq"))
    cancel_file = cmd.get("cancel") or ""
    tmpdir = cmd.get("tmp") or tempfile.mkdtemp(prefix="vsw_")
    os.makedirs(tmpdir, exist_ok=True)

    clip = source_clip(input_path, tmpdir)
    src_fps_num, src_fps_den = clip.fps_num, clip.fps_den
    if not src_fps_num or not src_fps_den:
        src_fps_num, src_fps_den = 24, 1

    start = float(cmd.get("start") or 0)
    duration = float(cmd.get("duration") or 0)
    if start > 0 or duration > 0:
        first = max(0, int(round(start * src_fps_num / float(src_fps_den))))
        if duration > 0:
            last = first + max(1, int(round(duration * src_fps_num / float(src_fps_den)))) - 1
            last = min(last, clip.num_frames - 1)
        else:
            last = clip.num_frames - 1
        clip = CORE.std.Trim(clip, first=first, last=last)

    clip = CORE.resize.Bicubic(clip, format=vs.RGBS,
                               matrix_in_s="709", transfer_in_s="709",
                               primaries_in_s="709", range_in_s="limited")

    # 可选的工作分辨率：先降到较小尺寸再做补帧/超分，之后由末尾的目标尺寸缩放收口。
    # 对"源分辨率远大于输出分辨率"的素材能省掉大量无效算力。
    pre_w, pre_h = int(cmd.get("pre_w") or 0), int(cmd.get("pre_h") or 0)
    if pre_w > 0 and pre_h > 0 and (pre_w != int(clip.width) or pre_h != int(clip.height)):
        emit({"ev": "log", "msg": "工作分辨率：%d×%d -> %d×%d（处理后再输出到目标尺寸）" % (
            clip.width, clip.height, pre_w, pre_h)})
        clip = CORE.resize.Lanczos(clip, width=pre_w, height=pre_h)

    vfi = cmd.get("vfi")
    sr = cmd.get("sr")
    tw, th = int(cmd.get("target_w") or 0), int(cmd.get("target_h") or 0)
    k = (int(sr.get("scale", 2)) or 2) if sr else 2

    def _apply_vfi(c):
        kw = dict(model_path=vfi["model"], gpu_id=int(vfi.get("gpu", 0)))
        if vfi.get("fps_num"):
            kw.update(fps_num=int(vfi["fps_num"]), fps_den=int(vfi.get("fps_den", 1)))
        else:
            kw.update(factor_num=int(vfi.get("factor_num", 2)),
                      factor_den=int(vfi.get("factor_den", 1)))
        if vfi.get("scene"):
            kw["sc"] = 1
        return CORE.rife.RIFE(c, **kw)

    def _apply_sr(c):
        emit({"ev": "log", "msg": "超分 %d×：%d×%d -> %d×%d" % (
            k, c.width, c.height, c.width * k, c.height * k)})
        sr_kind = sr.get("kind", "ncnn")
        if sr_kind == "onnx":
            if sr.get("use_trt"):
                try:
                    return _trt_clip(
                        c, sr, lambda s: emit({"ev": "log", "msg": s}))
                except Exception as e:
                    emit({"ev": "log", "msg": "TensorRT 不可用（%s），本次回退 ncnn 内核" % e})
            # vsncnn：直接吃 ONNX（on-the-fly 转 ncnn），支持 Real-CUGAN / AnimeJaNai 等
            use_fp16 = int(sr.get("fp16", 0))
            # AnimeJaNai 系列 fp16 会输出 NaN（已知问题），强制回退 fp32 保安全
            _pn = os.path.basename(str(sr.get("param", ""))).lower()
            if use_fp16 and "animejanai" in _pn:
                use_fp16 = 0
                emit({"ev": "log", "msg": "该模型 fp16 不稳定，已自动回退 fp32（画质优先）"})
            kw = dict(clips=c, network_path=sr["param"],
                      device_id=int(sr.get("gpu", 0)),
                      fp16=use_fp16)
            # vsncnn 的 tilesize 有边界 bug：当 tile 尺寸 >= 输入帧的宽或高时，
            # 会在 onnx 分块阶段段错误崩溃（旧版/新版均有）。这里只在 tile 严格
            # 小于输入宽高时才传 tilesize，否则交给 vsncnn 用完整帧尺寸，避免崩溃。
            _tile = int(sr.get("tile", 160) or 160)
            if _tile > 0 and _tile < int(c.width) and _tile < int(c.height):
                kw["tilesize"] = _tile
            if sr.get("overlap"):
                kw["overlap"] = int(sr["overlap"])
            return CORE.ncnn.Model(**kw)
        # slvncnn：吃 ncnn .param（Real-ESRGAN 系列）
        return CORE.slvncnn.NativeModel(
            c, model_path=sr["param"], scale=int(sr.get("scale", 2)),
            tile=int(sr.get("tile", 256) or 256), device_id=int(sr.get("gpu", 0)))

    # 消重永远在源帧上做（帧数最少、最便宜），与超分/补帧的先后无关
    if vfi and vfi.get("dedup"):
        n_before = int(clip.num_frames)
        clip, n_total, n_kept = forward_dedup(
            clip, float(vfi.get("dup_thr", 0.25)))
        emit({"ev": "log", "msg": "前进消重：%d 帧 -> %d 张（丢弃 %d 帧，阈值 %.2f）" % (
            n_total, n_kept, n_total - n_kept, float(vfi.get("dup_thr", 0.25)))})
        if n_kept == n_before:
            emit({"ev": "log", "msg": "前进消重：没有检测到低于阈值的重复帧"})

    # 处理顺序：
    #   sr_first=True  → 先超分再补帧（SVFI 的做法）。超分只跑源帧（如 24fps），
    #                    补帧在清晰的高分辨率帧上做，光流更准、成本更低。
    #   sr_first=False → 先补帧再超分（原行为）。超分要跑全部插帧后（如 120fps），
    #                    帧数被放大 5 倍，最贵的超分被做了 5 遍。
    if cmd.get("sr_first") and vfi and sr:
        emit({"ev": "log", "msg": "处理顺序：先超分 → 缩放 → 再补帧（更快）"})
        clip = _apply_sr(clip)
        # 关键：超分后先把画面缩到目标尺寸，再补帧。
        # 补帧成本与像素数成正比，在 2160p 上补帧比在 1080p 上贵 4 倍。
        if tw > 0 and th > 0 and (tw != int(clip.width) or th != int(clip.height)):
            clip = CORE.resize.Lanczos(clip, width=tw, height=th)
        clip = _apply_vfi(clip)
    else:
        if vfi:
            clip = _apply_vfi(clip)
        if sr:
            clip = _apply_sr(clip)

    if tw > 0 and th > 0 and (tw != int(clip.width) or th != int(clip.height)):
        # 缩回目标尺寸：用 Lanczos 高质量核（避免 Bicubic 造成的发糊）
        clip = CORE.resize.Lanczos(clip, width=tw, height=th)

    out_pix = cmd.get("out_pix") or "yuv420p10le"
    fmt = vs.YUV420P10 if "10" in out_pix else vs.YUV420P8
    # 色彩空间转换 + 色度下采样：保持 Bicubic（仅转换，不做尺寸缩放）
    clip = CORE.resize.Bicubic(clip, format=fmt, matrix_s="709", range_s="limited")

    total = clip.num_frames
    w, h = clip.width, clip.height
    fps_num, fps_den = clip.fps_num, clip.fps_den
    emit({"ev": "info", "width": w, "height": h, "frames": total,
          "fps_num": fps_num, "fps_den": fps_den})

    ffmpeg = cmd["ffmpeg"]
    codec = cmd["codec"]
    codec_args = list(cmd.get("codec_args") or [])
    audio = bool(cmd.get("audio", True)) and not image_seq
    if image_seq:
        out_path = output
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    else:
        root, ext = os.path.splitext(output)
        out_path = root + ".part" + (ext or ".mp4")

    args = [ffmpeg, "-v", "error", "-y", "-nostdin",
            "-f", "yuv4mpegpipe", "-i", "pipe:0"]
    if audio:
        args += ["-i", input_path, "-map", "0:v:0", "-map", "1:a?"]
    else:
        args += ["-map", "0:v:0"]
    args += ["-c:v", codec] + codec_args
    if image_seq:
        args += ["-f", "image2", "-start_number", "1", out_path]
    else:
        if audio:
            args += ["-c:a", "copy"]
        args.append(out_path)

    err = tempfile.TemporaryFile()
    _ff_kw = {}
    if os.name == "nt":
        _si = subprocess.STARTUPINFO()
        _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        _si.wShowWindow = 0
        _ff_kw = {"creationflags": 0x08000000, "startupinfo": _si}
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stderr=err, **_ff_kw)
    writer = Y4MWriter(proc.stdin, w, h, total, out_pix, cancel_file, emit)
    t0 = time.time()
    try:
        clip.output(writer, y4m=True)
        writer.flush()
        proc.stdin.close()
    except Cancelled:
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.kill()
        proc.wait()
        _cleanup(output, image_seq, out_path)
        emit({"ev": "cancelled"})
        return
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        _cleanup(output, image_seq, out_path)
        raise
    code = proc.wait()
    if code != 0:
        err.seek(0)
        tail = err.read().decode("utf-8", "replace")[-1200:]
        _cleanup(output, image_seq, out_path)
        raise RuntimeError("ffmpeg 退出码 %s：%s" % (code, tail.strip()))
    if not image_seq:
        try:
            if os.path.exists(output):
                os.remove(output)
            os.replace(out_path, output)
        except Exception:
            pass
    emit({"ev": "done", "output": output, "frames": total})


def _cleanup(output, image_seq, part=None):
    try:
        if image_seq:
            import shutil
            shutil.rmtree(os.path.dirname(output), ignore_errors=True)
        else:
            for p in (output, part or (output + ".part")):
                if p and os.path.exists(p):
                    os.remove(p)
    except Exception:
        pass


def main():
    global PLUGIN_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugins", required=True)
    a = ap.parse_args()
    PLUGIN_DIR = a.plugins
    loaded = load_plugins(a.plugins)
    emit({"ev": "ready", "plugins": loaded})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
        except Exception as e:
            emit({"ev": "log", "msg": "bad json: %s" % e})
            continue
        if cmd.get("cmd") == "quit":
            break
        if cmd.get("cmd") != "run":
            continue
        try:
            process(cmd)
        except Exception as e:
            emit({"ev": "error", "msg": str(e), "trace": traceback.format_exc()[-1500:]})


if __name__ == "__main__":
    main()
