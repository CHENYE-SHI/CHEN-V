# -*- coding: utf-8 -*-
"""启动时并行探测「显卡名 / 显存 / 编码器列表」。

这三项都要起子进程（nvidia-smi、ffmpeg -encoders），在这台机器上合计约
0.15~0.25s。串在主线程里做，启动过渡页的粒子就会定住那么久；这里在
import PySide6 之前就各开一个线程并行去跑，等界面构建到真要显示它们的
时候（约 1s 之后）早就好了，等于免费。

只依赖 procutil / paths / video，不碰 Qt，所以能在 import gui_main 之前用：
    envprobe.start()      # main.py 里，越早越好
    envprobe.encoders()   # 取值（万一还没好就等它剩下那点时间）
    envprobe.gpu()
    envprobe.gpu_mem()
"""
import threading

_LOCK = threading.Lock()
_BOX = {}
_TH = {}
MISSING = object()          # 区分「还没探到」和「探到了但没结果（None）」


def start(ffmpeg=None):
    """启动三个探测线程。重复调用是空操作。"""
    with _LOCK:
        if _TH:
            return
        for key, fn, args in (("gpu", _work_gpu, ()),
                              ("mem", _work_mem, ()),
                              ("enc", _work_enc, (ffmpeg,))):
            th = threading.Thread(target=fn, args=args, name="env-probe-" + key,
                                  daemon=True)
            _TH[key] = th
            th.start()


def _work_gpu():
    # 一次 nvidia-smi 同时拿到「型号」「有没有 N 卡」「计算能力」三件事：
    # 能报出设备名就是有 N 卡。TensorRT 运行库在包里躺着也只是文件，
    # 没有 N 卡根本跑不起来，界面要靠这个结论把勾选框置灰。
    name, cap = _nvidia_info()
    _BOX["nvidia"] = bool(name)
    _BOX["cap"] = cap
    if name:
        _BOX["gpu"] = name
        _BOX["vendors"] = {"nvidia"}
        return
    try:
        other = _other_gpu_name()
        _BOX["gpu"] = other
    except Exception:
        other = "未知显卡"
        _BOX["gpu"] = other
    _BOX["vendors"] = _vendor_from_name(other)


def _vendor_from_name(name):
    """按显卡名判断厂商，供编码器过滤用（决定是否列出 NVENC / AMF / QSV）。"""
    n = str(name or "").lower()
    if any(k in n for k in ("radeon", "amd", "firepro", "gcn")):
        return {"amd"}
    if any(k in n for k in ("intel", "iris", "uhd", "hd graphics")):
        return {"intel"}
    return set()


def _work_mem():
    try:
        _BOX["mem"] = gpu_mem_now()
    except Exception:
        _BOX["mem"] = None


def _work_enc(ffmpeg):
    try:
        if not ffmpeg:
            import paths
            ffmpeg = paths.find_ffmpeg()
    except Exception:
        ffmpeg = None
    _BOX["ffmpeg"] = ffmpeg
    try:
        import video as vd
        _BOX["encoders"] = (vd.available_encoders(ffmpeg, vendors())
                            if ffmpeg else ["H265 NVENC"])
    except Exception:
        _BOX["encoders"] = ["H265 NVENC"]


def _wait(key, timeout=5.0):
    th = _TH.get(key)
    if th is not None:
        # 探测再怎么卡也不能把界面拖死，超时就先用默认值
        th.join(timeout)


def encoders(default=None):
    _wait("enc")
    return _BOX.get("encoders") or (default or ["H265 NVENC"])


def gpu(default="未知显卡"):
    _wait("gpu")
    return _BOX.get("gpu") or default


def gpu_mem():
    """返回 (已用MB, 总MB)；探不到返回 None。"""
    _wait("mem")
    return _BOX.get("mem")


def cached(key):
    """只取已经探到的结果（不等待），没探到返回 MISSING。"""
    return _BOX.get(key, MISSING)


def cached_gpu():
    v = _BOX.get("gpu")
    return v or None


def cached_nvidia():
    """只取已探到的结论：True=有 N 卡，False=没有，None=还没探完（别等待）。"""
    return _BOX.get("nvidia")


def vendors():
    """显卡厂商集合（{"nvidia"} / {"amd"} / {"intel"} ...），没探到返回空集。

    编码器过滤用：N 卡机器不该列出 AMF/QSV，A 卡机器不该列出 NVENC。
    空集 = 还没探到 / 探测失败，此时调用方不应按硬件过滤（宁可多列也不藏）。
    """
    _wait("gpu")
    return _BOX.get("vendors") or set()


def has_amd(default=False):
    """有没有 AMD 显卡；没探到 / 失败时按 default（这里默认 False，因为过滤
    以「有则列、无则藏」为原则，探测异常时交给调用方自己兜底）。"""
    _wait("gpu", 0.3)
    v = _BOX.get("vendors")
    return default if v is None else ("amd" in v)


def has_nvidia(default=True):
    """有没有 NVIDIA 显卡；探测没跑 / 失败时按 default 处理（宽松放行）。

    只等 0.3s：探测一般早就跑完了（子进程约 0.15s，界面构建在 1s 之后）。
    真赶不上就先返回 default，_finish_boot 里还会再确认一次——不能让界面卡在
    这里等一个子进程。
    """
    _wait("gpu", 0.3)
    v = _BOX.get("nvidia")
    return default if v is None else bool(v)


def compute_cap(default=None):
    """显卡计算能力字符串（如 "8.6" / "12.0"）；没探到返回 default。"""
    _wait("gpu", 0.3)
    return _BOX.get("cap") or default


def cached_mem():
    return _BOX.get("mem", MISSING)


def _nvidia_info():
    """(显卡型号, 计算能力字符串) —— 没有 N 卡时返回 (None, None)。

    compute_cap 用来判断包里有没有对应架构的 TensorRT 构建资源
    （12.0 -> sm120、8.6 -> sm86）。老驱动不认这个字段时退回只查名字，
    绝不能因为字段不支持就误判成「没 N 卡」。
    """
    try:
        import procutil
        p = procutil.run(["nvidia-smi", "--query-gpu=name,compute_cap",
                          "--format=csv,noheader"],
                         capture_output=True, text=True, timeout=4)
        line = (p.stdout or "").strip().splitlines()
        if line:
            parts = [x.strip() for x in line[0].split(",")]
            name = parts[0] if parts else ""
            cap = parts[1] if len(parts) > 1 else ""
            if name:
                return name, (cap or None)
    except Exception:
        pass
    return _nvidia_name(), None


def _nvidia_name():
    """nvidia-smi 报出的第一块 N 卡型号；没有 N 卡 / 没装驱动返回 None。"""
    try:
        import procutil
        p = procutil.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                         capture_output=True, text=True, timeout=4)
        line = (p.stdout or "").strip().splitlines()
        if line:
            return line[0].strip()
    except Exception:
        pass
    return None


def _other_gpu_name():
    """非 N 卡时用 wmic 拿个名字（核显 / A 卡），纯粹为了界面显示。"""
    try:
        import procutil
        p = procutil.run(["wmic", "path", "win32_VideoController", "get", "name"],
                         capture_output=True, text=True, timeout=6)
        for ln in (p.stdout or "").splitlines():
            ln = ln.strip()
            if ln and "Name" not in ln:
                return ln
    except Exception:
        pass
    return "未知显卡"


def gpu_name():
    """显卡型号：先 nvidia-smi，再退回 wmic（两者都是子进程）。"""
    return _nvidia_name() or _other_gpu_name()


def gpu_mem_now():
    """现查显存占用：(已用MB, 总MB) 或 None。"""
    try:
        import procutil
        p = procutil.run(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                          "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, timeout=4)
        txt = (p.stdout or "").strip().splitlines()
        if txt:
            a, b = txt[0].split(",")[:2]
            return int(float(a)), int(float(b))
    except Exception:
        pass
    return None
