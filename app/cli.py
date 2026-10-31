# -*- coding: utf-8 -*-
"""命令行入口（批量 / 被别的工具调用）。

示例：
  runtime\\py311\\python.exe app\\cli.py -i in.mp4 -o out -m 4 --engine tariff ^
      --sr AnimeJaNai_V2_Compact_2x_nc_test_only --encoder "H265 NVENC" --turbo
"""
import argparse
import os
import sys
import time

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import paths
import job as jobmod
import video as vd


def build_opts(a):
    ffmpeg = paths.find_ffmpeg()
    sr_models = paths.find_sr_models()
    tariff = paths.find_tariff_models()
    opts = {
        "inputs": a.input, "out_dir": a.out, "ffmpeg": ffmpeg,
        "mult": a.mult, "encoder": a.encoder, "preset": a.preset,
        "rate_mode": a.rate, "crf": a.crf, "bitrate": a.bitrate,
        "out_format": str(a.format or "mp4").upper(),
        "ext": vd.VIDEO_FORMATS.get(str(a.format or "mp4").upper(), ".mp4"),
        "two_pass": a.two_pass, "keep_intermediate": a.keep_intermediate,
        "sr_device": a.device, "sr_tile": a.tile,
        "hwdecode": a.hwdecode, "dedup": a.dedup,
        "scene_skip": a.scene, "dup_thr": a.dup_thr, "scene_thr": a.scene_thr,
        "cut_out": a.cut_out, "cut_blend": a.cut_blend, "cut_extrap": a.cut_extrap,
        "turbo": a.turbo, "start": a.start, "duration": a.duration,
        "out_res_mode": a.out_res,
        "fps": a.fps,
        "pyd_dir": paths.find_tariff_pyd(),
    }
    if a.sr and a.sr.lower() != "off":
        key = a.sr if a.sr in sr_models else next((k for k in sr_models if a.sr.lower() in k.lower()), None)
        if not key:
            raise SystemExit("可用超分模型：" + (", ".join(sr_models) or "（无）"))
        opts["sr_model"] = sr_models[key]

    engine = a.engine
    if engine == "auto":
        if a.fps > 0 or a.mult > 1:
            engine = "tariff"
        else:
            engine = "none"
    elif a.mult <= 1 and a.fps <= 0:
        engine = "none"
    opts["engine"] = engine
    if engine == "tariff":
        key = a.vfi if a.vfi in tariff else next((k for k in tariff if a.vfi.lower() in k.lower()), None)
        if not key:
            raise SystemExit("可用补帧模型：" + (", ".join(tariff) or "（无）"))
        opts["vfi_type"], opts["vfi_dir"] = tariff[key]
    return opts


def main(argv=None):
    ap = argparse.ArgumentParser(description="画质工厂 CLI：补帧 + 超分")
    ap.add_argument("-i", "--input", nargs="+", required=True)
    ap.add_argument("-o", "--out", default="")
    ap.add_argument("-m", "--mult", type=int, default=2, choices=[1, 2, 3, 4, 5, 6, 8])
    ap.add_argument("--engine", default="auto", choices=["auto", "tariff", "none"],
                    help="tariff=Tariff MNN（流式补帧）")
    ap.add_argument("--vfi", default="pwr", help="tariff 引擎的模型：pwr / nb202")
    ap.add_argument("--sr", default="", help="超分模型名，off=关闭")
    ap.add_argument("--device", default="dml", choices=["dml", "cpu"])
    ap.add_argument("--tile", type=int, default=0)
    ap.add_argument("--encoder", default="H265 NVENC")
    ap.add_argument("--format", default="mp4", choices=["mp4", "mkv", "mov", "png", "jpg", "webp"],
                    help="输出格式：mp4/mkv/mov 视频，或 png/jpg/webp 图片序列（写到同名子文件夹）")
    ap.add_argument("--two-pass", action="store_true",
                    help="两段式：先补帧出中间片，再单独超分（补帧/超分不同时占显卡）")
    ap.add_argument("--keep-intermediate", action="store_true", default=True,
                    help="保留补帧中间片（默认保留）")
    ap.add_argument("--no-keep-intermediate", dest="keep_intermediate", action="store_false",
                    help="超分完删掉补帧中间片")
    ap.add_argument("--rate", default="crf", choices=["crf", "bitrate"])
    ap.add_argument("--crf", type=int, default=16)
    ap.add_argument("--bitrate", type=float, default=20.0, help="目标码率 Mbps")
    ap.add_argument("--preset", default="balanced")
    ap.add_argument("--hwdecode", action="store_true")
    ap.add_argument("--dup-thr", type=float, default=0.06, help="重复帧阈值（帧差 0~255），默认 0.06")
    ap.add_argument("--cut-out", action="store_true", default=True, help="输出转场帧")
    ap.add_argument("--no-cut-out", dest="cut_out", action="store_false")
    ap.add_argument("--cut-blend", action="store_true", default=True, help="转场使用帧混合")
    ap.add_argument("--no-cut-blend", dest="cut_blend", action="store_false")
    ap.add_argument("--cut-extrap", action="store_true", help="转场外插")
    ap.add_argument("--scene", action="store_true", help="转场不做补帧（默认关）")
    ap.add_argument("--scene-thr", type=float, default=8.0, help="硬切判定阈值（帧差 0~255），默认 8")
    ap.add_argument("--turbo", action="store_true")
    ap.add_argument("--fps", type=float, default=0.0, help="输出帧率（如 120）；0=按倍率")
    ap.add_argument("--out-res", default="源分辨率", help="输出分辨率：源分辨率/50%%/200%%/HD 1080p/UHD 4K ...")
    ap.add_argument("--dedup", action="store_true", help="去掉重复帧（1拍2 用，默认关）")
    ap.add_argument("--start", type=float, default=0.0, help="起始秒")
    ap.add_argument("--duration", type=float, default=0.0, help="处理时长（秒），0=到结尾")
    a = ap.parse_args(argv)

    if not paths.find_ffmpeg():
        print("找不到 ffmpeg.exe")
        return 1
    paths.ensure_work_dirs()
    opts = build_opts(a)
    t0 = time.time()
    code = jobmod.Job(opts, log=lambda s: print(s, flush=True)).run()
    print("total %.1fs" % (time.time() - t0))
    return code


if __name__ == "__main__":
    sys.exit(main())







