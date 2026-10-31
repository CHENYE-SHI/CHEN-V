# -*- coding: utf-8 -*-
"""画质工厂 GUI（Qt 版）：真正的半透明面板 + 背景图。

补帧：RIFE(ncnn) / Tariff(MNN)
超分：AnimeJaNai ONNX（GPU=DirectML / CPU）
编码：NVENC / x264 / x265，可选输出分辨率
"""
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPixmap, QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QComboBox,
    QLineEdit, QSpinBox, QCheckBox, QProgressBar, QTextEdit, QVBoxLayout, QHBoxLayout,
    QGridLayout, QSizePolicy, QFileDialog, QMessageBox, QInputDialog, QScrollArea,
    QListWidget, QMenu, QSplitter, QRadioButton, QDoubleSpinBox,
)

import paths
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import envprobe
import job as jobmod
import video as vd

OUT_RES = ["源分辨率", "25%", "50%", "75%", "150%", "200%", "300%", "400%",
           "SD 480p", "HD 720p", "HD 1080p", "UHD 4K", "UHD 8K"]
# 输出格式：视频容器 / 图片序列（图片序列每部片子写一个同名子文件夹）
OUT_FORMATS = ["MP4 视频", "MKV 视频", "PNG 序列", "JPG 序列", "WEBP 序列"]
FMT_MAP = {"MP4 视频": "MP4", "MKV 视频": "MKV",
           "PNG 序列": "PNG", "JPG 序列": "JPG", "WEBP 序列": "WEBP"}
DUP_MODES = ["不优化 (0)", "时空线性化 (1)", "固定阈值去重 (2)", "去除一拍二 (3)",
             "去除一拍二与一拍三 (4)", "时空重采样 (5)", "一阶差分去重 (6)",
             "交叉重建 (7)", "前进消重 (8)", "平滑差异 (9)"]
PRESET_DIR = os.path.join(paths.APP_DIR, "presets")

QSS = """
* { font-family: 'Microsoft YaHei UI'; font-size: 13px; color: #e6e7ea; }
QMainWindow, QWidget#root { background: transparent; }
QFrame#panel {
    background-color: rgba(18, 21, 30, 45%);
    border: 1px solid rgba(110, 130, 170, 22%);
    border-radius: 10px;
}
QFrame#drop {
    background-color: rgba(18, 21, 30, 35%);
    border: 1px dashed rgba(90, 160, 255, 75%);
    border-radius: 10px;
}
QLabel { background: transparent; }
QLabel#title { font-size: 26px; font-weight: 700; }
QLabel#sub { color: #9aa3b2; font-size: 12px; }
QLabel#hint { color: #98a0ae; font-size: 12px; }
QLabel#panelTitle { color: #5aa0ff; font-weight: 700; font-size: 13px; }
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: rgba(10, 12, 20, 50%);
    border: 1px solid rgba(110, 130, 170, 25%);
    border-radius: 6px; padding: 4px 8px; min-height: 22px;
}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover { border-color: rgba(90, 160, 255, 60%); }
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background: rgba(60, 70, 95, 70%); border: none; width: 16px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background: rgba(78, 156, 245, 60%);
}
QComboBox QAbstractItemView {
    background-color: #1b1f2b; border: 1px solid #333a4e; selection-background-color: #2f6fd0;
}
QPushButton {
    background-color: rgba(37, 42, 59, 55%);
    border: 1px solid rgba(110, 130, 170, 25%);
    border-radius: 6px; padding: 6px 14px;
}
QPushButton:hover { background-color: rgba(49, 57, 90, 95%); }
QPushButton#primary {
    background-color: #4e9cf5; color: #0b1220; font-weight: 700; border: none; padding: 8px 22px;
}
QPushButton#primary:hover { background-color: #6fb2ff; }
QPushButton#stop { background-color: rgba(122, 47, 47, 90%); color: #ffe9e9; border: none; padding: 8px 18px; }
QPushButton#stop:hover { background-color: #9c3b3b; }
QCheckBox { background: transparent; spacing: 6px; }
'QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid rgba(140, 160, 200, 65%); background: rgba(10, 12, 20, 75%);
}
QCheckBox::indicator:checked {
    background: #4e9cf5; border: 1px solid #4e9cf5; image: url("{CHECKPNG}");
}'
QProgressBar {
    background-color: rgba(10, 12, 20, 45%); border: 1px solid rgba(110, 130, 170, 25%);
    border-radius: 6px; height: 14px; text-align: center; color: #cfd3da;
}
QProgressBar::chunk { background-color: #4e9cf5; border-radius: 5px; }
QTextEdit {
    background-color: rgba(10, 12, 18, 40%);
    border: 1px solid rgba(110, 130, 170, 22%); border-radius: 8px;
    font-family: Consolas, 'Microsoft YaHei UI'; font-size: 12px;
}
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: rgba(120, 140, 180, 45%); border-radius: 5px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
"""


class Backdrop(QWidget):
    """铺满窗口的背景图 + 暗色蒙版；子控件用半透明底色就能透出它"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pix = None
        self.dark = 0.42

    def set_image(self, path):
        if path and os.path.isfile(path):
            p = QPixmap(path)
            self.pix = p if not p.isNull() else None
        else:
            self.pix = None
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        r = self.rect()
        if self.pix is not None:
            scaled = self.pix.scaled(r.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x = (scaled.width() - r.width()) // 2
            y = (scaled.height() - r.height()) // 2
            p.drawPixmap(-x, -y, scaled)
            p.fillRect(r, QColor(8, 10, 16, int(255 * self.dark)))
        else:
            p.fillRect(r, QColor(21, 23, 31))


class Bar(QWidget):
    """自绘进度条：QProgressBar 在 Fusion 下会露白底，这里自己画，保证半透明"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._min, self._max, self._val = 0, 100, 0
        self.setMinimumHeight(18)
        self.setMaximumHeight(18)

    def setRange(self, a, b):
        self._min, self._max = int(a), max(int(b), 1)
        self.update()

    def setValue(self, v):
        self._val = int(v)
        self.update()

    def value(self):
        return self._val

    def maximum(self):
        return self._max

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect().adjusted(0, 2, -1, -3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(10, 12, 20, 120))
        p.drawRoundedRect(r, 6, 6)
        span = max(self._max - self._min, 1)
        frac = max(0.0, min(1.0, (self._val - self._min) / span))
        if frac > 0:
            fill = r.adjusted(1, 1, -1, -1)
            fill.setWidth(int(fill.width() * frac))
            p.setBrush(QColor(78, 156, 245, 235))
            p.drawRoundedRect(fill, 5, 5)
        p.setPen(QColor(230, 231, 234))
        f = p.font()
        f.setPointSizeF(8.5)
        p.setFont(f)
        pct = "%d%%" % int(frac * 100)
        p.drawText(self.rect(), Qt.AlignCenter, pct)
        p.end()


class Panel(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(12, 10, 12, 12)
        self.v.setSpacing(6)
        if title:
            lab = QLabel(title)
            lab.setObjectName("panelTitle")
            self.v.addWidget(lab)

    def body(self):
        return self.v


class Win(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CHEN-V · 补帧 + 超分")
        try:
            from PySide6.QtGui import QIcon
            _ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
            if os.path.isfile(_ico):
                self.setWindowIcon(QIcon(_ico))
        except Exception:
            pass
        scr = QGuiApplication.primaryScreen().availableGeometry()
        dpr = QGuiApplication.primaryScreen().devicePixelRatio() or 1.0
        # 物理像素宽 / dpr = 能放下的逻辑宽，留点边
        max_logical = int(scr.width() / dpr) - 60
        w = min(1200, max(880, max_logical))
        h = min(860, max(600, int(scr.height() / dpr) - 200))
        self.resize(w, h)
        self.move(scr.x() + max(0, (scr.width() // dpr - w) // 2),
                  scr.y() + max(0, (scr.height() - h) // 4))
        self.setAcceptDrops(True)
        self.q = queue.Queue()
        self.worker = None
        self.stop_event = threading.Event()
        self.t0 = 0.0
        self.samples = []
        self.cur_file = (0, 0, "")
        self.items = []
        self.layout_mode = "classic"
        self.setting = paths.load_settings()

        self.ffmpeg = paths.find_ffmpeg()
        self.sr_models = paths.find_sr_models()
        self.tariff_models = paths.find_tariff_models()
        self.encoders = vd.available_encoders(self.ffmpeg, envprobe.vendors()) if self.ffmpeg else ["H265"]
        self.pyd_dir = paths.find_tariff_pyd()
        # 补帧模型：本地 Tariff MNN 推理（独立 rife-ncnn-vulkan exe 已移除）
        self.vfi_map = {}
        for name, (mt, d_) in self.tariff_models.items():
            self.vfi_map[name] = ("tariff", ((mt, d_), name))
        if not self.vfi_map:
            self.vfi_map["（没有找到补帧模型）"] = ("none", None)
        os.makedirs(PRESET_DIR, exist_ok=True)

        self.root = QWidget(objectName="root")
        self.bg = Backdrop(self.root)
        self.bg.setGeometry(0, 0, self.width(), self.height())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.root.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setWidget(self.root)
        self.scroll = scroll
        self.setCentralWidget(scroll)

        self._build()
        # 缩小下拉框的最小宽度，避免布局把窗口撑出屏幕
        for _cb in self.findChildren(QComboBox):
            _cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            _cb.setMinimumContentsLength(8)
            _cb.setMaxVisibleItems(14)
            try:
                _w = max(220, _cb.sizeHint().width())
                for _i in range(_cb.count()):
                    _w = max(_w, _cb.fontMetrics().horizontalAdvance(_cb.itemText(_i)) + 40)
                _cb.view().setMinimumWidth(min(_w, 520))
            except Exception:
                pass
        for _ed in self.findChildren(QLineEdit):
            _ed.setMinimumWidth(120)
        self._restore()
        self._sync_rate_mode()
        self._sync_out_format()
        self._apply_bg(self.setting.get("bg", ""), save=False)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(150)
        self._log_env()

    # ------------------------------------------------------------ UI
    def _label(self, text, obj=None):
        l = QLabel(text)
        if obj:
            l.setObjectName(obj)
        return l

    def _combo(self, values, width=None, editable=False):
        c = QComboBox()
        c.addItems(values)
        c.setEditable(False)
        if width:
            c.setMinimumWidth(width)
        if editable:
            c.setEditable(True)
        return c

    def _build(self):
        outer = QVBoxLayout(self.root)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(8)

        # ---------------- 顶栏 ----------------
        self.box_head = QWidget()
        head = QHBoxLayout(self.box_head)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(10)
        head.addWidget(self._label("CHEN-V", "title"))
        head.addWidget(self._label("补帧 · 超分 · GPU 加速", "sub"))
        head.addStretch(1)
        head.addWidget(self._label("预设", "hint"))
        self.cb_preset = self._combo(self._preset_names())
        self.cb_preset.currentIndexChanged.connect(lambda i: self._load_preset())
        head.addWidget(self.cb_preset)
        b_save = QPushButton("保存预设")
        b_save.clicked.connect(self._save_preset)
        head.addWidget(b_save)
        b_del = QPushButton("删除预设")
        b_del.clicked.connect(self._del_preset)
        head.addWidget(b_del)
        b_bg = QPushButton("背景图")
        b_bg.clicked.connect(self._pick_bg)
        head.addWidget(b_bg)
        b_bgc = QPushButton("清除背景")
        b_bgc.clicked.connect(self._clear_bg)
        head.addWidget(b_bgc)
        b_cache = QPushButton("清理缓存")
        b_cache.clicked.connect(self._purge_cache)
        head.addWidget(b_cache)

        # ---------------- 拖放区 ----------------
        drop = QFrame(objectName="drop")
        dv = QVBoxLayout(drop)
        dv.setContentsMargins(16, 14, 16, 12)
        dv.setSpacing(8)
        self.lbl_drop = self._label("把视频文件 / 文件夹拖到这里（也可以点下面按钮）", "hint")
        self.lbl_drop.setAlignment(Qt.AlignCenter)
        self.lbl_drop.setStyleSheet("font-size: 15px; color: #b9c2d0;")
        dv.addWidget(self.lbl_drop)
        rowb = QHBoxLayout()
        rowb.addStretch(1)
        for text, fn in (("选择文件", self._pick_files), ("选择文件夹", self._pick_folder),
                         ("清空列表", self._clear_inputs)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            rowb.addWidget(b)
        rowb.addStretch(1)
        dv.addLayout(rowb)
        self.lbl_files = self._label("未选择文件", "hint")
        dv.addWidget(self.lbl_files)
        self.drop_area = None

        # ---------------- 输出目录 ----------------
        p_out = Panel("", self.root)
        g = QGridLayout()
        g.setHorizontalSpacing(8)
        g.addWidget(self._label("输出目录（留空 = 源文件目录）"), 0, 0, 1, 3)
        self.ed_out = QLineEdit()
        g.addWidget(self.ed_out, 1, 0, 1, 1)
        b1 = QPushButton("浏览…")
        b1.clicked.connect(self._pick_out)
        g.addWidget(b1, 1, 1)
        b2 = QPushButton("打开")
        b2.clicked.connect(self._open_out)
        g.addWidget(b2, 1, 2)
        g.setColumnStretch(0, 1)
        p_out.body().addLayout(g)
        self.box_out = QWidget()
        _l = QVBoxLayout(self.box_out)
        _l.setContentsMargins(0, 0, 0, 0)
        _l.addWidget(p_out)

        # ---------------- 三个面板 ----------------
        p1 = Panel("补帧（补帧模型）", self.root)
        p2 = Panel("超分", self.root)
        p3 = Panel("编码", self.root)

        g1 = QGridLayout()
        g1.setHorizontalSpacing(8)
        g1.setVerticalSpacing(6)
        self.cb_vfi = self._combo(list(self.vfi_map) or ["（无可用引擎）"])
        self.chk_vfi = QCheckBox("启用补帧")
        g1.addWidget(self._label("补帧模型"), 0, 0)
        g1.addWidget(self.chk_vfi, 0, 1, alignment=Qt.AlignRight)
        g1.addWidget(self.cb_vfi, 1, 0, 1, 2)
        # 倍率 / 输出帧率：二选一（选一个另一个就自动失效）
        self.rb_mult = QRadioButton("按倍率")
        self.rb_fps = QRadioButton("按输出帧率")
        self.rb_mult.setChecked(True)
        g1.addWidget(self.rb_mult, 2, 0)
        self.cb_mult = self._combo(["2", "3", "4", "5", "6"])
        self.cb_mult.setCurrentText("5")
        g1.addWidget(self.cb_mult, 2, 1)
        g1.addWidget(self.rb_fps, 3, 0)
        self.sp_fps = QSpinBox()
        self.sp_fps.setRange(1, 480)
        self.sp_fps.setSuffix(" fps")
        self.sp_fps.setValue(120)
        g1.addWidget(self.sp_fps, 3, 1)
        self.rb_mult.toggled.connect(self._sync_rate_mode)
        self.rb_fps.toggled.connect(self._sync_rate_mode)
        self.lbl_hint = self._label("", "hint")
        self.lbl_hint.setWordWrap(True)
        g1.addWidget(self.lbl_hint, 4, 0, 1, 2)
        # 两段式：先补帧出中间片，再单独超分（补帧 Vulkan 和超分 DirectML 不同时占卡）
        self.chk_two = QCheckBox("两段式：先补帧 → 再超分")
        self.chk_keep = QCheckBox("保留补帧中间片")
        self.chk_keep.setChecked(True)
        self.chk_two.toggled.connect(lambda c: self._refresh_hint())
        self.chk_keep.toggled.connect(lambda c: self._refresh_hint())
        g1.addWidget(self.chk_two, 5, 0, 1, 2)
        g1.addWidget(self.chk_keep, 6, 0, 1, 2)
        p1.body().addLayout(g1)
        p1.body().addStretch(1)

        import sr_ncnn
        self.sr_map = {}
        for _n, _p in self.sr_models.items():
            self.sr_map["%s（onnx）" % _n] = ("onnx", _p)
        for _label, _v in sr_ncnn.list_ncnn_sr().items():
            self.sr_map[_label] = ("ncnn", _v)
        srn = ["关闭"] + list(self.sr_map)
        g2 = QGridLayout()
        g2.setHorizontalSpacing(8)
        g2.setVerticalSpacing(6)
        self.cb_sr = self._combo(srn)
        self.chk_sr = QCheckBox("启用超分")
        g2.addWidget(self._label("超分模型"), 0, 0)
        g2.addWidget(self.chk_sr, 0, 1, 1, 2, alignment=Qt.AlignRight)
        g2.addWidget(self.cb_sr, 1, 0, 1, 3)
        g2.addWidget(self._label("设备"), 2, 0)
        self.cb_dev = self._combo(["GPU", "CPU"])
        g2.addWidget(self.cb_dev, 3, 0)
        g2.addWidget(self._label("分块"), 2, 1)
        self.cb_tile = self._combo(["自动", "512", "768", "1024"])
        g2.addWidget(self.cb_tile, 3, 1)
        g2.addWidget(self._label("GPU = 显卡推理（DirectML），CPU 是兜底", "hint"), 4, 0, 1, 3)
        p2.body().addLayout(g2)
        p2.body().addStretch(1)

        g3 = QGridLayout()
        g3.setHorizontalSpacing(8)
        g3.setVerticalSpacing(6)
        g3.addWidget(self._label("输出格式"), 0, 0, 1, 3)
        self.cb_fmt = self._combo(OUT_FORMATS)
        self.cb_fmt.currentIndexChanged.connect(lambda i: self._sync_out_format())
        g3.addWidget(self.cb_fmt, 1, 0, 1, 3)
        self.cb_enc = self._combo(self.encoders)
        g3.addWidget(self._label("编码器"), 2, 0, 1, 2)
        g3.addWidget(self.cb_enc, 3, 0, 1, 3)
        g3.addWidget(self._label("码率模式"), 4, 0)
        self.cb_rate = self._combo(["CRF", "目标码率"])
        g3.addWidget(self.cb_rate, 5, 0)
        g3.addWidget(self._label("CRF/Mbps"), 4, 1)
        self.sp_q = QSpinBox()
        self.sp_q.setRange(0, 200)
        g3.addWidget(self.sp_q, 5, 1)
        g3.addWidget(self._label("输出分辨率"), 6, 0, 1, 2)
        self.cb_outres = self._combo(OUT_RES)
        g3.addWidget(self.cb_outres, 7, 0, 1, 3)
        g3.addWidget(self._label("preset"), 8, 0)
        self.cb_preset_enc = self._combo(["fast", "balanced", "slow"])
        g3.addWidget(self.cb_preset_enc, 9, 0)
        self.lbl_fmt_hint = self._label("", "hint")
        self.lbl_fmt_hint.setWordWrap(True)
        g3.addWidget(self.lbl_fmt_hint, 10, 0, 1, 3)
        p3.body().addLayout(g3)
        p3.body().addStretch(1)

        self.box_panels = QWidget()
        row = QHBoxLayout(self.box_panels)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(p1, 3)
        row.addWidget(p2, 4)
        row.addWidget(p3, 3)

        # ---------------- 高级 ----------------
        p4 = Panel("加速 / 高级", self.root)
        g4 = QGridLayout()
        g4.setHorizontalSpacing(14)
        g4.setVerticalSpacing(6)
        self.chk_hw = QCheckBox("硬件解码")
        self.chk_dedup = QCheckBox("前进消重（去重复帧·1拍2）")
        self.chk_dedup.setChecked(True)
        self.chk_scene = QCheckBox("切镜保护（硬切保留）")
        self.chk_turbo = QCheckBox("涡轮增速（只影响编码/日志）")
        self.chk_cut_out = QCheckBox("输出转场帧")
        self.chk_cut_out.setChecked(True)
        self.chk_cut_blend = QCheckBox("转场使用帧混合")
        self.chk_cut_blend.setChecked(True)
        self.chk_cut_extrap = QCheckBox("转场外插")
        hb = QHBoxLayout()
        for w in (self.chk_hw, self.chk_dedup, self.chk_scene,
                  self.chk_cut_out, self.chk_cut_blend, self.chk_cut_extrap,
                  self.chk_turbo):
            hb.addWidget(w)
        hb.addStretch(1)
        g4.addLayout(hb, 0, 0, 1, 6)

        g4.addWidget(self._label("时段"), 1, 0)
        self.sp_start = QSpinBox()
        self.sp_start.setRange(0, 99999)
        g4.addWidget(self.sp_start, 1, 1)
        g4.addWidget(self._label("秒起  时长"), 1, 2)
        self.sp_dur = QSpinBox()
        self.sp_dur.setRange(0, 99999)
        g4.addWidget(self.sp_dur, 1, 3)
        g4.addWidget(self._label("去重阈值"), 2, 0)
        self.sp_dup = QDoubleSpinBox()
        self.sp_dup.setRange(0.0, 1.0)
        self.sp_dup.setDecimals(2)
        self.sp_dup.setSingleStep(0.01)
        self.sp_dup.setValue(0.06)
        g4.addWidget(self.sp_dup, 2, 1)
        g4.addWidget(self._label("帧差阈值：0.03~0.10 之间，越小越严（默认 0.06）", "hint"), 2, 2, 1, 2)
        g4.addWidget(self._label("转场阈值"), 2, 4)
        self.sp_scene = QSpinBox()
        self.sp_scene.setRange(0, 255)
        g4.addWidget(self.sp_scene, 2, 5)

        g4.setColumnStretch(6, 1)
        p4.body().addLayout(g4)
        self.panel_adv = p4
        self.adv_frame_vfi = [self.chk_scene]
        self.box_adv = QWidget()
        _l = QVBoxLayout(self.box_adv)
        _l.setContentsMargins(0, 0, 0, 0)
        _l.addWidget(p4)

        # ---------------- 运行区 ----------------
        self.box_run = QWidget()
        rl = QVBoxLayout(self.box_run)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        act = QHBoxLayout()
        act.setSpacing(10)
        self.btn_start = QPushButton("开始处理")
        self.btn_start.setObjectName("primary")
        self.btn_start.clicked.connect(self._start)
        act.addWidget(self.btn_start)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setObjectName("stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        act.addWidget(self.btn_stop)
        self.lbl_status = self._label("就绪", "sub")
        act.addWidget(self.lbl_status)
        act.addStretch(1)
        rl.addLayout(act)
        self.pb = Bar()
        self.pb.setRange(0, 100)
        self.pb.setValue(0)
        rl.addWidget(self.pb)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.viewport().setStyleSheet("background: transparent;")
        rl.addWidget(self.log, 1)

        # ---------------- 视频列表（高级布局用） ----------------
        self.box_files = Panel("视频列表（可拖入 / 右键操作）", self.root)
        self.list_files = QListWidget()
        self.list_files.setSelectionMode(QListWidget.ExtendedSelection)
        self.list_files.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_files.customContextMenuRequested.connect(self._file_menu)
        self.list_files.setAlternatingRowColors(True)
        # 调色板兜底：背景图很亮时，隔行浅色 + 浅色文字会让文件名列「看不见」
        _pal = self.list_files.palette()
        _pal.setColor(QPalette.Base, QColor(12, 15, 22, 235))
        _pal.setColor(QPalette.AlternateBase, QColor(26, 30, 42, 235))
        _pal.setColor(QPalette.Text, QColor("#e6e7ea"))
        _pal.setColor(QPalette.Highlight, QColor("#2f6fd0"))
        _pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        self.list_files.setPalette(_pal)
        self.list_files.setStyleSheet(
            "QListWidget{background:rgba(10,12,20,215);alternate-background-color:rgba(25,29,40,215);"
            "border:1px solid rgba(110,130,170,25%);border-radius:8px;color:#e6e7ea;}"
            "QListWidget::item{padding:4px 6px;border-bottom:1px solid rgba(110,130,170,20%);}"
            "QListWidget::item:selected{background:#2f6fd0;color:#ffffff;}")
        self.list_files.setMinimumWidth(220)
        self.box_files.body().addWidget(self.list_files, 1)
        fb = QHBoxLayout()
        fb.setSpacing(6)
        for text, fn in (("选择文件", self._pick_files), ("选择文件夹", self._pick_folder),
                         ("选择全部", self._select_all), ("删除选中", self._del_selected),
                         ("清空", self._clear_inputs)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            fb.addWidget(b)
        self.box_files.body().addLayout(fb)
        self.lbl_fcount = self._label("共 0 个", "hint")
        self.box_files.body().addWidget(self.lbl_fcount)

        # ---------------- 组装 ----------------
        outer.addWidget(self.box_head)
        self.body = QWidget()
        outer.addWidget(self.body, 1)
        bl = QHBoxLayout(self.body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(8)
        for _w in (self.box_out, self.box_panels, self.box_adv, self.box_run):
            lv.addWidget(_w)
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(6)
        split.addWidget(left)
        split.addWidget(self.box_files)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([700, 420])
        self.split = split
        bl.addWidget(split)
        self.box_files.setVisible(True)

        self.cb_vfi.currentIndexChanged.connect(lambda i: self._refresh_hint())
        self.cb_sr.currentIndexChanged.connect(lambda i: self._refresh_hint())
        self.chk_vfi.toggled.connect(lambda c: self._refresh_hint())
        self.chk_sr.toggled.connect(lambda c: self._refresh_hint())

    # ------------------------------------------------------------ 视频列表
    def _refresh_list(self):
        if not hasattr(self, "list_files"):
            return
        self.list_files.clear()
        for p in getattr(self, "items", []):
            self.list_files.addItem(p)
        try:
            self.lbl_fcount.setText("共 %d 个" % len(getattr(self, "items", [])))
        except Exception:
            pass

    def _select_all(self):
        self.list_files.selectAll()

    def _del_selected(self):
        rows = sorted({self.list_files.row(i) for i in self.list_files.selectedItems()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self.items):
                self.items.pop(r)
        self._refresh_list()
        self._update_files_label()

    def _file_menu(self, pos):
        it = self.list_files.itemAt(pos)
        if it is None:
            return
        path = it.text()
        m = QMenu(self)
        a_open = m.addAction("打开所在文件夹")
        a_info = m.addAction("信息")
        a_copy = m.addAction("复制路径")
        m.addSeparator()
        a_del = m.addAction("从列表删除")
        act = m.exec(self.list_files.mapToGlobal(pos))
        if act is None:
            return
        if act == a_open:
            d = path if os.path.isdir(path) else os.path.dirname(path)
            if os.path.isdir(d):
                os.startfile(d)
        elif act == a_info:
            try:
                info = vd.probe(self.ffmpeg, path)
                QMessageBox.information(self, "信息", "%s\n%d x %d  %.3f fps  %.2f 秒" % (
                    os.path.basename(path), info["width"], info["height"], info["fps"], info["duration"]))
            except Exception as e:
                QMessageBox.warning(self, "信息", str(e))
        elif act == a_copy:
            QApplication.clipboard().setText(path)
        elif act == a_del:
            r = self.list_files.row(it)
            if 0 <= r < len(self.items):
                self.items.pop(r)
            self._refresh_list()
            self._update_files_label()

    # ------------------------------------------------------------ 背景
    def resizeEvent(self, e):
        try:
            self.bg.setGeometry(0, 0, self.root.width(), self.root.height())
        except Exception:
            self.bg.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(e)

    def _pick_bg(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择背景图片", "",
                                           "图片 (*.png *.jpg *.jpeg *.webp *.bmp);;全部 (*.*)")
        if f:
            self._apply_bg(f)

    def _clear_bg(self):
        self._apply_bg("", save=True)

    def _purge_cache(self):
        if self.worker and self.worker.is_alive():
            QMessageBox.warning(self, "清理缓存", "任务正在跑，等它结束再清理")
            return
        paths.ensure_work_dirs()
        size = paths.dir_size(paths.TEMP_DIR) + paths.dir_size(paths.CACHE_DIR)
        for p in paths.legacy_cache_paths():
            size += paths.dir_size(p)
        msg = ("将删除补帧缓存和临时抽帧文件（含 C 盘旧缓存，约 %.0f MB）。\n"
               "补帧缓存删掉后，下次要重新插帧。继续？" % (size / 1048576.0))
        if QMessageBox.question(self, "清理缓存", msg) != QMessageBox.Yes:
            return
        freed = paths.purge_caches()
        self._append("已清理缓存：%.0f MB（缓存目录 %s）" % (freed / 1048576.0, paths.CACHE_DIR))

    def _apply_bg(self, path, save=True):
        self.bg.set_image(path)
        if save:
            self.setting["bg"] = path
            paths.save_settings(self.setting)
        if not path:
            self.bg.pix = None
            self.bg.update()

    # ------------------------------------------------------------ 拖放
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if files:
            self._set_inputs(files, append=True)

    # ------------------------------------------------------------ 输入
    def _set_inputs(self, items, append=True):
        base = list(getattr(self, "items", [])) if append else []
        for p in items:
            p = p.strip().strip('"')
            if p and p not in base:
                base.append(p)
        self.items = base
        self._refresh_list()
        self._update_files_label()

    def _update_files_label(self):
        """只更新右侧列表的计数（拖放区已经去掉，不再有单独的文字标签）"""
        items = getattr(self, "items", [])
        try:
            self.lbl_fcount.setText("共 %d 个" % len(items))
        except Exception:
            pass

    def _pick_files(self):
        fs, _ = QFileDialog.getOpenFileNames(
            self, "选择视频", "", "视频 (*.mp4 *.mkv *.mov *.avi *.flv *.wmv *.webm *.m4v *.ts);;全部 (*.*)")
        if fs:
            self._set_inputs(fs)

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "选择视频文件夹")
        if d:
            self._set_inputs([d])

    def _clear_inputs(self):
        self.items = []
        self._refresh_list()
        self._update_files_label()

    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.ed_out.setText(d)

    def _open_out(self):
        d = self.ed_out.text().strip()
        if not d and getattr(self, "_inputs_list", None):
            d = os.path.dirname(self._inputs_list[0])
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
            "vfi_on": self.chk_vfi.isChecked(), "sr_on": self.chk_sr.isChecked(),
            "vfi": self.cb_vfi.currentText(), "mult": self.cb_mult.currentText(),
            "sr": self.cb_sr.currentText(), "dev": self.cb_dev.currentText(),
            "tile": self.cb_tile.currentText(), "encoder": self.cb_enc.currentText(),
            "rate": self.cb_rate.currentText(), "q": self.sp_q.value(),
            "preset": self.cb_preset_enc.currentText(),
            "hwdec": self.chk_hw.isChecked(), "dedup": self.chk_dedup.isChecked(),
            "scene": self.chk_scene.isChecked(),
            "cut_out": self.chk_cut_out.isChecked(),
            "cut_blend": self.chk_cut_blend.isChecked(),
            "cut_extrap": self.chk_cut_extrap.isChecked(), "turbo": self.chk_turbo.isChecked(),
            "rate_mode": "fps" if self.rb_fps.isChecked() else "mult",
            "fps": float(self.sp_fps.value()) if self.rb_fps.isChecked() else 0.0,
            "start": float(self.sp_start.value()),
            "duration": float(self.sp_dur.value()),
            "dup_thr": float(self.sp_dup.value()), "scene_thr": float(self.sp_scene.value()),
            "out_res_mode": self.cb_outres.currentText(),
            "out_format": self.cb_fmt.currentText(),
            "two_pass": self.chk_two.isChecked(),
            "keep_intermediate": self.chk_keep.isChecked(),
            "out": self.ed_out.text(), "bg": self.setting.get("bg", ""),
        }

    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "保存预设", "预设名称：",
                                        text=self.cb_preset.currentText() or "我的预设")
        if not ok or not name.strip():
            return
        name = name.strip().replace("\\", "_").replace("/", "_")
        try:
            with open(os.path.join(PRESET_DIR, name + ".json"), "w", encoding="utf-8") as f:
                json.dump(self._collect(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", "%s: %s" % (type(e).__name__, e))
            return
        cur = self.cb_preset.currentText()
        self.cb_preset.blockSignals(True)
        self.cb_preset.clear()
        self.cb_preset.addItems(self._preset_names())
        self.cb_preset.setCurrentText(name)
        self.cb_preset.blockSignals(False)
        self._append("已保存预设：%s" % name)

    def _load_preset(self):
        name = self.cb_preset.currentText()
        if name == "默认":
            self._apply_dict(paths.load_settings())
            return
        p = os.path.join(PRESET_DIR, name + ".json")
        if not os.path.isfile(p):
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                self._apply_dict(json.load(f))
            self._append("已载入预设：%s" % name)
        except Exception as e:
            QMessageBox.critical(self, "载入失败", "%s: %s" % (type(e).__name__, e))

    def _del_preset(self):
        name = self.cb_preset.currentText()
        if name in ("默认", ""):
            return
        p = os.path.join(PRESET_DIR, name + ".json")
        if os.path.isfile(p) and QMessageBox.question(self, "删除预设", "确定删除「%s」？" % name) == QMessageBox.Yes:
            os.remove(p)
            self.cb_preset.clear()
            self.cb_preset.addItems(self._preset_names())

    def _apply_dict(self, d):
        def set_combo(cb, val):
            if val is None:
                return
            i = cb.findText(str(val))
            if i >= 0:
                cb.setCurrentIndex(i)
        if "vfi_on" in d:
            self.chk_vfi.setChecked(bool(d["vfi_on"]))
        if "sr_on" in d:
            self.chk_sr.setChecked(bool(d["sr_on"]))
        set_combo(self.cb_vfi, d.get("vfi"))
        set_combo(self.cb_mult, d.get("mult"))
        set_combo(self.cb_sr, d.get("sr"))
        set_combo(self.cb_dev, d.get("dev") if d.get("dev") in ("GPU", "CPU") else "GPU")
        set_combo(self.cb_tile, d.get("tile"))
        set_combo(self.cb_enc, d.get("encoder"))
        set_combo(self.cb_rate, d.get("rate"))
        set_combo(self.cb_preset_enc, d.get("preset"))
        set_combo(self.cb_outres, d.get("out_res_mode"))
        set_combo(self.cb_fmt, d.get("out_format"))
        for w, k in ((self.chk_hw, "hwdec"), (self.chk_dedup, "dedup"), (self.chk_scene, "scene"),
                     (self.chk_turbo, "turbo"), (self.chk_cut_out, "cut_out"),
                     (self.chk_cut_blend, "cut_blend"), (self.chk_cut_extrap, "cut_extrap"),
                     (self.chk_two, "two_pass"), (self.chk_keep, "keep_intermediate")):
            if k in d:
                w.setChecked(bool(d[k]))
        try:
            if self.sp_fps.value() <= 1:
                self.sp_fps.setValue(120)
        except Exception:
            pass
        if d.get("rate_mode") == "fps":
            self.rb_fps.setChecked(True)
        elif d.get("rate_mode") == "mult":
            self.rb_mult.setChecked(True)
        for w, k, f in ((self.sp_q, "q", 16), (self.sp_fps, "fps", 120), (self.sp_start, "start", 0),
                        (self.sp_dur, "duration", 0), (self.sp_scene, "scene_thr", 8)):
            if k in d:
                try:
                    w.setValue(int(float(d[k])))
                except Exception:
                    w.setValue(f)
        if "dup_thr" in d:
            try:
                v = float(d["dup_thr"])
                if v > 1.0:          # 老设置是 ×0.01 存的（6 = 0.06）
                    v = v / 100.0
                self.sp_dup.setValue(max(0.0, min(1.0, v)))
            except Exception:
                self.sp_dup.setValue(0.06)
        if d.get("out") is not None:
            self.ed_out.setText(str(d["out"]))
        self._refresh_hint()
        self._sync_out_format()

    def _restore(self):
        d = dict(self.setting)
        if self.setting.get("scene_thr") in (40, 40.0, "40", "40.0"):
            d["scene_thr"] = 8
            d["scene"] = True
        self._apply_dict(d)

    # ------------------------------------------------------------ 运行
    def _cur_fmt(self):
        return FMT_MAP.get(self.cb_fmt.currentText(), "MP4")

    def _sync_out_format(self, *_):
        img = vd.is_image_format(self._cur_fmt())
        # 图片序列不走编码器，码率 / preset / 涡轮这些关掉免得误导
        for w in (self.cb_enc, self.cb_rate, self.sp_q, self.cb_preset_enc, self.chk_turbo):
            w.setEnabled(not img)
        self.lbl_fmt_hint.setText(
            "图片序列：写入同名子文件夹（frame_00000001.png…），不含音轨；"
            "PNG 最清晰也最大、JPG/WEBP 小很多；编码器 / 码率不生效。"
            if img else
            "视频：音轨原样复制；NVENC 几乎不吃 CPU，x265 软编才是瓶颈。")

    def _sync_rate_mode(self, *_):
        # 0.25 偏激进（容易把真实变化当重复帧），这里只在日志里提示

        by_fps = self.rb_fps.isChecked()
        self.sp_fps.setEnabled(by_fps)
        self.cb_mult.setEnabled(not by_fps)
        paths.save_settings(self.setting)
        self._refresh_hint()

    def _refresh_hint(self):
        eng, _ = self.vfi_map.get(self.cb_vfi.currentText(), ("none", None))
        vfi_on = self.chk_vfi.isChecked()
        sr_on = self.chk_sr.isChecked() and self.cb_sr.currentText() != "关闭"
        if not vfi_on:
            t = "补帧已关闭：只做超分 / 转码，按源帧率输出（「输出帧率」不生效）"
        elif eng == "tariff":
            t = "Tariff MNN：1080p 约 0.85 帧/秒，质量优先"
        else:
            t = "未选择补帧引擎"
        lines = [t]
        if vfi_on:
            lines.append("输出帧率以「输出帧率」为准（0 = 按倍率）")
        if (getattr(self, "chk_two", None) is not None and self.chk_two.isChecked()
                and vfi_on and sr_on):
            lines.append("两段式：第 1 段只补帧出中间片（MKV），第 2 段再超分；中间片%s" % (
                "保留" if self.chk_keep.isChecked() else "自动删除"))
        self.lbl_hint.setText("\n".join(lines))

    def _start(self):
        if self.worker and self.worker.is_alive():
            return
        ins = list(getattr(self, "items", []))
        if not ins:
            QMessageBox.warning(self, "提示", "先拖视频进来，或点「选择文件」")
            return
        eng, data = self.vfi_map.get(self.cb_vfi.currentText(), ("none", None))
        if not self.chk_vfi.isChecked():
            eng, data = "none", None
        sr_label = self.cb_sr.currentText()
        sr_on = self.chk_sr.isChecked() and sr_label != "关闭"
        fmt = self._cur_fmt()
        is_img = vd.is_image_format(fmt)
        if eng == "none" and not sr_on and not is_img:
            QMessageBox.warning(self, "提示", "补帧和超分都关着，没什么可做的")
            return
        by_fps = self.rb_fps.isChecked()
        mult = 1 if by_fps else (int(self.cb_mult.currentText()) if eng != "none" else 1)
        q = self.sp_q.value()
        bitrate_mode = self.cb_rate.currentText() == "目标码率"
        opts = {
            "inputs": ins,
            "out_dir": self.ed_out.text().strip(),
            "ffmpeg": self.ffmpeg,
            "mult": mult,
            "engine": eng,
            "encoder": self.cb_enc.currentText(),
            "rate_mode": "bitrate" if bitrate_mode else "crf",
            "crf": q if not bitrate_mode else 16,
            "bitrate": float(q if bitrate_mode else 20),
            "preset": self.cb_preset_enc.currentText(),
            "out_format": fmt,
            "ext": vd.VIDEO_FORMATS.get(fmt, ".mp4"),
            "two_pass": self.chk_two.isChecked() and eng != "none" and sr_on,
            "keep_intermediate": self.chk_keep.isChecked(),
            "sr_device": "dml" if self.cb_dev.currentText() == "GPU" else "cpu",
            "sr_tile": 0 if self.cb_tile.currentText() == "自动" else int(self.cb_tile.currentText()),
            "pyd_dir": self.pyd_dir,
            "hwdecode": self.chk_hw.isChecked(),
            "dedup": self.chk_dedup.isChecked(),
            "scene_skip": self.chk_scene.isChecked(),
            "cut_out": self.chk_cut_out.isChecked(),
            "cut_blend": self.chk_cut_blend.isChecked(),
            "cut_extrap": self.chk_cut_extrap.isChecked(),
            "fps": float(self.sp_fps.value()) if by_fps else 0.0,
            "dup_thr": float(self.sp_dup.value()),
            "scene_thr": float(self.sp_scene.value()),
            "turbo": self.chk_turbo.isChecked(),
            "out_res_mode": self.cb_outres.currentText(),
            "start": float(self.sp_start.value()),
            "duration": float(self.sp_dur.value()),
        }
        if sr_on:
            _eng, _val = self.sr_map.get(sr_label, ("onnx", None))
            if _eng == "onnx":
                opts["sr_model"] = _val
            else:
                opts["sr_ncnn"] = _val
        if eng == "tariff":
            (mt, d_), _k = data
            opts["vfi_type"] = mt
            opts["vfi_dir"] = d_

        self.stop_event.clear()
        self.pb.setRange(0, 100)
        self.pb.setValue(0)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.lbl_status.setText("启动中…")
        self.t0 = time.time()
        self.samples = []
        self.cur_file = (0, len(ins), "")
        self.log.clear()
        self._append("引擎：%s ｜ 超分：%s ｜ 输出格式：%s ｜ 编码：%s ｜ 分辨率：%s ｜ 目标 %.0f fps%s" % (
            self.cb_vfi.currentText() if eng != "none" else "关闭",
            sr_label if sr_on else "关闭",
            ("%s 图片序列" % fmt) if is_img else fmt,
            "—" if is_img else self.cb_enc.currentText(),
            self.cb_outres.currentText(), float(self.sp_fps.value()),
            " ｜ 两段式（先补帧→再超分）" if opts.get("two_pass") else ""))
        self.worker = threading.Thread(target=self._worker, args=(opts,), daemon=True)
        self.worker.start()

    def _worker(self, opts):
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

    def _stop(self):
        self.stop_event.set()
        self.lbl_status.setText("正在停止…")

    def _poll(self):
        try:
            if self.bg.size() != self.root.size():
                self.bg.setGeometry(0, 0, self.root.width(), self.root.height())
        except Exception:
            pass
        try:
            while True:
                m = self.q.get_nowait()
                if m[0] == "log":
                    self._append(m[1])
                elif m[0] == "file":
                    _, idx, cnt, name, est = m
                    self.cur_file = (idx, cnt, name)
                    self.samples = []
                    self.pb.setRange(0, max(int(est), 1))
                    self.pb.setValue(0)
                    short = name if len(name) <= 30 else (name[:28] + "…")
                    self.lbl_status.setText("第 %d/%d 个：%s（准备中…）" % (idx, cnt, short))
                elif m[0] == "prog":
                    d, t = m[1], m[2]
                    if t > 0:
                        self.pb.setRange(0, t)
                        self.pb.setValue(min(d, t))
                        now = time.time()
                        self.samples.append((now, d))
                        while len(self.samples) > 1 and now - self.samples[0][0] > 60:
                            self.samples.pop(0)
                        ta, da = self.samples[0]
                        sp = (d - da) / (now - ta) if (len(self.samples) > 1 and now - ta > 0.2) else 0
                        eta = (t - d) / sp if sp > 1e-6 else 0
                        idx, cnt, _name = getattr(self, "cur_file", (0, 0, ""))
                        head = ("第 %d/%d 个 · " % (idx, cnt)) if cnt else ""
                        self.lbl_status.setText("%s进度 %d/%d（%.1f%%） %.2f 帧/秒 剩余 %s" % (
                            head, d, t, 100.0 * d / t, sp, self._dt(eta) if sp > 0 else "计算中…"))
                elif m[0] == "done":
                    self.btn_start.setEnabled(True)
                    self.btn_stop.setEnabled(False)
                    if m[1] == 0:
                        self.pb.setValue(self.pb.maximum())
                        self.lbl_status.setText("完成，用时 %s" % self._dt(time.time() - self.t0))
                    elif m[1] == 2:
                        self.lbl_status.setText("已取消")
                    else:
                        self.lbl_status.setText("出错，看日志")
        except queue.Empty:
            pass

    def _dt(self, sec):
        s = int(max(sec, 0))
        return "%d:%02d:%02d" % (s // 3600, (s % 3600) // 60, s % 60)

    def _append(self, text):
        self.log.append(text.rstrip())
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _log_env(self):
        try:
            import onnxruntime as ort
            provs = ort.get_available_providers()
            if "CUDAExecutionProvider" in provs:
                backend = "GPU（CUDA）"
            elif "DmlExecutionProvider" in provs:
                backend = "GPU（DirectML）"
            else:
                backend = "CPU"
        except Exception:
            backend = "?"
        self._append("ffmpeg：%s" % (self.ffmpeg or "未找到"))
        self._append("补帧引擎：%s" % ", ".join(self.vfi_map) if self.vfi_map else "无")
        self._append("超分模型：%d 个    推理设备：%s" % (len(self.sr_models), backend))
        self._append("编码器：%s" % ", ".join(self.encoders))
        self._append("缓存/临时目录：%s（不再写 C 盘）" % paths.WORK_DIR)
        legacy = paths.legacy_cache_paths()
        if legacy:
            self._append("检测到 C 盘旧缓存 %d 处：点右上「清理缓存」可释放" % len(legacy))
        if not self.sr_models:
            self._append("⚠ 没找到超分 onnx，检查 models\\sr")

    def closeEvent(self, e):
        # 关窗口时先把 CHEN/ffmpeg 子进程收掉，免得后台还在跑
        try:
            if self.worker and self.worker.is_alive():
                self.stop_event.set()
                self.worker.join(timeout=4)
        except Exception:
            pass
        try:
            data = self._collect()
            data["preset_name"] = self.cb_preset.currentText()
            data["bg"] = self.setting.get("bg", "")
            paths.save_settings(data)
        except Exception:
            pass
        self.stop_event.set()
        super().closeEvent(e)


def _make_check_png():
    """QSS 画不了对勾：先生成一张 16x16 白色对勾图，给 indicator 用"""
    home = paths.WORK_DIR
    os.makedirs(home, exist_ok=True)
    out = os.path.join(home, "check.png")
    if os.path.isfile(out):
        return out
    pm = QPixmap(16, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = p.pen()
    pen.setColor(QColor("#ffffff"))
    pen.setWidthF(2.2)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.drawLine(4, 9, 7, 12)
    p.drawLine(7, 12, 12, 4)
    p.end()
    pm.save(out, "PNG")
    return out


def run():
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CHEN.V.VideoFactory")
    except Exception:
        pass
    paths.ensure_work_dirs()
    app = QApplication.instance() or QApplication([])
    try:
        from PySide6.QtGui import QIcon
        _ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.isfile(_ico):
            app.setWindowIcon(QIcon(_ico))
    except Exception:
        pass
    try:
        app.setStyle("Fusion")
    except Exception:
        pass
    try:
        check = _make_check_png().replace("\\", "/")
        qss = QSS.replace("{CHECKPNG}", check)
    except Exception:
        qss = QSS.replace(' image: url("{CHECKPNG}");', "").replace("{CHECKPNG}", "")
    app.setStyleSheet(qss)
    w = Win()
    w.showMaximized()
    return app.exec()







