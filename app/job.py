# -*- coding: utf-8 -*-
"""任务流水线：解码 -> 补帧(Tariff) -> 超分(AnimeJaNai) -> 编码/写图。

输出两种形态：
  * 视频   : ffmpeg 编码 MP4 / MKV / MOV，音轨原样复制
  * 图片序列: PNG / JPG / WEBP，每部片子一个同名子文件夹（frame_00000001.png…）

两段式（two_pass=True）：第 1 段只补帧、输出中间片 MKV；第 2 段只超分、读中间片出最终片。
两段之间补帧进程已退出，显存释放，避免 Vulkan / DirectML 抢同一张卡。

补帧：流式，逐帧解码 -> 去重合并 -> Tariff MNN 插值 -> 超分 -> 编码。
按「输出帧率」而不是死倍率算，所以 23.976 的源也能精确出 120.000fps。
"""
import math
import os
import re
import time

import video as vd
import procutil
import paths

VIDEO_EXT = (".mp4", ".mkv", ".mov", ".avi", ".flv", ".wmv", ".webm", ".m4v", ".ts", ".m2ts")



def expand_inputs(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for f in sorted(os.listdir(p)):
                if f.lower().endswith(VIDEO_EXT):
                    out.append(os.path.join(p, f))
        elif os.path.isfile(p):
            out.append(p)
    return out


def _unique(path):
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 1
    while os.path.exists("%s_%d%s" % (stem, i, ext)):
        i += 1
    return "%s_%d%s" % (stem, i, ext)


def _fmt_dt(sec):
    sec = int(max(sec, 0))
    return "%d:%02d:%02d" % (sec // 3600, (sec % 3600) // 60, sec % 60)


def _norm_format(o):
    """输出格式：MP4 / MKV / MOV / PNG / JPG / WEBP（缺省按 ext 推断，再退回 MP4）"""
    f = str(o.get("out_format") or "").strip().upper()
    if f == "JPEG":
        f = "JPG"
    if f in vd.VIDEO_FORMATS or f in vd.IMAGE_FORMATS:
        return f
    # 也认界面上的显示名，比如 "PNG 序列"
    for k in list(vd.IMAGE_FORMATS) + list(vd.VIDEO_FORMATS):
        if f.startswith(k):
            return k
    ext = str(o.get("ext") or ".mp4").strip().lower()
    if ext and not ext.startswith("."):
        ext = "." + ext
    for k, v in vd.VIDEO_FORMATS.items():
        if v == ext:
            return k
    for k, v in vd.IMAGE_FORMATS.items():
        if v[0] == ext:
            return k
    return "MP4"


def _mmss(sec):
    sec = int(max(round(float(sec)), 0))
    return "%02d:%02d:%02d" % (sec // 3600, (sec % 3600) // 60, sec % 60)


def _diff(a, b):
    """子采样平均绝对差（0~255）"""
    # numpy 延迟导入：它要 0.15s，import job 会把这段时间压在启动过渡页上，
    # 而界面一开局就要 import job（只为拿 VIDEO_EXT 和 Job 类）
    import numpy as np
    ga = a[::8, ::8].astype(np.int16)
    gb = b[::8, ::8].astype(np.int16)
    return float(np.abs(ga - gb).mean())


# 进程级引擎缓存：同一个界面里连续处理多个文件 / 多次点开始，引擎只初始化一次
_ENGINES = {}


def _reuse(key, factory, log=None, label=""):
    obj = _ENGINES.get(key)
    if obj is not None:
        if log:
            log("%s引擎已就绪：复用上次实例，跳过初始化" % label)
        return obj
    obj = factory()
    _ENGINES[key] = obj
    return obj


class Cancelled(Exception):
    """用户点了停止"""


class Job(object):
    def __init__(self, opts, log=print, progress=None, should_stop=None, file_hook=None):
        self.o = opts
        self.log = log
        # progress(done, total)：当前这个视频自己的进度（GUI 一条视频一个读条）
        self._progress = progress or (lambda done, total: None)
        # file_hook(idx, count, name, est)：轮到第几个视频
        self._file_hook = file_hook or (lambda idx, count, name, est: None)
        self._stop = should_stop or (lambda: False)
        self.sr = None
        self.vfi = None

    # ---------------------------------------------------------------- 资源
    def _get_sr(self):
        if self.sr is not None:
            return self.sr
        nc = self.o.get("sr_ncnn")
        if nc:
            from sr_ncnn import SrNcnn
            kind, model = nc
            gpuid = 0 if self.o.get("sr_device", "dml") != "cpu" else -1
            key = ("sr_ncnn", kind, model, gpuid)
            self.sr = _reuse(key, lambda: SrNcnn(kind, model, gpuid=gpuid, log=self.log),
                             self.log, "超分(ncnn)")
            return self.sr
        if self.sr is None and self.o.get("sr_model"):
            from sr import SrEngine
            key = ("sr", os.path.abspath(self.o["sr_model"]), self.o.get("sr_device", "auto"),
                   int(self.o.get("sr_tile") or 0))

            def make():
                self.log("加载超分模型：%s" % os.path.basename(self.o["sr_model"]))
                eng = SrEngine(self.o["sr_model"], device=self.o.get("sr_device", "auto"),
                               tile=int(self.o.get("sr_tile") or 0), log=self.log)
                self.log("超分后端：%s" % ", ".join(eng.providers))
                return eng

            self.sr = _reuse(key, make, self.log, "超分")
        return self.sr

    def _get_vfi(self):
        if self.vfi is None:
            from vfi import TariffEngine
            key = ("tariff", self.o.get("vfi_type", "pwr"), os.path.abspath(self.o["vfi_dir"]),
                   self.o.get("pyd_dir"))
            self.vfi = _reuse(key, lambda: TariffEngine(
                self.o.get("vfi_type", "pwr"), self.o["vfi_dir"],
                pyd_dir=self.o.get("pyd_dir"), log=self.log), self.log, "Tariff 补帧")
        return self.vfi

    # ---------------------------------------------------------------- 主流程
    def run(self):
        inputs = expand_inputs(self.o.get("inputs") or [])
        if not inputs:
            self.log("没有可处理的视频文件")
            return 1
        out_dir = self.o.get("out_dir") or os.path.dirname(inputs[0])
        os.makedirs(out_dir, exist_ok=True)
        ffmpeg = self.o["ffmpeg"]
        mult = max(int(self.o.get("mult") or 1), 1)
        engine = self.o.get("engine") or ("tariff" if mult > 1 else "none")
        if engine == "ncnn":
            # 独立 rife-ncnn-vulkan exe 已移除，统一走流式 Tariff 补帧
            engine = "tariff"

        plans = []
        for p in inputs:
            try:
                info = vd.probe(ffmpeg, p)
            except Exception as e:
                self.log("跳过 %s：%s" % (os.path.basename(p), e))
                continue
            n_src = self._range_frames(info)
            est = self._out_frames(info, n_src, mult)
            plans.append((p, info, est))
        if not plans:
            return 1

        t_start = time.time()
        # 两段式：第 1 段只补帧出中间片，第 2 段再单独超分（补帧/超分不抢同一张卡）
        if self._two_pass_enabled():
            try:
                code = self._run_two_pass(plans, out_dir)
            except Cancelled:
                self.log("任务已取消")
                return 2
            if code == 0:
                self.log("全部完成（先补帧 → 再超分），用时 %s" % _fmt_dt(time.time() - t_start))
            return code

        try:
            for idx, (p, info, est) in enumerate(plans, 1):
                if self._stop():
                    raise Cancelled()
                self._file_hook(idx, len(plans), os.path.basename(p), est)
                got = self._process_one(p, info, out_dir, mult, engine, est)
                self._progress(got, max(est, got))
        except Cancelled:
            self.log("任务已取消")
            return 2
        if not self.o.get("_quiet_done"):
            self.log("全部完成，用时 %s" % _fmt_dt(time.time() - t_start))
        return 0

    # ---------------------------------------------------------------- 两段式
    def _two_pass_enabled(self):
        """勾了两段式、并且补帧和超分都真的开着，才走两段。"""
        if not self.o.get("two_pass"):
            return False
        has_sr = bool(self.o.get("sr_model") or self.o.get("sr_ncnn"))
        return (self.o.get("engine") == "tariff") and has_sr

    @staticmethod
    def _pick_video(folder):
        try:
            fs = [os.path.join(folder, f) for f in sorted(os.listdir(folder))
                  if f.lower().endswith(VIDEO_EXT)]
        except Exception:
            fs = []
        return fs[0] if fs else None

    def _run_two_pass(self, plans, out_dir):
        """先补帧（超分关）→ 中间片 MKV → 再对中间片做超分（补帧关）。

        中间片用「编码器 / 码率」那套设置，和你手动先跑一遍补帧的结果一致；
        第 2 段把 out_res 留到最后再算，避免中间片先被缩一次。
        """
        keep = bool(self.o.get("keep_intermediate", True))
        count = len(plans)
        for idx, (src, _info, est) in enumerate(plans, 1):
            if self._stop():
                raise Cancelled()
            # 一个视频一条读条：两段合起来算这个视频的 100%
            one_total = max(int(est) * 2, 1)
            self._file_hook(idx, count, os.path.basename(src), one_total)
            stem = os.path.splitext(os.path.basename(src))[0]
            mid_dir = _unique(os.path.join(out_dir, "%s_补帧中间片" % stem))
            os.makedirs(mid_dir, exist_ok=True)

            o1 = dict(self.o)
            o1.pop("sr_model", None)
            o1.pop("sr_ncnn", None)
            o1.update({
                "inputs": [src], "out_dir": mid_dir,
                "out_format": "MKV", "ext": ".mkv",
                "out_res_mode": "源分辨率",
                "two_pass": False, "_quiet_done": True,
            })
            self.log("=" * 56)
            self.log("第 1 段／补帧：%s（超分关闭，中间片目录 %s）" % (os.path.basename(src), mid_dir))
            code = Job(o1, log=self.log,
                       progress=lambda d, t: self._progress(min(d, est), one_total),
                       should_stop=self._stop).run()
            if code != 0:
                return code

            mid = self._pick_video(mid_dir)
            if not mid:
                self.log("第 1 段没有产出中间片，跳过 %s" % os.path.basename(src))
                continue
            self.log("中间片：%s" % mid)

            o2 = dict(self.o)
            o2.update({
                "inputs": [mid], "out_dir": out_dir,
                "engine": "none", "mult": 1, "fps": 0.0,
                "start": 0.0, "duration": 0.0,
                "dedup": False, "scene_skip": False, "cut_out": False,
                "two_pass": False, "_quiet_done": True,
            })
            self.log("-" * 56)
            self.log("第 2 段／超分：%s（补帧关闭，只做超分 + 编码）" % os.path.basename(mid))
            code = Job(o2, log=self.log,
                       progress=lambda d, t: self._progress(min(est + d, one_total), one_total),
                       should_stop=self._stop).run()
            if code != 0:
                return code

            if keep:
                self.log("补帧中间片保留在：%s" % mid_dir)
            else:
                try:
                    import shutil
                    shutil.rmtree(mid_dir, ignore_errors=True)
                    self.log("已删除补帧中间片目录（勾「保留补帧中间片」可留着）")
                except Exception:
                    pass
            self._progress(one_total, one_total)
        return 0

    def _range_frames(self, info):
        n = info["frames"] or int(info["duration"] * info["fps"])
        dur = self.o.get("duration") or 0
        start = self.o.get("start") or 0
        if info["fps"] > 0:
            if start > 0:
                n = max(1, n - int(start * info["fps"]))
            if dur > 0:
                n = min(n, max(1, int(dur * info["fps"])))
        return n

    def _target_res(self, w, h):
        """输出分辨率预设 → (w, h)；None = 保持原样"""
        mode = (self.o.get("out_res_mode") or "").strip()
        if not mode or mode in ("源分辨率", "原分辨率", "100%"):
            return None
        try:
            if mode.endswith("%"):
                f = float(mode[:-1]) / 100.0
                tw, th = int(round(w * f)), int(round(h * f))
            else:
                presets = {"SD 480p": 480, "HD 720p": 720, "HD 1080p": 1080,
                           "UHD 4K": 2160, "UHD 8K": 4320}
                th = presets.get(mode)
                if not th:
                    return None
                tw = int(round(th * w / float(h)))
        except Exception:
            return None
        tw -= tw % 2
        th -= th % 2
        if tw < 16 or th < 16:
            return None
        # 不再因为"和目标等于源尺寸"就跳过：开了超分时实际帧是源的 N 倍，
        # 必须照样缩到用户选的尺寸。
        return (tw, th)

    def _out_frames(self, info, n_src, mult):
        engine = self.o.get("engine") or "none"
        tf = float(self.o.get("fps") or 0)
        fps_in = info["fps"] or 24.0
        if engine == "none":
            # 不补帧：输出帧数就是源帧数，「输出帧率」不参与（否则只超分会被改快慢）
            return max(1, n_src)
        if tf > 0:
            return max(1, int(round(n_src / fps_in * tf)))
        return max(1, n_src * mult)

    # ---------------------------------------------------------------- 单个文件
    def _process_one(self, src, info, out_dir, mult, engine, est):
        w, h = info["width"], info["height"]
        self.o["_scale_to"] = self._target_res(w, h)
        fps_in = info["fps"] or 24.0
        tf = float(self.o.get("fps") or 0) if engine != "none" else 0.0
        if engine == "none":
            mult = 1                      # 不补帧就别按倍率/目标帧率改时间轴
        fps_out = tf if tf > 0 else fps_in * mult
        has_sr = bool(self.o.get("sr_model") or self.o.get("sr_ncnn"))
        tag = []
        if engine != "none":
            tag.append("%.2ffps" % fps_out)
        if engine == "tariff":
            tag.append("rife")
        if has_sr:
            tag.append("SR")
        stem = os.path.splitext(os.path.basename(src))[0]
        fmt = _norm_format(self.o)
        self.o["_fmt"] = fmt
        is_image = fmt in vd.IMAGE_FORMATS
        base_name = "%s_%s" % (stem, "_".join(tag) or "out")
        _sfx = str(self.o.get("name_suffix") or "").strip()
        if _sfx:
            _sfx = re.sub(r'[\\/:*?"<>|]+', "_", _sfx).strip(" .")
            if _sfx:
                base_name = "%s_%s" % (stem, _sfx)
        if is_image:
            # 图片序列：每部片子一个同名子文件夹，里面是 frame_00000001.png…
            out = _unique(os.path.join(out_dir, base_name))
            os.makedirs(out, exist_ok=True)
        else:
            out = _unique(os.path.join(out_dir, base_name + vd.VIDEO_FORMATS.get(fmt, ".mp4")))
        self.log("—" * 56)
        self.log("输入：%s  %dx%d  %.3ffps  约 %d 帧" % (os.path.basename(src), w, h, fps_in, info["frames"]))
        if is_image:
            self.log("输出：%s\\frame_%%08d%s  (%s 图片序列，%.3ffps，不含音轨)" % (
                out, vd.IMAGE_FORMATS[fmt][0], fmt, fps_out))
        else:
            self.log("输出：%s  (%.3ffps)" % (out, fps_out))

        return self._run_stream(src, out, w, h, fps_in, fps_out, mult, engine, est)


    # ---------------------------------------------------------------- 流式（Tariff / 无补帧）
    def _run_stream(self, src, out, w, h, fps_in, fps_out, mult, engine, est):
        ffmpeg = self.o["ffmpeg"]
        start, dur = self.o.get("start"), self.o.get("duration")
        sr = self._get_sr()
        reader = vd.FrameReader(ffmpeg, src, w, h, hwdecode=self.o.get("hwdecode", False),
                               start=start, duration=dur)
        first = reader.read()
        if first is None:
            reader.close()
            self.log("读取失败，跳过")
            return 0
        first_out = sr.upscale(first) if sr is not None else first
        oh, ow = first_out.shape[:2]
        writer = self._writer(out, ow, oh, fps_out, src)
        vfi = self._get_vfi() if engine == "tariff" else None
        dedup = bool(self.o.get("dedup", False)) and vfi is not None
        dup_thr = float(self.o.get("dup_thr", 0.06))
        scene_thr = float(self.o.get("scene_thr", 40.0))
        scene_skip = bool(self.o.get("scene_skip", False)) and vfi is not None
        ratio = max(fps_out / max(fps_in, 1e-6), 1.0) if vfi is not None else 1.0
        acc = 1.0
        n_out = n_dup = n_scene = 0
        t0 = time.time()
        try:
            writer.write(first_out); n_out += 1
            prev = first
            held = 0
            while True:
                if self._stop():
                    raise Cancelled()
                cur = reader.read()
                if cur is None:
                    break
                d = None
                if dedup or scene_skip:
                    d = _diff(prev, cur)
                if dedup and d is not None and d < dup_thr:
                    held += 1                      # 和上一张几乎一样：先压着，攒到真正变化时一起插
                    n_dup += 1
                    continue
                steps = held + 1
                held = 0
                cut = (scene_skip and d is not None and d > scene_thr)
                frames = []
                if vfi is not None:
                    acc += steps * ratio
                    k = int(round(acc))
                    acc -= k
                    k = max(k, 1)
                    if cut:
                        frames = [prev] * max(k - 1, 0)
                        n_scene += 1
                    elif k > 1:
                        frames = vfi.interpolate(prev, cur, [i / float(k) for i in range(1, k)])
                for f in frames + [cur]:
                    if self._stop():
                        raise Cancelled()
                    o = sr.upscale(f) if sr is not None else f
                    writer.write(o)
                    n_out += 1
                    self._tick(t0, n_out, est)
                prev = cur
            writer.close()
        finally:
            reader.close()
        st = self.o.get("_scale_to")
        fw, fh = (st[0], st[1]) if st else (ow, oh)
        self._log_done(out, n_out, fw, fh, fps_out, t0,
                       "  合并重复 %d 帧/跳转场 %d 处" % (n_dup, n_scene) if (n_dup or n_scene) else "")
        return n_out

    # ---------------------------------------------------------------- 工具
    def _writer(self, out, ow, oh, fps_out, src, fmt=None):
        # 只有目标尺寸和实际帧尺寸不一致时才加 scale 滤镜
        st = self.o.get("_scale_to")
        if st and (int(st[0]), int(st[1])) == (int(ow), int(oh)):
            st = None
        fmt = fmt or self.o.get("_fmt") or _norm_format(self.o)
        if fmt in vd.IMAGE_FORMATS:
            # 图片序列：out 是目录，ffmpeg 按 frame_%08d 编号写盘，音轨不带
            return vd.FrameWriter(self.o["ffmpeg"], vd.image_pattern(out, fmt), ow, oh, fps_out,
                                  None, image_fmt=fmt, log=self.log, scale_to=st)
        return vd.FrameWriter(self.o["ffmpeg"], out, ow, oh, fps_out, src,
                              encoder=self.o.get("encoder", "H265 NVENC"),
                              crf=self.o.get("crf", 16),
                              preset=self.o.get("preset", "balanced"),
                              rate_mode=self.o.get("rate_mode", "crf"),
                              bitrate=self.o.get("bitrate", 20),
                              turbo=self.o.get("turbo", False),
                              start=self.o.get("start"), duration=self.o.get("duration"),
                              scale_to=st, log=self.log)

    def _tick(self, t0, n_out, est):
        self._progress(n_out, max(int(est), 1))
        every = 12 if self.o.get("turbo") else 4
        if n_out % every == 0:
            el = max(time.time() - t0, 1e-6)
            sp = n_out / el
            self.log("  已输出 %d 帧  %.2f 帧/秒  剩余约 %s" % (
                n_out, sp, _fmt_dt(max(est - n_out, 0) / max(sp, 1e-6))))

    def _log_done(self, out, n, fw, fh, fps_out, t0, extra=""):
        fmt = self.o.get("_fmt") or ""
        if fmt in vd.IMAGE_FORMATS:
            self.log("完成：%s  %d 张 %dx%d（%s 图片序列）用时 %s%s" % (
                os.path.basename(out), n, fw, fh, fmt, _fmt_dt(time.time() - t0), extra))
        else:
            self.log("完成：%s  %d 帧 %dx%d %.3ffps 用时 %s%s" % (
                os.path.basename(out), n, fw, fh, fps_out, _fmt_dt(time.time() - t0), extra))
















