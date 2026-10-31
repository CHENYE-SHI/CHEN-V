# -*- coding: utf-8 -*-
"""ffmpeg 封装：探测元数据、逐帧读取、逐帧写入（视频编码 / PNG·JPG·WEBP 图片序列）。"""
import procutil
import os
import re
import subprocess


class ProbeError(RuntimeError):
    pass


def probe(ffmpeg, path):
    """用 ffmpeg -i 的 stderr 解析元数据（不依赖 ffprobe）"""
    p = procutil.run([ffmpeg, "-hide_banner", "-i", path],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    txt = p.stderr or ""
    if "Video:" not in txt:
        raise ProbeError("无法识别的视频文件：%s" % os.path.basename(path))
    m = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", txt)
    if not m:
        raise ProbeError("无法解析分辨率")
    w, h = int(m.group(1)), int(m.group(2))
    fps = 24.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*fps", txt)
    if m:
        fps = float(m.group(1))
    else:
        m = re.search(r"(\d+(?:\.\d+)?)\s*tbr", txt)
        if m:
            fps = float(m.group(1))
    dur = 0.0
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", txt)
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    frames = 0
    m = re.search(r"(\d+)\s*frames", txt)
    if m:
        frames = int(m.group(1))
    if not frames and dur > 0:
        frames = int(round(dur * fps))
    return {
        "width": w, "height": h, "fps": fps, "duration": dur,
        "frames": max(frames, 0), "has_audio": "Audio:" in txt, "raw": txt,
    }


def _range_args(start=None, duration=None):
    a = []
    if start and start > 0:
        a += ["-ss", "%.3f" % start]
    if duration and duration > 0:
        a += ["-t", "%.3f" % duration]
    return a


class FrameReader(object):
    """视频/图片序列 -> rgb24 裸流"""

    def __init__(self, ffmpeg, path, w, h, hwdecode=False, start=None, duration=None,
                 start_number=None, pattern=None):
        self.w, self.h = w, h
        self.frame_bytes = w * h * 3
        cmd = [ffmpeg, "-v", "error", "-nostdin"]
        if hwdecode and pattern is None:
            cmd += ["-hwaccel", "auto"]
        cmd += _range_args(start, duration)
        if pattern:
            cmd += ["-start_number", str(start_number or 1), "-i", pattern]
        else:
            cmd += ["-i", path, "-map", "0:v:0"]
        # 逐帧管线：不要按 CFR 补帧/丢帧，解码出多少帧就读多少帧
        cmd += ["-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.proc = procutil.popen(cmd, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, bufsize=self.frame_bytes * 16)

    def read(self):
        import numpy as np
        buf = self.proc.stdout.read(self.frame_bytes)
        if not buf or len(buf) < self.frame_bytes:
            return None
        return np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)

    def close(self):
        for fn in (lambda: self.proc.stdout.close(), lambda: self.proc.kill()):
            try:
                fn()
            except Exception:
                pass


# 编码器菜单：显示名 -> (编码器, 像素格式, 参数家族)
# 像素格式按各家硬编的原生格式给（NVENC=yuv420p，AMF/QSV=nv12/p010le），
# 少一层 swscale 转换，也避开 QSV 不收 yuv420p 的问题。
ENCODERS = {
    # NVIDIA NVENC
    "H264 NVENC": ("h264_nvenc", "yuv420p", "nvenc"),
    "H265 NVENC": ("hevc_nvenc", "yuv420p", "nvenc"),
    "H265 10bit NVENC": ("hevc_nvenc", "yuv420p10le", "nvenc"),
    "AV1 NVENC": ("av1_nvenc", "yuv420p", "nvenc"),
    # AMD AMF
    "H264 AMF": ("h264_amf", "nv12", "amf"),
    "H265 AMF": ("hevc_amf", "nv12", "amf"),
    "H265 10bit AMF": ("hevc_amf", "p010le", "amf"),
    "AV1 AMF": ("av1_amf", "nv12", "amf"),
    # Intel QSV
    "H264 QSV": ("h264_qsv", "nv12", "qsv"),
    "H265 QSV": ("hevc_qsv", "nv12", "qsv"),
    "H265 10bit QSV": ("hevc_qsv", "p010le", "qsv"),
    "AV1 QSV": ("av1_qsv", "nv12", "qsv"),
    # 软件编码（任何机器都能跑，作兜底）
    "H264": ("libx264", "yuv420p", "x264"),
    "H265": ("libx265", "yuv420p", "x265"),
    "H265 10bit": ("libx265", "yuv420p10le", "x265"),
    "VP9": ("libvpx-vp9", "yuv420p", "vp9"),
    "AV1 (SVT-AV1)": ("libsvtav1", "yuv420p", "svtav1"),
    "AV1 (libaom)": ("libaom-av1", "yuv420p", "aom"),
}

# 参数家族 -> 依赖的显卡厂商（不在表里的是纯软件编码）
ENC_VENDOR = {"nvenc": "nvidia", "amf": "amd", "qsv": "intel"}


def _amf_qp(codec, crf):
    """把 CRF 换算成 AMF 的 QP。

    H.264/H.265 的 QP 与 x264 CRF 同为 0~51 尺度，可直接用；AV1 的 QP 是
    0~255 尺度，按 4 倍换算（CRF 20 ≈ QP 80，与 libaom 的观感大致对齐）。
    """
    try:
        q = int(round(float(crf)))
    except Exception:
        q = 20
    if codec == "av1_amf":
        return max(0, min(q * 4, 255))
    return max(0, min(q, 51))


def default_encoder(names):
    """从可用列表里挑一个默认档：优先 10bit 硬编，其次硬编 H265/H264，最后软编。

    列表已经按本机显卡过滤过，所以 A 卡机器上不会挑出 NVENC——这里的顺序
    只是同一台机器上的优先级。
    """
    for pref in ("H265 10bit NVENC", "H265 10bit AMF", "H265 10bit QSV",
                 "H265 NVENC", "H265 AMF", "H265 QSV",
                 "H264 NVENC", "H264 AMF", "H264 QSV",
                 "H265 10bit", "H265"):
        if pref in names:
            return pref
    return names[0] if names else "H265"

# 输出格式：视频容器（显示名 -> 扩展名）
VIDEO_FORMATS = {"MP4": ".mp4", "MKV": ".mkv", "MOV": ".mov",
                 "GIF": ".gif", "WEBP": ".webp"}

# 输出格式：图片序列（显示名 -> (扩展名, ffmpeg 编码参数)），走 image2 复用器
IMAGE_FORMATS = {
    "PNG": (".png", ["-c:v", "png", "-pix_fmt", "rgb24", "-compression_level", "3"]),
    "JPG": (".jpg", ["-c:v", "mjpeg", "-q:v", "2", "-pix_fmt", "yuvj420p"]),
    "WEBP": (".webp", ["-c:v", "libwebp", "-quality", "95", "-pix_fmt", "yuv420p"]),
}


def is_image_format(fmt):
    return str(fmt or "").strip().upper() in IMAGE_FORMATS


def image_pattern(dir_path, fmt):
    """图片序列的输出通配符：<目录>/frame_%08d.<ext>"""
    fmt = str(fmt or "").strip().upper()
    return os.path.join(dir_path, "frame_%08d" + IMAGE_FORMATS[fmt][0])


class FrameWriter(object):
    """逐帧写出：默认编码成视频；image_fmt 给定时写成图片序列（PNG / JPG / WEBP）。"""

    def __init__(self, ffmpeg, out_path, w, h, fps, src_path=None,
                 encoder="H265 NVENC", crf=16, preset="balanced", rate_mode="crf",
                 bitrate=20, turbo=False, log=print, start=None, duration=None, scale_to=None,
                 image_fmt=None):
        self.log = log
        self.w, self.h = w, h
        self.image_fmt = str(image_fmt or "").strip().upper() or None
        cmd = [ffmpeg, "-v", "error", "-nostdin", "-y",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (w, h),
               "-r", ("%.6f" % fps).rstrip("0").rstrip("."), "-i", "pipe:0"]
        if self.image_fmt:
            if self.image_fmt not in IMAGE_FORMATS:
                raise ValueError("未知图片格式：%s" % image_fmt)
            if scale_to:
                cmd += ["-vf", "scale=%d:%d:flags=lanczos" % (int(scale_to[0]), int(scale_to[1]))]
            cmd += list(IMAGE_FORMATS[self.image_fmt][1])
            # image2 复用器按 out_path 里的 %08d 编号落盘，没有音轨
            cmd += ["-f", "image2", "-start_number", "1", out_path]
        else:
            # 名字对不上时退回软件编码：硬编兜底会在没有该显卡的机器上直接失败，
            # 软编至少能出片（这种情形只出现在设置文件从别的机器带过来）
            codec, pix_fmt, family = ENCODERS.get(encoder) or ENCODERS["H265"]
            if src_path and os.path.isfile(src_path):
                cmd += _range_args(start, duration) + ["-i", src_path]
            cmd += ["-map", "0:v:0"]
            if src_path and os.path.isfile(src_path):
                cmd += ["-map", "1:a?"]
            if scale_to:
                cmd += ["-vf", "scale=%d:%d:flags=lanczos" % (int(scale_to[0]), int(scale_to[1]))]
            cmd += ["-c:v", codec, "-pix_fmt", pix_fmt]

            if family == "nvenc":
                cmd += ["-preset", "p1" if turbo else ("p3" if preset in ("fast", "medium") else "p5")]
                cmd += ["-tune", "hq", "-rc", "vbr"]
                if rate_mode == "bitrate":
                    k = max(int(bitrate * 1000), 100)
                    cmd += ["-b:v", "%dk" % k, "-maxrate", "%dk" % int(k * 1.5), "-bufsize", "%dk" % (k * 2)]
                else:
                    cmd += ["-cq", str(crf), "-b:v", "0"]
            elif family == "amf":
                # AMF 没有 NVENC 那套 p1~p7/tune，质量档只有 quality|balanced|speed；
                # 恒定质量走 cqp + 逐帧 QP（B 帧只有 H.264 有）
                cmd += ["-quality", "speed" if turbo else
                        {"fast": "speed", "medium": "speed", "balanced": "balanced",
                         "slow": "quality"}.get(preset, "balanced")]
                if rate_mode == "bitrate":
                    k = max(int(bitrate * 1000), 100)
                    cmd += ["-rc", "vbr_peak", "-b:v", "%dk" % k,
                            "-maxrate", "%dk" % int(k * 1.5), "-bufsize", "%dk" % (k * 2)]
                else:
                    qp = str(_amf_qp(codec, crf))
                    cmd += ["-rc", "cqp", "-qp_i", qp, "-qp_p", qp]
                    if codec == "h264_amf":
                        cmd += ["-qp_b", qp]
            elif family == "qsv":
                # QSV 不走 crf，恒定质量用 ICQ（global_quality）；也没给 preset，
                # 各家驱动的默认档差异太大，交给驱动自己决定更稳
                if rate_mode == "bitrate":
                    k = max(int(bitrate * 1000), 100)
                    cmd += ["-b:v", "%dk" % k, "-maxrate", "%dk" % int(k * 1.5),
                            "-bufsize", "%dk" % (k * 2)]
                else:
                    cmd += ["-global_quality", str(crf)]
            elif family == "svtav1":
                cmd += ["-preset", "8"]
                if rate_mode == "bitrate":
                    k = max(int(bitrate * 1000), 100)
                    cmd += ["-b:v", "%dk" % k]
                else:
                    cmd += ["-crf", str(crf)]
            elif family == "aom":
                cmd += ["-cpu-used", "6"]
                if rate_mode == "bitrate":
                    k = max(int(bitrate * 1000), 100)
                    cmd += ["-b:v", "%dk" % k]
                else:
                    cmd += ["-crf", str(crf), "-b:v", "0"]
            elif family == "vp9":
                if rate_mode == "bitrate":
                    k = max(int(bitrate * 1000), 100)
                    cmd += ["-b:v", "%dk" % k]
                else:
                    cmd += ["-crf", str(crf), "-b:v", "0"]
            else:
                xp = {"fast": "medium", "medium": "medium", "balanced": "slow",
                      "slow": "slow", "slower": "slower", "veryslow": "veryslow"}.get(preset, "slow")
                cmd += ["-preset", xp]
                if rate_mode == "bitrate":
                    k = max(int(bitrate * 1000), 100)
                    cmd += ["-b:v", "%dk" % k, "-maxrate", "%dk" % int(k * 1.5), "-bufsize", "%dk" % (k * 2)]
                elif family == "x265":
                    cmd += ["-crf", str(crf), "-x265-params", "log-level=error"]
                else:
                    cmd += ["-crf", str(crf)]
            if family == "x265":
                cmd += ["-tag:v", "hvc1"]
            if src_path and os.path.isfile(src_path):
                cmd += ["-c:a", "copy"]
            if out_path.lower().endswith((".mp4", ".m4v", ".mov")):
                cmd += ["-movflags", "+faststart"]
            cmd += [out_path]
        self.log(("导出图片：" if self.image_fmt else "编码：") + " ".join(cmd))
        self.proc = procutil.popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        self.written = 0

    def write(self, frame_rgb):
        self.proc.stdin.write(frame_rgb.tobytes())
        self.written += 1

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        err = b""
        try:
            err = self.proc.stderr.read() or b""
        except Exception:
            pass
        code = self.proc.wait()
        txt = err.decode("utf-8", "replace").strip()
        if code != 0:
            raise RuntimeError("编码失败（退出码 %s）：%s" % (code, txt[-800:]))
        return txt


def available_encoders(ffmpeg, vendors=None):
    """本机真正能用的编码器菜单（按 ENCODERS 顺序）。

    两层过滤，缺一不可：

    1. ffmpeg 有没有把这个编码器编进去 —— gyan 的 full build 会把 nvenc / amf /
       qsv 全套都编上，所以光看这一层，N 卡机器上照样能选到 AMF，选中就直接
       「Cannot load nvEncodeAPI / 找不到编码器」。
    2. 本机有没有对应厂商的显卡 —— vendors 为 None 表示还没探到，这时**不按硬件
       过滤**：宁可多列几档让用户自己选，也不能因为一次探测失败把可用项藏掉。
    """
    try:
        out = procutil.run([ffmpeg, "-hide_banner", "-encoders"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace").stdout or ""
    except Exception:
        out = ""
    names = []
    for label, (codec, _pix, fam) in ENCODERS.items():
        if codec not in out:
            continue
        need = ENC_VENDOR.get(fam)
        if need and vendors and need not in vendors:
            continue
        names.append(label)
    # 全被过滤光（ffmpeg 太精简 / 探测异常）时至少留个软编，别给出空菜单
    return names or ["H265"]

