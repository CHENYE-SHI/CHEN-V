# -*- coding: utf-8 -*-
"""画质工厂 GUI（v2）：拖放输入、自定义背景、可保存预设。

补帧：RIFE(ncnn) / Tariff(MNN)
超分：AnimeJaNai ONNX（GPU=DirectML / CPU）
编码：NVENC / x264 / x265
"""
import procutil
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

import paths
import envprobe
import job as jobmod
import video as vd

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _HAS_DND = True
except Exception:
    TkinterDnD = None
    DND_FILES = None
    _HAS_DND = False

BG = "#15171f"
PANEL = "#1b1e2a"
PANEL2 = "#252a3b"
FG = "#e6e7ea"
MUTED = "#98a0ae"
ACCENT = "#4e9cf5"
FONT = ("Microsoft YaHei UI", 10)
FONT_B = ("Microsoft YaHei UI", 10, "bold")
FONT_T = ("Microsoft YaHei UI", 16, "bold")
FONT_M = ("Consolas", 9)

OUT_RES = ["源分辨率", "25%", "50%", "75%", "150%", "200%", "300%", "400%",
           "SD 480p", "HD 720p", "HD 1080p", "UHD 4K", "UHD 8K"]

# 输出格式：视频容器 / 图片序列（图片序列写到同名子文件夹）
OUT_FORMATS = ["MP4 视频", "MKV 视频", "PNG 序列", "JPG 序列", "WEBP 序列"]
FMT_MAP = {"MP4 视频": "MP4", "MKV 视频": "MKV",
           "PNG 序列": "PNG", "JPG 序列": "JPG", "WEBP 序列": "WEBP"}

VFI_ORDER = [("pwr", "Tariff pwr（高质量·慢）"),
             ("nb202", "Tariff nb202（最慢）")]

PRESET_DIR = os.path.join(paths.APP_DIR, "presets")



class Panel(tk.Frame):
    """带背景图的卡片：画布在下（背景图按窗口坐标裁切 + 暗色蒙版 + 标题），
    内容放在 body 里；body 只包住控件本身，四周和空白处露出背景图。"""

    def __init__(self, master, app, title="", **kw):
        tk.Frame.__init__(self, master, bg=PANEL, highlightthickness=1,
                          highlightbackground="#3a4256", **kw)
        self.app = app
        self.title = title
        self.cv = tk.Canvas(self, bg=PANEL, highlightthickness=0, bd=0)
        self.cv.place(x=0, y=0, relwidth=1, relheight=1)
        self.body = ttk.Frame(self, style="Card.TFrame")
        self.body.pack(anchor="nw", padx=10, pady=(20, 8))

    def refresh(self):
        cv = self.cv
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10:
            return
        cv.delete("all")
        photo = getattr(self.app, "_bg_photo", None)
        # 面板里只铺一层很淡的背景（约 88% 暗），作为"能看见背景图"的最低可读版本；
        # Tk 没有真正的控件级半透明，再透就会看不清文字。
        if photo is not None and bool(getattr(self.app, "var_panelbg", None) and self.app.var_panelbg.get()):
            try:
                x = self.winfo_rootx() - self.app.winfo_rootx()
                y = self.winfo_rooty() - self.app.winfo_rooty()
                cv.create_image(-x, -y, anchor="nw", image=photo)
                cv.create_rectangle(0, 0, w, h, fill="#0a0d14", outline="", stipple="gray75")
                cv.create_rectangle(1, 1, w + 1, h + 1, fill="#0a0d14", outline="", stipple="gray50")
                cv.create_rectangle(2, 2, w + 2, h + 2, fill="#0a0d14", outline="", stipple="gray25")
            except Exception:
                cv.configure(bg=PANEL)
        else:
            cv.configure(bg=PANEL)
        if self.title:
            cv.create_text(10, 4, text=self.title, anchor="nw", fill=ACCENT, font=FONT_B)

class Check(tk.Frame):
    """自绘复选框：方框 + 对勾"""

    def __init__(self, master, text, var, bg=PANEL, fg=FG, accent=ACCENT, font=FONT):
        tk.Frame.__init__(self, master, bg=bg)
        self.var = var
        self.fg = fg
        self.accent = accent
        self.cv = tk.Canvas(self, width=17, height=17, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.cv.pack(side="left")
        self.box = self.cv.create_rectangle(1.5, 1.5, 15.5, 15.5, outline="#5b6480", width=1.4, fill="#11131b")
        self.tick = self.cv.create_line(4.6, 8.8, 7.2, 11.6, 12.6, 5.2, fill=accent, width=2.2,
                                        capstyle="round", joinstyle="round", state="hidden")
        self.lbl = tk.Label(self, text=text, bg=bg, fg=fg, font=font, cursor="hand2")
        self.lbl.pack(side="left", padx=(7, 0))
        for w in (self, self.cv, self.lbl):
            w.bind("<Button-1>", self._toggle)
            w.bind("<Enter>", self._hover_on)
            w.bind("<Leave>", self._hover_off)
        try:
            self.var.trace_add("write", lambda *a: self._sync())
        except Exception:
            self.var.trace("w", lambda *a: self._sync())
        self._sync()

    def _toggle(self, _e=None):
        self.var.set(not bool(self.var.get()))

    def _hover_on(self, _e=None):
        self.lbl.configure(fg=self.accent)
        self.cv.itemconfigure(self.box, outline=self.accent)

    def _hover_off(self, _e=None):
        self.lbl.configure(fg=self.fg)
        self.cv.itemconfigure(self.box, outline=self.accent if self.var.get() else "#5b6480")

    def _sync(self):
        on = bool(self.var.get())
        self.cv.itemconfigure(self.tick, state="normal" if on else "hidden")
        self.cv.itemconfigure(self.box, outline=self.accent if on else "#5b6480",
                              fill="#22344f" if on else "#11131b")


if _HAS_DND:
    class _Root(TkinterDnD.Tk):
        pass
else:
    class _Root(tk.Tk):
        pass


class App(_Root):
    def __init__(self):
        _Root.__init__(self)
        self.title("画质工厂 · 补帧 + 超分")
        self.configure(bg=BG)
        self.q = queue.Queue()
        self.worker = None
        self.stop_event = threading.Event()
        self.t0 = 0.0
        self._samples = []
        self.cur_file = (0, 0, "")
        self._bg_photo = None
        self._bg_size = (0, 0)
        self._bg_job = None
        self.setting = paths.load_settings()

        self.ffmpeg = paths.find_ffmpeg()
        self.sr_models = paths.find_sr_models()
        self.tariff_models = paths.find_tariff_models()
        self.encoders = vd.available_encoders(self.ffmpeg, envprobe.vendors()) if self.ffmpeg else ["H265"]
        self.pyd_dir = paths.find_tariff_pyd()
        self.vfi_map = self._build_vfi_map()
        os.makedirs(PRESET_DIR, exist_ok=True)

        self._style()
        self._build()
        self._place_window()
        self._restore()
        self._apply_background(self.setting.get("bg", ""), save=False)
        self.bind("<Configure>", self._on_resize)
        self.after(150, self._poll)
        self.after(400, self._refresh_hint)      # 等布局稳定后再决定显隐
        self.after(500, self._refresh_panels)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._report_env()

    # ------------------------------------------------------------ 模型菜单
    def _build_vfi_map(self):
        m = {}
        for key, label in VFI_ORDER:
            if key in self.tariff_models:
                m[label] = ("tariff", (self.tariff_models[key], key))
        return m

    # ------------------------------------------------------------ 主题
    def _style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure(".", background=BG, foreground=FG, font=FONT, fieldbackground=PANEL2)
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=PANEL)
        st.configure("TLabel", background=PANEL, foreground=FG)
        st.configure("Title.TLabel", background=BG, foreground=FG, font=FONT_T)
        st.configure("Sub.TLabel", background=BG, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        st.configure("Card.TLabel", background=PANEL, foreground=FG)
        st.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        st.configure("TLabelframe", background=PANEL, foreground=ACCENT, bordercolor="#333a4e")
        st.configure("TLabelframe.Label", background=PANEL, foreground=ACCENT, font=FONT_B)
        st.configure("TButton", background=PANEL2, foreground=FG, borderwidth=0, padding=(11, 6))
        st.map("TButton", background=[("active", "#31395a"), ("disabled", "#22252f")])
        st.configure("Accent.TButton", background=ACCENT, foreground="#0b1220", font=FONT_B, padding=(18, 8))
        st.map("Accent.TButton", background=[("active", "#6fb2ff"), ("disabled", "#2b3247")])
        st.configure("Stop.TButton", background="#7a2f2f", foreground="#ffe9e9", padding=(18, 8))
        st.map("Stop.TButton", background=[("active", "#9c3b3b"), ("disabled", "#3a2a2a")],
               foreground=[("disabled", "#8d7a7a")])
        st.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2, foreground=FG,
                     arrowcolor=FG, selectbackground=PANEL2, selectforeground=FG,
                     bordercolor="#333a4e", lightcolor=PANEL2, darkcolor=PANEL2)
        st.map("TCombobox",
               fieldbackground=[("readonly", PANEL2), ("disabled", "#2a2e3d")],
               foreground=[("readonly", FG), ("disabled", MUTED)],
               selectbackground=[("readonly", PANEL2)],
               selectforeground=[("readonly", FG)])
        st.configure("TEntry", fieldbackground=PANEL2, foreground=FG, insertcolor=FG)
        st.configure("TSpinbox", fieldbackground=PANEL2, foreground=FG, arrowcolor=FG)
        st.configure("TScale", background=BG)
        st.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=PANEL2,
                     bordercolor=PANEL, lightcolor=ACCENT, darkcolor=ACCENT)
        self.option_add("*TCombobox*Listbox.background", PANEL2)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", "#0b1220")

    # ------------------------------------------------------------ 背景（独立背窗 + 窗口透明）
    def _ensure_backdrop(self):
        """背景图放在一个无边框的后置窗口里，主窗口用 -alpha 变半透明，
        这样面板/日志区都能透出背景（Tk 没有真正的控件级透明，这是唯一靠谱的做法）。"""
        if getattr(self, "_bd", None) is None:
            self._bd = tk.Toplevel(self)
            self._bd.overrideredirect(True)
            try:
                self._bd.attributes("-toolwindow", True)
            except Exception:
                pass
            self._bd.configure(bg=BG)
            self._bd_cv = tk.Canvas(self._bd, bg=BG, highlightthickness=0, bd=0)
            self._bd_cv.pack(fill="both", expand=True)
            self._bd.withdraw()
        return self._bd

    def _bg_canvas(self):
        self._ensure_backdrop()
        return self._bd_cv

    def _sync_backdrop(self):
        if getattr(self, "_bd", None) is None:
            return
        try:
            if self.state() == "iconic":
                self._bd.withdraw()
                return
            x, y = self.winfo_rootx(), self.winfo_rooty()
            w, h = self.winfo_width(), self.winfo_height()
            if w < 50 or h < 50:
                return
            self._bd.geometry("%dx%d+%d+%d" % (w, h, x, y))
            if not self._bd.winfo_ismapped():
                self._bd.deiconify()
            try:
                self.tk.call("lower", self._bd._w)
            except Exception:
                pass
        except Exception:
            pass

    def pick_background(self):
        f = filedialog.askopenfilename(title="选择背景图片",
                                       filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp"), ("全部", "*.*")])
        if f:
            self._apply_background(f)

    def clear_background(self):
        self.setting["bg"] = ""
        paths.save_settings(self.setting)
        cv = self._bg_canvas()
        cv.delete("all")
        self._bg_photo = None
        self._bg_size = (0, 0)
        try:
            self._bd.withdraw()
        except Exception:
            pass
        self._apply_alpha()

    def purge_cache(self):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("清理缓存", "任务正在跑，等它结束再清理")
            return
        paths.ensure_work_dirs()
        size = paths.dir_size(paths.TEMP_DIR) + paths.dir_size(paths.CACHE_DIR)
        for p in paths.legacy_cache_paths():
            size += paths.dir_size(p)
        if not messagebox.askyesno("清理缓存",
                                   "将删除补帧缓存和临时抽帧文件（含 C 盘旧缓存，约 %.0f MB）。\n"
                                   "补帧缓存删掉后，下次要重新插帧。继续？" % (size / 1048576.0)):
            return
        freed = paths.purge_caches()
        self._append("已清理缓存：%.0f MB（缓存目录 %s）" % (freed / 1048576.0, paths.CACHE_DIR))

    def _scaled_bg(self, src, w, h):
        """用 ffmpeg 缩放到窗口大小，输出到 ASCII 临时目录（Tk 自己缩放会糊）"""
        if not self.ffmpeg or not os.path.isfile(src):
            return None
        home = paths.WORK_DIR
        os.makedirs(home, exist_ok=True)
        out = os.path.join(home, "bg_%dx%d.png" % (w, h))
        try:
            procutil.run([self.ffmpeg, "-y", "-v", "error", "-i", src,
                            "-vf", "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d" % (w, h, w, h),
                            "-frames:v", "1", out], timeout=60)
            return out if os.path.isfile(out) else None
        except Exception:
            return None

    def _apply_background(self, path, save=True):
        if not path or not os.path.isfile(path):
            return
        self._ensure_backdrop()
        w = max(self.winfo_width(), 900)
        h = max(self.winfo_height(), 600)
        out = self._scaled_bg(path, w, h)
        if not out:
            return
        try:
            self._bg_photo = tk.PhotoImage(file=out)
        except Exception:
            return
        cv = self._bd_cv
        cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_photo)
        self._bg_size = (w, h)
        try:
            wc = getattr(self, "_win_cv", None)
            if wc is not None:
                wc.delete("all")
                wc.create_image(0, 0, anchor="nw", image=self._bg_photo)
                wc.create_rectangle(0, 0, w, h, fill="#0a0d14", outline="", stipple="gray25")
        except Exception:
            pass
        self._draw_overlay()
        self._sync_backdrop()
        self._apply_alpha()
        self.after(60, self._refresh_panels)
        if save:
            self.setting["bg"] = path
            paths.save_settings(self.setting)

    def _draw_overlay(self):
        if not self._bg_photo:
            return
        cv = self._bd_cv
        cv.delete("ov")
        try:
            dark = int(float(self.var_bgalpha.get()))
        except Exception:
            dark = 40
        stipple = "gray75" if dark >= 80 else ("gray50" if dark >= 55 else ("gray25" if dark >= 25 else "gray12"))
        w, h = self._bg_size
        cv.create_rectangle(0, 0, w, h, fill="#07090f", outline="", stipple=stipple, tags="ov")

    def _toggle_panelbg(self):
        try:
            self.setting["panel_bg"] = bool(self.var_panelbg.get())
            paths.save_settings(self.setting)
        except Exception:
            pass
        self._refresh_panels()

    def _refresh_panels(self):
        for p in getattr(self, "_panels", []):
            try:
                p.refresh()
            except Exception:
                pass

    def _apply_alpha(self):
        """主窗口透明度：背景暗度越低，窗口越透（背景越明显）"""
        if not self._bg_photo:
            try:
                self.attributes("-alpha", 1.0)
            except Exception:
                pass
            return
        try:
            dark = int(float(self.var_bgalpha.get()))
        except Exception:
            dark = 40
        try:
            self.attributes("-alpha", alpha)
        except Exception:
            pass

    def _on_resize(self, e=None):
        if e is not None and e.widget is not self:
            return
        self._sync_backdrop()
        if self._bg_job:
            try:
                self.after_cancel(self._bg_job)
            except Exception:
                pass
        self._bg_job = self.after(400, self._resize_bg)

    def _resize_bg(self):
        self._bg_job = None
        path = self.setting.get("bg", "")
        if path and os.path.isfile(path):
            w, h = self.winfo_width(), self.winfo_height()
            if abs(w - self._bg_size[0]) > 40 or abs(h - self._bg_size[1]) > 40:
                self._apply_background(path, save=False)
        self._sync_backdrop()
        self.after(80, self._refresh_panels)

    def _on_alpha(self, *_):
        try:
            self.setting["bg_alpha"] = int(float(self.var_bgalpha.get()))
        except Exception:
            pass
        paths.save_settings(self.setting)
        self._draw_overlay()
        self._apply_alpha()

    # ------------------------------------------------------------ 布局
    def _card(self, parent, pad=(12, 8)):
        outer = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground="#333a4e")
        inner = ttk.Frame(outer, style="Card.TFrame", padding=pad)
        inner.pack(fill="both", expand=True)
        return outer, inner

    def _build(self):
        # 窗口最底层放一张画布，用来铺背景图（面板各自也有半透层）
        self._win_cv = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self._win_cv.place(x=0, y=0, relwidth=1, relheight=1)
        try:
            self.tk.call("lower", self._win_cv._w)
        except Exception:
            pass
        head = ttk.Frame(self, padding=(16, 10, 16, 2))
        head.pack(fill="x")
        tk.Label(head, text="画质工厂", bg=BG, fg=FG, font=FONT_T).pack(side="left")
        tk.Label(head, text="   补帧 · 超分 · GPU 加速", bg=BG, fg=MUTED,
                 font=("Microsoft YaHei UI", 9)).pack(side="left")

        right = tk.Frame(head, bg=BG)
        right.pack(side="right")
        tk.Label(right, text="预设", bg=BG, fg=MUTED, font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(0, 4))
        self.var_preset = tk.StringVar(value=self.setting.get("preset_name", "默认"))
        self.cb_preset = ttk.Combobox(right, textvariable=self.var_preset, values=self._preset_names(),
                                      state="readonly", width=12)
        self.cb_preset.pack(side="left")
        self.cb_preset.bind("<<ComboboxSelected>>", lambda e: self.load_preset())
        ttk.Button(right, text="保存预设", command=self.save_preset).pack(side="left", padx=(6, 0))
        ttk.Button(right, text="删除预设", command=self.del_preset).pack(side="left", padx=(6, 0))
        tk.Frame(right, bg=BG, width=18).pack(side="left")
        tk.Label(right, text="背景暗度", bg=BG, fg=MUTED, font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(0, 4))
        self.var_bgalpha = tk.StringVar(value=str(self.setting.get("bg_alpha", 40)))
        sc = ttk.Scale(right, from_=0, to=100, orient="horizontal", length=80,
                       command=lambda v: self._on_alpha(v))
        try:
            sc.set(float(self.var_bgalpha.get()))
        except Exception:
            sc.set(40)
        sc.pack(side="left")
        ttk.Button(right, text="背景图", command=self.pick_background).pack(side="left", padx=(10, 0))
        ttk.Button(right, text="清除背景", command=self.clear_background).pack(side="left", padx=(6, 0))
        ttk.Button(right, text="清理缓存", command=self.purge_cache).pack(side="left", padx=(6, 0))

        # 拖放区
        drop_outer = tk.Frame(self, bg=PANEL, highlightthickness=2, highlightbackground=ACCENT)
        drop_outer.pack(fill="x", padx=16, pady=(8, 6))
        drop = tk.Frame(drop_outer, bg=PANEL)
        drop.pack(fill="x", padx=2, pady=2)
        self.lbl_drop = tk.Label(drop, text="把视频文件 / 文件夹拖到这里\n（也可以点下面的按钮选择）",
                                 bg=PANEL, fg=MUTED, font=("Microsoft YaHei UI", 11), pady=12)
        self.lbl_drop.pack(fill="x")
        btns = tk.Frame(drop, bg=PANEL)
        btns.pack(pady=(0, 8))
        ttk.Button(btns, text="选择文件", command=self.pick_files).pack(side="left", padx=4)
        ttk.Button(btns, text="选择文件夹", command=self.pick_folder).pack(side="left", padx=4)
        ttk.Button(btns, text="清空列表", command=self.clear_inputs).pack(side="left", padx=4)
        self.lbl_files = tk.Label(drop, text="未选择文件", bg=PANEL, fg=MUTED, font=("Microsoft YaHei UI", 9),
                                  anchor="w", justify="left", wraplength=900)
        self.lbl_files.pack(fill="x", padx=14, pady=(0, 8))
        self.var_input = tk.StringVar()

        for w in (drop_outer, drop, self.lbl_drop, self.lbl_files):
            self._register_drop(w)

        # 输出目录
        out_outer, out_in = self._card(self)
        out_outer.pack(fill="x", padx=16, pady=(0, 6))
        ttk.Label(out_in, text="输出目录（留空 = 源文件目录）", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.var_out = tk.StringVar()
        ttk.Entry(out_in, textvariable=self.var_out).grid(row=1, column=0, sticky="ew", pady=(4, 0), padx=(0, 8))
        ttk.Button(out_in, text="浏览…", command=self.pick_out).grid(row=1, column=1, padx=2)
        ttk.Button(out_in, text="打开", command=self.open_out).grid(row=1, column=2, padx=2)
        out_in.columnconfigure(0, weight=1)

        # 三个面板
        row = ttk.Frame(self, padding=(16, 2, 16, 0))
        row.pack(fill="x")
        row.columnconfigure(0, weight=3, uniform="c")
        row.columnconfigure(1, weight=4, uniform="c")
        row.columnconfigure(2, weight=3, uniform="c")
        p1 = Panel(row, self, "补帧")
        p1.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        lf1 = p1.body
        p2 = Panel(row, self, "超分")
        p2.grid(row=0, column=1, sticky="nsew", padx=6)
        lf2 = p2.body
        p3 = Panel(row, self, "编码")
        p3.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        lf3 = p3.body
        self._panels = [p1, p2, p3]

        self.var_vfi_on = tk.BooleanVar(value=bool(self.setting.get("vfi_on", True)))
        self.var_sr_on = tk.BooleanVar(value=bool(self.setting.get("sr_on", True)))
        names = list(self.vfi_map.keys()) or ["（没有可用补帧引擎）"]
        self.var_vfi = tk.StringVar(value=self.setting.get("vfi", names[0]))
        ttk.Label(lf1, text="补帧引擎", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        Check(lf1, "启用补帧", self.var_vfi_on).grid(row=0, column=1, sticky="e")
        cb = ttk.Combobox(lf1, textvariable=self.var_vfi, values=names, state="readonly", width=22)
        cb.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 6))
        cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_hint())
        ttk.Label(lf1, text="倍率", style="Card.TLabel").grid(row=2, column=0, sticky="w")
        self.var_mult = tk.StringVar(value=str(self.setting.get("mult", 2)))
        ttk.Combobox(lf1, textvariable=self.var_mult, values=["2", "3", "4", "5", "6"],
                     state="readonly", width=5).grid(row=3, column=0, sticky="w", pady=(2, 4))
        self.var_hint = tk.StringVar(value="")
        ttk.Label(lf1, textvariable=self.var_hint, style="Muted.TLabel", wraplength=260, justify="left")\
            .grid(row=4, column=0, columnspan=2, sticky="w")
        self.var_two = tk.BooleanVar(value=bool(self.setting.get("two_pass", False)))
        self.var_keep = tk.BooleanVar(value=bool(self.setting.get("keep_intermediate", True)))
        Check(lf1, "两段式：先补帧 → 再超分", self.var_two)\
            .grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        Check(lf1, "保留补帧中间片", self.var_keep).grid(row=6, column=0, columnspan=2, sticky="w")
        for _v in (self.var_two, self.var_keep, self.var_vfi_on, self.var_sr_on):
            _v.trace_add("write", lambda *a: self._refresh_hint())
        lf1.columnconfigure(0, weight=1)

        srn = ["关闭"] + list(self.sr_models.keys())
        self.var_sr = tk.StringVar(value=self.setting.get("sr", srn[1] if len(srn) > 1 else "关闭"))
        ttk.Label(lf2, text="超分模型", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        Check(lf2, "启用超分", self.var_sr_on).grid(row=0, column=1, columnspan=2, sticky="e")
        ttk.Combobox(lf2, textvariable=self.var_sr, values=srn, state="readonly", width=26)\
            .grid(row=1, column=0, columnspan=3, sticky="ew", pady=(2, 6))
        ttk.Label(lf2, text="设备", style="Card.TLabel").grid(row=2, column=0, sticky="w")
        self.var_dev = tk.StringVar(value=self.setting.get("dev", "GPU"))
        ttk.Combobox(lf2, textvariable=self.var_dev, values=["GPU", "CPU"], state="readonly", width=8)\
            .grid(row=3, column=0, sticky="w", pady=(2, 4))
        ttk.Label(lf2, text="分块", style="Card.TLabel").grid(row=2, column=1, sticky="w", padx=(10, 0))
        self.var_tile = tk.StringVar(value=self.setting.get("tile", "自动"))
        ttk.Combobox(lf2, textvariable=self.var_tile, values=["自动", "512", "768", "1024"],
                     state="readonly", width=7).grid(row=3, column=1, sticky="w", padx=(10, 0), pady=(2, 4))
        ttk.Label(lf2, text="GPU = 显卡推理（DirectML），CPU 是兜底", style="Muted.TLabel")\
            .grid(row=4, column=0, columnspan=3, sticky="w")
        lf2.columnconfigure(0, weight=1)

        ttk.Label(lf3, text="编码器", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.var_enc = tk.StringVar(value=self.setting.get(
            "encoder", "H265 10bit NVENC" if "H265 10bit NVENC" in self.encoders else self.encoders[0]))
        ttk.Combobox(lf3, textvariable=self.var_enc, values=self.encoders, state="readonly", width=16)\
            .grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 6))
        ttk.Label(lf3, text="码率模式", style="Card.TLabel").grid(row=2, column=0, sticky="w")
        self.var_rate = tk.StringVar(value=self.setting.get("rate", "CRF"))
        rcb = ttk.Combobox(lf3, textvariable=self.var_rate, values=["CRF", "目标码率"],
                           state="readonly", width=9)
        rcb.grid(row=3, column=0, sticky="w", pady=(2, 4))
        rcb.bind("<<ComboboxSelected>>", lambda e: self._refresh_hint())
        self.var_q = tk.StringVar(value=str(self.setting.get("q", 16)))
        ttk.Label(lf3, text="CRF / Mbps", style="Card.TLabel").grid(row=2, column=1, sticky="w", padx=(8, 0))
        ttk.Spinbox(lf3, from_=0, to=200, textvariable=self.var_q, width=6)\
            .grid(row=3, column=1, sticky="w", padx=(8, 0), pady=(2, 4))
        ttk.Label(lf3, text="输出分辨率", style="Card.TLabel").grid(row=4, column=0, sticky="w")
        self.var_outres = tk.StringVar(value=self.setting.get("out_res_mode", "源分辨率"))
        ttk.Combobox(lf3, textvariable=self.var_outres, values=OUT_RES, state="readonly", width=12)\
            .grid(row=5, column=0, columnspan=2, sticky="w", pady=(2, 6))
        ttk.Label(lf3, text="preset", style="Card.TLabel").grid(row=6, column=0, sticky="w")
        self.var_preset_enc = tk.StringVar(value=self.setting.get("preset", "balanced"))
        ttk.Combobox(lf3, textvariable=self.var_preset_enc, values=["fast", "balanced", "slow"],
                     state="readonly", width=9).grid(row=7, column=0, sticky="w", pady=(2, 0))
        ttk.Label(lf3, text="输出格式", style="Card.TLabel").grid(row=8, column=0, sticky="w", pady=(6, 0))
        self.var_fmt = tk.StringVar(value=self.setting.get("out_format", OUT_FORMATS[0]))
        ttk.Combobox(lf3, textvariable=self.var_fmt, values=OUT_FORMATS, state="readonly", width=14)\
            .grid(row=9, column=0, columnspan=2, sticky="w", pady=(2, 0))
        lf3.columnconfigure(0, weight=1)

        # 高级
        p4 = Panel(self, self, "加速 / 高级")
        p4.pack(fill="x", padx=16, pady=6)
        adv = p4.body
        self._panels.append(p4)
        self.var_hwdec = tk.BooleanVar(value=bool(self.setting.get("hwdec", True)))
        self.var_dedup = tk.BooleanVar(value=bool(self.setting.get("dedup", False)))
        self.var_scene = tk.BooleanVar(value=bool(self.setting.get("scene", True)))
        self.var_turbo = tk.BooleanVar(value=bool(self.setting.get("turbo", False)))
        self.var_panelbg = tk.BooleanVar(value=bool(self.setting.get("panel_bg", False)))
        self.var_kenburns = tk.BooleanVar(value=bool(self.setting.get("kenburns", False)))
        self.var_kbamp = tk.StringVar(value=str(self.setting.get("kenburns_amp", 2.5)))
        self.var_start = tk.StringVar(value=str(self.setting.get("start", 0)))
        self.var_dur = tk.StringVar(value=str(self.setting.get("duration", 0)))
        self.var_fps = tk.StringVar(value=str(self.setting.get("fps", 120)))
        self.var_dupthr = tk.StringVar(value=str(self.setting.get("dup_thr", 0.06)))
        self.var_scenethr = tk.StringVar(value=str(self.setting.get("scene_thr", 8)))

        chk = tk.Frame(adv, bg=PANEL)
        chk.grid(row=0, column=0, columnspan=2, sticky="w")
        Check(chk, "面板透背景", self.var_panelbg).pack(side="left", padx=(0, 18))
        self.var_panelbg.trace_add("write", lambda *a: self._toggle_panelbg())
        Check(chk, "硬件解码", self.var_hwdec).pack(side="left", padx=(0, 18))
        Check(chk, "跳过重复帧（1拍2 / 静止画面）", self.var_dedup).pack(side="left", padx=(0, 18))
        self.frm_vfi_opts = tk.Frame(chk, bg=PANEL)
        Check(self.frm_vfi_opts, "切镜保护（硬切保留，不插帧）", self.var_scene)\
            .pack(side="left", padx=(0, 18))
        Check(self.frm_vfi_opts, "静止段微动（Ken Burns）", self.var_kenburns).pack(side="left", padx=(0, 4))
        ttk.Entry(self.frm_vfi_opts, textvariable=self.var_kbamp, width=4).pack(side="left")
        tk.Label(self.frm_vfi_opts, text="%", bg=PANEL, fg=MUTED,
                 font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(0, 18))
        self.frm_vfi_opts.pack(side="left")
        self.chk_turbo = Check(chk, "涡轮增速（只影响编码/日志）", self.var_turbo)
        self.chk_turbo.pack(side="left", padx=(0, 18))

        trow = tk.Frame(adv, bg=PANEL)
        trow.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(trow, text="输出帧率", style="Card.TLabel").pack(side="left")
        ttk.Entry(trow, textvariable=self.var_fps, width=7).pack(side="left", padx=(6, 3))
        ttk.Label(trow, text="fps（0 = 按倍率）", style="Muted.TLabel").pack(side="left", padx=(0, 16))
        ttk.Label(trow, text="时段", style="Card.TLabel").pack(side="left")
        ttk.Entry(trow, textvariable=self.var_start, width=6).pack(side="left", padx=(6, 3))
        ttk.Label(trow, text="秒起  时长", style="Muted.TLabel").pack(side="left")
        ttk.Entry(trow, textvariable=self.var_dur, width=6).pack(side="left", padx=(6, 3))
        ttk.Label(trow, text="秒（0 = 整段）", style="Muted.TLabel").pack(side="left", padx=(0, 16))
        ttk.Label(trow, text="去重阈值", style="Card.TLabel").pack(side="left")
        ttk.Entry(trow, textvariable=self.var_dupthr, width=5).pack(side="left", padx=(6, 3))
        ttk.Label(trow, text="转场阈值", style="Card.TLabel").pack(side="left", padx=(8, 0))
        ttk.Entry(trow, textvariable=self.var_scenethr, width=5).pack(side="left", padx=(6, 0))

        adv.columnconfigure(0, weight=1)

        # 操作
        act = ttk.Frame(self, padding=(16, 6, 16, 2))
        act.pack(fill="x")
        self.btn_start = ttk.Button(act, text="开始处理", style="Accent.TButton", command=self.start)
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(act, text="停止", style="Stop.TButton", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=8)
        self.var_status = tk.StringVar(value="就绪")
        tk.Label(act, textvariable=self.var_status, bg=BG, fg=MUTED, font=("Microsoft YaHei UI", 9))\
            .pack(side="left", padx=12)

        self.pb = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.pb.pack(fill="x", padx=16, pady=(2, 6))

        logf = tk.Frame(self, bg=PANEL, highlightthickness=1, highlightbackground="#333a4e")
        logf.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.log = tk.Text(logf, bg=PANEL, fg="#cfd3da", insertbackground=FG, bd=0,
                           font=FONT_M, wrap="word", state="disabled", padx=10, pady=8, height=9)
        sb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        self._refresh_hint()

    # ------------------------------------------------------------ 拖放
    def _register_drop(self, widget):
        if not _HAS_DND:
            return
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass

    def _on_drop(self, event):
        try:
            items = list(self.tk.splitlist(event.data))
        except Exception:
            items = [event.data]
        if items:
            self.var_input.set(";".join(items))
            self._refresh_files_label()

    # ------------------------------------------------------------ 输入
    def _inputs(self):
        raw = self.var_input.get().strip()
        if not raw:
            return []
        parts = [p for p in raw.replace("\n", ";").split(";") if p.strip()]
        return [os.path.normpath(p.strip().strip('"')) for p in parts]

    def _refresh_files_label(self):
        items = self._inputs()
        if not items:
            self.lbl_files.configure(text="未选择文件", fg=MUTED)
            return
        names = [os.path.basename(p.rstrip("\\/")) or p for p in items[:3]]
        more = " 等 %d 项" % len(items) if len(items) > 3 else ""
        total = 0
        for p in items:
            if os.path.isdir(p):
                try:
                    total += len([f for f in os.listdir(p) if f.lower().endswith(jobmod.VIDEO_EXT)])
                except Exception:
                    pass
            else:
                total += 1
        self.lbl_files.configure(text="已选择 %d 个视频：%s%s" % (total, "、".join(names), more), fg=FG)

    def pick_files(self):
        fs = filedialog.askopenfilenames(
            title="选择视频",
            filetypes=[("视频文件", "*.mp4 *.mkv *.mov *.avi *.flv *.wmv *.webm *.m4v *.ts"), ("全部", "*.*")])
        if fs:
            self.var_input.set(";".join(fs))
            self._refresh_files_label()

    def pick_folder(self):
        d = filedialog.askdirectory(title="选择视频文件夹")
        if d:
            self.var_input.set(d)
            self._refresh_files_label()

    def clear_inputs(self):
        self.var_input.set("")
        self._refresh_files_label()

    def pick_out(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.var_out.set(d)

    def open_out(self):
        d = self.var_out.get().strip()
        if not d:
            items = self._inputs()
            d = os.path.dirname(items[0]) if items else paths.ROOT
        if d and os.path.isdir(d):
            os.startfile(d)

    # ------------------------------------------------------------ 预设
    def _preset_names(self):
        try:
            names = [os.path.splitext(f)[0] for f in os.listdir(PRESET_DIR) if f.endswith(".json")]
        except Exception:
            names = []
        return ["默认"] + sorted(n for n in names if n != "默认")

    def _collect(self):
        return {
            "vfi_on": bool(self.var_vfi_on.get()), "sr_on": bool(self.var_sr_on.get()),
            "vfi": self.var_vfi.get(), "mult": self.var_mult.get(),
            "sr": self.var_sr.get(), "dev": self.var_dev.get(), "tile": self.var_tile.get(),
            "encoder": self.var_enc.get(), "rate": self.var_rate.get(),
            "q": self._num(self.var_q.get(), 16), "preset": self.var_preset_enc.get(),
            "hwdec": bool(self.var_hwdec.get()), "dedup": bool(self.var_dedup.get()),
            "scene": bool(self.var_scene.get()), "turbo": bool(self.var_turbo.get()),
            "fps": self._num(self.var_fps.get()), "start": self._num(self.var_start.get()),
            "duration": self._num(self.var_dur.get()),
            "dup_thr": self._num(self.var_dupthr.get(), 0.06), "scene_thr": self._num(self.var_scenethr.get(), 8),
            "kenburns": bool(self.var_kenburns.get()), "kenburns_amp": self._num(self.var_kbamp.get(), 2.5),
            "out_res_mode": self.var_outres.get(),
            "out_format": self.var_fmt.get(),
            "two_pass": bool(self.var_two.get()),
            "keep_intermediate": bool(self.var_keep.get()),
            "out": self.var_out.get(), "bg": self.setting.get("bg", ""),
            "bg_alpha": int(self._num(self.var_bgalpha.get(), 40)), "panel_bg": bool(self.var_panelbg.get()),
        }

    def save_preset(self):
        name = simpledialog.askstring("保存预设", "预设名称：",
                                      initialvalue=self.var_preset.get() or "我的预设", parent=self)
        if not name:
            return
        name = name.strip().replace("\\", "_").replace("/", "_")
        if not name:
            return
        try:
            with open(os.path.join(PRESET_DIR, name + ".json"), "w", encoding="utf-8") as f:
                json.dump(self._collect(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            return
        self.cb_preset.configure(values=self._preset_names())
        self.var_preset.set(name)
        self._append("已保存预设：%s" % name)

    def load_preset(self):
        name = self.var_preset.get()
        if name == "默认":
            self._apply_dict(paths.load_settings())
            self._append("已载入默认设置")
            return
        p = os.path.join(PRESET_DIR, name + ".json")
        if not os.path.isfile(p):
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._apply_dict(data)
            self.setting["preset_name"] = name
            paths.save_settings(self.setting)
            self._append("已载入预设：%s" % name)
        except Exception as e:
            messagebox.showerror("载入失败", str(e))

    def del_preset(self):
        name = self.var_preset.get()
        if name in ("默认", ""):
            return
        p = os.path.join(PRESET_DIR, name + ".json")
        if os.path.isfile(p) and messagebox.askyesno("删除预设", "确定删除「%s」？" % name):
            os.remove(p)
            self.cb_preset.configure(values=self._preset_names())
            self.var_preset.set("默认")

    def _apply_dict(self, d):
        def nums(var, key):
            if key in d and d[key] is not None:
                try:
                    var.set("%g" % float(d[key]))
                except Exception:
                    pass
        if "vfi_on" in d:
            self.var_vfi_on.set(bool(d["vfi_on"]))
        if "sr_on" in d:
            self.var_sr_on.set(bool(d["sr_on"]))
        if d.get("vfi") in self.vfi_map:
            self.var_vfi.set(d["vfi"])
        if d.get("mult"):
            self.var_mult.set(str(d["mult"]))
        if d.get("sr") in ["关闭"] + list(self.sr_models):
            self.var_sr.set(d["sr"])
        if d.get("dev") in ("GPU", "CPU", "DirectML"):
            self.var_dev.set("GPU" if d["dev"] in ("GPU", "DirectML") else "CPU")
        if d.get("tile"):
            self.var_tile.set(str(d["tile"]))
        if d.get("encoder") in self.encoders:
            self.var_enc.set(d["encoder"])
        if d.get("rate") in ("CRF", "目标码率"):
            self.var_rate.set(d["rate"])
        nums(self.var_q, "q")
        if d.get("preset"):
            self.var_preset_enc.set(d["preset"])
        for var, key in ((self.var_hwdec, "hwdec"), (self.var_dedup, "dedup"),
                         (self.var_scene, "scene"), (self.var_turbo, "turbo"),
                         (self.var_two, "two_pass"), (self.var_keep, "keep_intermediate")):
            if key in d:
                var.set(bool(d[key]))
        nums(self.var_fps, "fps")
        nums(self.var_start, "start")
        nums(self.var_dur, "duration")
        nums(self.var_dupthr, "dup_thr")
        nums(self.var_scenethr, "scene_thr")
        nums(self.var_kbamp, "kenburns_amp")
        if d.get("out_res_mode") in OUT_RES:
            self.var_outres.set(d["out_res_mode"])
        if d.get("out_format") in OUT_FORMATS:
            self.var_fmt.set(d["out_format"])
        if "kenburns" in d:
            self.var_kenburns.set(bool(d["kenburns"]))
        if d.get("out") is not None:
            self.var_out.set(d["out"])
        self._refresh_hint()

    # ------------------------------------------------------------ 运行
    def _refresh_hint(self):
        eng, _ = self.vfi_map.get(self.var_vfi.get(), ("none", None))
        if not self.var_vfi_on.get():
            t = "补帧已关闭：按源帧率输出"
        elif eng == "tariff":
            t = "Tariff MNN：1080p 约 0.85 帧/秒，质量优先"
        else:
            t = "未选择补帧引擎"
        rate = "按目标码率编码" if self.var_rate.get() == "目标码率" else "CRF 越小越清晰"
        sron = "" if self.var_sr_on.get() else "；超分已关闭"
        self.var_hint.set("%s\n%s%s" % (t, rate, sron))
        if self.var_two.get() and self.var_vfi_on.get() and self.var_sr_on.get():
            self.var_hint.set(self.var_hint.get() + "\n两段式：先补帧出中间片，再超分（中间片%s）" % (
                "保留" if self.var_keep.get() else "自动删除"))

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        ins = self._inputs()
        if not ins:
            messagebox.showwarning("提示", "先拖视频进来，或点「选择文件」")
            return
        if not self.ffmpeg:
            messagebox.showerror("缺少 ffmpeg", "没有找到 ffmpeg.exe")
            return
        eng, data = self.vfi_map.get(self.var_vfi.get(), ("none", None))
        if not self.var_vfi_on.get():
            eng, data = "none", None
        sr_label = self.var_sr.get()
        sr_on = bool(self.var_sr_on.get()) and sr_label != "关闭"
        fmt = FMT_MAP.get(self.var_fmt.get(), "MP4")
        is_img = vd.is_image_format(fmt)
        if eng == "none" and not sr_on and not is_img:
            messagebox.showwarning("提示", "补帧和超分都关着，没什么可做的")
            return
        mult = int(self.var_mult.get() or 2) if eng != "none" else 1
        try:
            q = int(float(self.var_q.get()))
        except Exception:
            q = 16
        bitrate_mode = self.var_rate.get() == "目标码率"
        opts = {
            "inputs": ins,
            "out_dir": self.var_out.get().strip(),
            "ffmpeg": self.ffmpeg,
            "mult": mult,
            "engine": eng,
            "encoder": self.var_enc.get(),
            "rate_mode": "bitrate" if bitrate_mode else "crf",
            "crf": q if not bitrate_mode else 16,
            "bitrate": float(q if bitrate_mode else 20),
            "preset": self.var_preset_enc.get(),
            "out_format": fmt,
            "ext": vd.VIDEO_FORMATS.get(fmt, ".mp4"),
            "sr_device": "dml" if self.var_dev.get() == "GPU" else "cpu",
            "sr_tile": 0 if self.var_tile.get() == "自动" else int(self.var_tile.get()),
            "pyd_dir": self.pyd_dir,
            "hwdecode": bool(self.var_hwdec.get()),
            "dedup": bool(self.var_dedup.get()),
            "scene_skip": bool(self.var_scene.get()),
            "fps": self._num(self.var_fps.get()),
            "dup_thr": self._num(self.var_dupthr.get(), 0.06),
            "scene_thr": self._num(self.var_scenethr.get(), 8.0),
            "turbo": bool(self.var_turbo.get()),
            "kenburns": bool(self.var_kenburns.get()),
            "kenburns_amp": self._num(self.var_kbamp.get(), 2.5),
            "out_res_mode": self.var_outres.get(),
            "two_pass": bool(self.var_two.get()) and eng != "none" and sr_on,
            "keep_intermediate": bool(self.var_keep.get()),
            "start": self._num(self.var_start.get()),
            "duration": self._num(self.var_dur.get()),
        }
        if sr_on:
            opts["sr_model"] = self.sr_models.get(sr_label)
        if eng == "tariff":
            (mt, d), _k = data
            opts["vfi_type"] = mt
            opts["vfi_dir"] = d

        self.stop_event.clear()
        self.pb.configure(value=0, maximum=100)
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.var_status.set("启动中…")
        self.t0 = time.time()
        self._samples = []
        self.cur_file = (0, len(ins), "")
        self._clear_log()
        self._append("引擎：%s ｜ 超分：%s ｜ 格式：%s ｜ 编码：%s ｜ 目标 %.0f fps ｜ 涡轮：%s%s" % (
            self.var_vfi.get() if eng != "none" else "关闭",
            (sr_label if sr_on else "关闭"),
            ("%s 图片序列" % fmt) if is_img else fmt,
            "—" if is_img else self.var_enc.get(),
            self._num(self.var_fps.get(), 0), "开" if self.var_turbo.get() else "关",
            " ｜ 两段式（先补帧→再超分）" if opts.get("two_pass") else ""))
        self.worker = threading.Thread(target=self._run_worker, args=(opts,), daemon=True)
        self.worker.start()

    def _run_worker(self, opts):
        try:
            j = jobmod.Job(opts, log=lambda s: self.q.put(("log", s)),
                           progress=lambda d, t: self.q.put(("prog", d, t)),
                           file_hook=lambda i, n, name, est: self.q.put(("file", i, n, name, est)),
                           should_stop=self.stop_event.is_set)
            code = j.run()
            self.q.put(("done", code))
        except Exception:
            self.q.put(("log", traceback.format_exc()))
            self.q.put(("done", 9))

    def stop(self):
        self.stop_event.set()
        self.var_status.set("正在停止…")

    # ------------------------------------------------------------ 消息循环
    def _poll(self):
        try:
            while True:
                m = self.q.get_nowait()
                if m[0] == "log":
                    self._append(m[1])
                elif m[0] == "file":
                    _, idx, cnt, name, est = m
                    self.cur_file = (idx, cnt, name)
                    self._samples = []
                    self.pb.configure(maximum=max(int(est), 1), value=0)
                    short = name if len(name) <= 30 else (name[:28] + "…")
                    self.var_status.set("第 %d/%d 个：%s（准备中…）" % (idx, cnt, short))
                elif m[0] == "prog":
                    d, t = m[1], m[2]
                    if t > 0:
                        self.pb.configure(maximum=t, value=min(d, t))
                        now = time.time()
                        self._samples.append((now, d))
                        while len(self._samples) > 1 and now - self._samples[0][0] > 60:
                            self._samples.pop(0)
                        t_a, d_a = self._samples[0]
                        sp = (d - d_a) / (now - t_a) if (len(self._samples) > 1 and now - t_a > 0.2) else 0.0
                        eta = (t - d) / sp if sp > 1e-6 else 0
                        idx, cnt, _name = getattr(self, "cur_file", (0, 0, ""))
                        head = ("第 %d/%d 个 · " % (idx, cnt)) if cnt else ""
                        self.var_status.set("%s进度 %d/%d（%.1f%%）  %.2f 帧/秒  剩余 %s" % (
                            head, d, t, 100.0 * d / t, sp, self._dt(eta) if sp > 1e-6 else "计算中…"))
                elif m[0] == "done":
                    self.btn_start.configure(state="normal")
                    self.btn_stop.configure(state="disabled")
                    if m[1] == 0:
                        self.pb.configure(value=self.pb["maximum"])
                        self.var_status.set("完成，用时 %s" % self._elapsed())
                    elif m[1] == 2:
                        self.var_status.set("已取消")
                    else:
                        self.var_status.set("出错，看日志")
        except queue.Empty:
            pass
        self.after(150, self._poll)

    def _elapsed(self):
        return self._dt(time.time() - self.t0 if self.t0 else 0)

    @staticmethod
    def _dt(sec):
        s = int(max(sec, 0))
        return "%d:%02d:%02d" % (s // 3600, (s % 3600) // 60, s % 60)

    def _append(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    # ------------------------------------------------------------ 其他
    def _place_window(self):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        req_w, req_h = self.winfo_reqwidth(), self.winfo_reqheight()
        if req_w > sw - 60:
            try:
                self.tk.call("tk", "scaling", 1.0)
            except Exception:
                pass
            self.update_idletasks()
            req_w, req_h = self.winfo_reqwidth(), self.winfo_reqheight()
        w = min(max(req_w + 6, 1060), sw - 30)
        h = min(max(req_h + 6, 760), sh - 60)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        self.geometry("%dx%d+%d+%d" % (w, h, x, y))
        self.minsize(min(w, 1000), min(h, 680))

    def _report_env(self):
        try:
            import onnxruntime as ort
            provs = ort.get_available_providers()
            backend = "GPU（DirectML）" if "DmlExecutionProvider" in provs else "CPU"
        except Exception:
            backend = "?"
        self._append("ffmpeg：%s" % (self.ffmpeg or "未找到"))
        self._append("补帧引擎：%s" % ", ".join(self.vfi_map.keys() or ["无"]))
        self._append("超分模型：%d 个    推理设备：%s" % (len(self.sr_models), backend))
        self._append("编码器：%s" % ", ".join(self.encoders))
        self._append("缓存/临时目录：%s（不再写 C 盘）" % paths.WORK_DIR)
        legacy = paths.legacy_cache_paths()
        if legacy:
            self._append("检测到 C 盘旧缓存 %d 处：点右上「清理缓存」可释放" % len(legacy))
        self._append("拖放：%s" % ("可用" if _HAS_DND else "不可用（请用按钮选择）"))
        if not self.sr_models:
            self._append("⚠ 没找到超分 onnx，检查 models\\sr")
        self._append("")

    def _restore(self):
        self._apply_dict(dict(self.setting))
        if self.var_vfi.get() not in self.vfi_map and self.vfi_map:
            self.var_vfi.set(list(self.vfi_map)[0])
        if self.var_enc.get() not in self.encoders and self.encoders:
            self.var_enc.set(self.encoders[0])
        if self.var_sr.get() != "关闭" and self.var_sr.get() not in self.sr_models:
            self.var_sr.set("关闭")
        if self.setting.get("input"):
            self.var_input.set(self.setting["input"])
        self._refresh_hint()
        self._refresh_files_label()

    def _on_close(self):
        try:
            data = self._collect()
            data.update({
                "input": self.var_input.get(),
                "vfi": self.var_vfi.get(), "sr": self.var_sr.get(),
                "preset_name": self.var_preset.get(),
                "bg": self.setting.get("bg", ""),
                "bg_alpha": int(self._num(self.var_bgalpha.get(), 40)), "panel_bg": bool(self.var_panelbg.get()),
            })
            paths.save_settings(data)
        except Exception:
            pass
        self.stop_event.set()
        try:
            self.attributes("-alpha", 1.0)
        except Exception:
            pass
        try:
            if getattr(self, "_bd", None) is not None:
                self._bd.destroy()
        except Exception:
            pass
        self.destroy()

    @staticmethod
    def _num(s, d=0.0):
        try:
            return float(str(s).strip() or 0)
        except Exception:
            return d


def run():
    paths.ensure_work_dirs()
    App().mainloop()























