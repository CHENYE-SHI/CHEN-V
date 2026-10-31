# -*- coding: utf-8 -*-
"""CHEN-V 界面：左侧导航 + 创建增强任务 + 批量队列 + 进度 / 格式转换 / 性能测试 / 设置。

底层仍然复用 job.py 的补帧+超分流水线；图片超分、格式转换、GPU 测试是本界面新加的入口。
"""
import json
import glob
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
import atexit


import i18n as _i18n
import updater

# numpy（~0.1s）和 PIL（~0.1s）只有处理任务时才用到，没必要在启动路径上付这笔钱：
# 一开始就 import 的话，过渡页会在 "import gui_main" 这一步定住两三百毫秒。
_NP = None
_PIL = None


def _np_pil():
    """按需加载 numpy / PIL（只加载一次，之后直接用返回的对象）。"""
    global _NP, _PIL
    if _NP is None:
        import numpy as _n
        from PIL import Image as _i
        _NP, _PIL = _n, _i
    return _NP, _PIL

from PySide6.QtCore import Qt, QTimer, QSize, QRectF, Signal
from PySide6.QtGui import (QColor, QIcon, QPixmap, QFont, QFontDatabase, QPainter,
                           QPen, QBrush)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QComboBox,
    QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox, QProgressBar, QTextEdit,
    QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget, QFileDialog,
    QMessageBox, QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView,
    QListWidget, QListWidgetItem, QButtonGroup, QSizePolicy, QAbstractItemView,
    QSplitter, QRadioButton, QSlider, QColorDialog, QInputDialog,
    QGraphicsDropShadowEffect, QDialog,
)

import paths
import procutil
import envprobe
import job as jobmod
import video as vd
import sr as srmod
import sr_ncnn
import kernel_backend

def _app_font(fam, size=10):
    """应用字体：只给单一字体族。

    这里刻意不挂第二字体族（setFamilies 会让每次字体度量先建整条回退链，
    实测首个控件就要 0.5~0.9s）。UI 里用到的图标字符已全部换成微软雅黑自带的
    字形（◆ ◎ → ≡ ◇ ■ ⊙ ☆ ↓ △ ——都在雅黑 cmap 里），既不用回退链，也不会
    触发「为找不到的字形扫遍系统字体」那条慢路径（单个字符约 0.45~0.8s）。
    换图标前请先用 work/_w13.py 单进程实测一下该字符的首次绘制成本。
    """
    return QFont(fam, size)


def _tl(text):
    """弹窗文字：按当前界面语言翻译；未收录的原文原样返回。"""
    return _i18n.tr(text)


def _cb_val(cb, default=""):
    """取下拉框的原始值。

    选项显示文本会跟随界面语言变化，但 itemData 恒为简体中文原文，
    业务逻辑（模型匹配、设置存取、格式判断）一律读这里，避免切语言后失效。
    """
    d = cb.currentData()
    if d is None or d == "":
        d = cb.currentText()
    return d if d not in (None, "") else default


def _tl_combo_name(v):
    """下拉项名称翻译。

    部分名称是「基础名 + （ncnn 内核）」拼接出来的，整串查不到译文，
    这里把后缀拆开分别翻译再拼回。
    """
    _suf = "（ncnn 内核）"
    if isinstance(v, str) and v.endswith(_suf):
        return _tl(v[:-len(_suf)]) + _tl(_suf)
    return _tl(v)


def _fill_combo(cb, values, current=None):
    """按当前语言填充下拉框：显示文本走翻译，itemData 保留中文原文。"""
    cb.blockSignals(True)
    cb.clear()
    for v in values:
        cb.addItem(_tl_combo_name(v), v)
    if current is not None:
        i = cb.findData(current)
        if i >= 0:
            cb.setCurrentIndex(i)
    cb.blockSignals(False)
    # 标记：只有「显示文本是中文原文、data 存原文」的下拉才参与切语言重刷，
    # 避免把语言选择框（data 是 zh-CN/en 这类代码）也当成译文项处理。
    cb.setProperty("i18n_combo", True)
    return cb


def _combo_select(cb, val):
    """按中文原文选中下拉项：优先 itemData，其次显示文本（兼容没有 data 的下拉框）。"""
    v = str(val)
    i = cb.findData(v)
    if i < 0:
        i = cb.findText(v)
    if i >= 0:
        cb.setCurrentIndex(i)
    return i


def _i18n_label(text, key, object_name="hint", wrap=True):
    """长段落标签：用稳定标识（如 about.disclaimer.1）取译文，切语言时按标识重取。

    直接把整段中文当 key 会因标点差异匹配失败，所以把标识存在控件属性里。
    """
    lb = QLabel(_i18n.kv(key, text), objectName=object_name)
    lb.setProperty("i18n_key", key)
    lb.setProperty("i18n_src", text)
    if wrap:
        lb.setWordWrap(True)
    return lb


APP_NAME = "CHEN-V"
APP_VERSION = "V1.00"
BUILD = "2026.10.28"
SETTINGS_FILE = os.path.join(paths.APP_DIR, "settings_qt.json")
PRESETS_DIR = os.path.join(paths.APP_DIR, "presets")

VIDEO_EXT = jobmod.VIDEO_EXT
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")

MODE_IMAGE = "图片超分"
MODE_SR = "视频超分"
MODE_VFI = "视频补帧"
MODE_BOTH = "超分并补帧"
MODES = [MODE_IMAGE, MODE_SR, MODE_VFI, MODE_BOTH]

OUT_RES = ["源分辨率", "50%", "75%", "150%", "200%", "300%", "400%",
           "HD 720p", "HD 1080p", "UHD 2K", "UHD 4K"]
OUT_FMT = ["MP4", "MKV", "MOV", "GIF", "WEBP", "PNG 序列", "JPG 序列", "WEBP 序列"]
FMT_KEYS = {"MP4": "MP4", "MKV": "MKV", "MOV": "MOV", "GIF": "GIF", "WEBP": "WEBP",
            "PNG 序列": "PNG", "JPG 序列": "JPG", "WEBP 序列": "WEBP_IMG"}

# 主题配色：每个主题一套色板，用于生成 QSS
THEMES = {
    "浅色": {
        "fg": "#1f2937", "bg": "#eef2f7", "sidebar": "#f8fafc", "card": "#ffffff",
        "text_strong": "#0f172a", "text_mid": "#334155", "muted": "#64748b", "hint": "#475569",
        "accent": "#2563eb", "accent2": "#3b82f6", "accent_soft": "#eff6ff",
        "accent_checked": "#e0efff", "accent_checked_fg": "#1d4ed8",
        "border": "#e5eaf2", "border2": "#dbe3ee", "border3": "#e2e8f0",
        "border_soft": "#bcd3f5", "seg_bg": "#f1f5f9", "hover": "#f8fafc",
        "disabled_bg": "#f1f5f9", "disabled_fg": "#9aa3b2", "focus_border": "#93c5fd",
        "primary_disabled": "#bfdbfe", "primary_disabled_fg": "#eff6ff",
        "stop_bg": "#fff1f2", "stop_border": "#fecdd3", "stop_fg": "#be123c", "stop_hover": "#ffe4e6",
        "header_bg": "#f8fafc", "item_border": "#f1f5f9", "scrollbar": "#cbd5e1",
        "log_bg": "#0f172a", "log_fg": "#e2e8f0", "drop_bg": "#f8fbff",
    },
    "深色": {
        "fg": "#e5e7eb", "bg": "#111827", "sidebar": "#1f2937", "card": "#1f2937",
        "text_strong": "#f9fafb", "text_mid": "#d1d5db", "muted": "#cbd5e1", "hint": "#e5e7eb",
        "accent": "#60a5fa", "accent2": "#3b82f6", "accent_soft": "#1e3a5f",
        "accent_checked": "#1e40af", "accent_checked_fg": "#93c5fd",
        "border": "#374151", "border2": "#4b5563", "border3": "#374151",
        "border_soft": "#2563eb", "seg_bg": "#111827", "hover": "#273449",
        "disabled_bg": "#1f2937", "disabled_fg": "#6b7280", "focus_border": "#3b82f6",
        "primary_disabled": "#1e3a5f", "primary_disabled_fg": "#9ca3af",
        "stop_bg": "#3f1d2e", "stop_border": "#7f1d1d", "stop_fg": "#fda4af", "stop_hover": "#4a1f30",
        "header_bg": "#1f2937", "item_border": "#374151", "scrollbar": "#4b5563",
        "log_bg": "#000000", "log_fg": "#d1d5db", "drop_bg": "#1e293b",
    },
    "紫色": {
        "fg": "#3a3550", "bg": "#f3f0fa", "sidebar": "#ede8f7", "card": "#ffffff",
        "text_strong": "#2e2942", "text_mid": "#4a445e", "muted": "#8b849e", "hint": "#6b6485",
        "accent": "#8e7cc3", "accent2": "#9c8bd0", "accent_soft": "#efeaf8",
        "accent_checked": "#e3dcf5", "accent_checked_fg": "#5b4a99",
        "border": "#e8e3f2", "border2": "#e0daee", "border3": "#e8e3f2",
        "border_soft": "#b9a8dd", "seg_bg": "#f3effb", "hover": "#f5f2fb",
        "disabled_bg": "#f3effb", "disabled_fg": "#b3accc", "focus_border": "#9c8bd0",
        "primary_disabled": "#d5cdec", "primary_disabled_fg": "#f7f4fc",
        "stop_bg": "#fdf0f4", "stop_border": "#f6c8d4", "stop_fg": "#b03a5b", "stop_hover": "#fbe3ea",
        "header_bg": "#f5f2fb", "item_border": "#eee9f6", "scrollbar": "#c9bdd9",
        "log_bg": "#2e2942", "log_fg": "#e8e3f2", "drop_bg": "#f7f4fc",
    },
}

_QSS_TEMPLATE = """
* {{ font-family: '{font}'; font-size: 13px; color: {fg}; }}
QMainWindow, QWidget#root {{ background: transparent; }}
/* 卡片 / 侧栏 / 拖放区 / 分段栏 / 状态栏 由 GlassPanel 自绘背景，这里不再设 QSS 背景，
   否则会和自绘叠加成两次混色（画面偏实、通透度失效） */
QLabel#logo {{ font-size: 25px; font-weight: 800; color: {accent}; }}
QLabel#logoSub {{ color: {muted}; font-size: 11px; }}
QLabel#h1 {{ font-size: 22px; font-weight: 700; color: {text_strong}; }}
QLabel#h2 {{ font-size: 15px; font-weight: 600; color: {text_strong}; }}
QLabel#muted {{ color: {muted}; font-size: 12px; }}
QLabel#hint {{ color: {hint}; font-size: 12px; }}
QLabel#notice {{ color: {accent_checked_fg}; background: {accent_soft}; border: 1px solid {border_soft};
                 border-radius: 8px; padding: 8px 10px; font-size: 12px; font-weight: 600; }}
QPushButton {{ background: {card_rgba}; border: 1px solid {border2}; border-radius: 8px; padding: 7px 14px; color: {text_mid}; }}
QPushButton:hover {{ background: {hover}; border-color: {border_soft}; }}
QPushButton#primary {{ background: {accent2}; border: none; color: #ffffff; font-weight: 700; padding: 10px 24px; border-radius: 10px; }}
QPushButton#primary:hover {{ background: {accent}; }}
QPushButton#primary:disabled {{ background: {primary_disabled}; color: {primary_disabled_fg}; }}
QPushButton#link {{ background: transparent; border: none; color: {accent}; text-align: left; padding: 6px 0; }}
QPushButton#link:hover {{ color: {accent2}; }}
QPushButton#stop {{ background: {stop_bg}; border: 1px solid {stop_border}; color: {stop_fg}; }}
QPushButton#stop:hover {{ background: {stop_hover}; }}
QPushButton#nav {{ text-align: left; padding: 10px 14px; border: none; border-radius: 9px; color: {hint}; background: transparent; font-size: 13px; }}
QPushButton#nav:hover {{ background: {accent_soft}; color: {accent}; }}
QPushButton#nav:checked {{ background: {accent_checked}; color: {accent_checked_fg}; font-weight: 600; }}
QPushButton#mode {{ background: transparent; border: none; border-radius: 8px; padding: 8px 16px; color: {muted}; }}
QPushButton#mode:hover {{ color: {accent}; }}
QPushButton#mode:checked {{ background: {card}; color: {accent_checked_fg}; font-weight: 600; border: 1px solid {accent_checked}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {card_rgba}; border: 1px solid {border2}; border-radius: 8px; padding: 6px 10px; min-height: 22px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {focus_border}; outline: none; }}
QComboBox:focus {{ border: 1px solid {focus_border}; outline: none; }}
QComboBox::drop-down {{ border: none; background: transparent; width: 24px; }}
QComboBox::down-arrow {{ image: none; border: none; }}
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled {{
    color: {disabled_fg}; background: {disabled_bg}; border-color: {border};
}}
QRadioButton:disabled, QCheckBox:disabled {{ color: {disabled_fg}; }}
QComboBox QAbstractItemView {{ background: {card}; color: {fg}; border: 1px solid {border2}; border-radius: 8px; padding: 4px; outline: none; }}
QComboBox QAbstractItemView::item {{ min-height: 28px; padding: 6px 8px; border: none; border-radius: 6px; color: {fg}; }}
QComboBox QAbstractItemView::item:hover {{ background: {accent_soft}; color: {text_strong}; }}
QComboBox QAbstractItemView::item:selected {{ background: {accent_checked}; color: {accent_checked_fg}; }}
QCheckBox {{ spacing: 7px; color: {text_mid}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {border2}; border-radius: 4px; background: {card_rgba}; }}
QCheckBox::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
QRadioButton {{ spacing: 7px; color: {text_mid}; }}
QRadioButton::indicator {{ width: 16px; height: 16px; border: 1px solid {border2}; border-radius: 8px; background: {card_rgba}; }}
QRadioButton::indicator:hover {{ border-color: {accent}; }}
QRadioButton::indicator:checked {{ background: {accent}; border-color: {accent}; }}
QSlider::groove:horizontal {{ height: 6px; background: {border}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ height: 6px; background: {accent2}; border-radius: 3px; }}
QSlider::add-page:horizontal {{ height: 6px; background: {border}; border-radius: 3px; }}
QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -5px 0; background: {card}; border: 2px solid {accent}; border-radius: 8px; }}
QSlider::handle:horizontal:hover {{ background: {accent_soft}; border-color: {accent2}; }}
QTableWidget {{ background: {card}; border: 1px solid {border}; border-radius: 10px; gridline-color: transparent; selection-background-color: {accent_soft}; selection-color: {fg}; }}
QHeaderView::section {{ background: {header_bg}; border: none; border-bottom: 1px solid {border}; padding: 8px; color: {muted}; font-weight: 600; }}
QTableWidget::item {{ padding: 4px 8px; border-bottom: 1px solid {item_border}; }}
QProgressBar {{ background: {bg}; border: none; border-radius: 6px; height: 12px; text-align: center; color: {hint}; font-size: 10px; }}
QProgressBar::chunk {{ background: {accent2}; border-radius: 6px; }}
QTextEdit {{ background: {log_bg}; color: {log_fg}; border: none; border-radius: 10px; font-family: '{font}'; font-size: 12px; padding: 8px; }}
QListWidget {{ background: {card}; border: 1px solid {border}; border-radius: 10px; padding: 4px; }}
QListWidget::item {{ padding: 6px 8px; border-bottom: 1px solid {item_border}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QAbstractScrollArea {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px 0; border: none; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0 2px; border: none; }}
QScrollBar::handle:vertical {{ background: {scrollbar}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:horizontal {{ background: {scrollbar}; border-radius: 5px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; background: transparent; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; border: none; }}

QLabel#env {{ color: {muted}; font-size: 11px; }}
QToolTip {{ background: {card}; color: {text_strong}; border: 1px solid {border2}; border-radius: 6px; padding: 8px 10px; font-size: 12px; }}
QDialog, QMessageBox {{ background: {bg}; }}
QMessageBox {{ background: {card}; }}
QMessageBox QLabel {{ color: {fg}; font-size: 13px; }}
QMessageBox QPushButton {{ background: {card_rgba}; color: {text_mid}; border: 1px solid {border2}; border-radius: 8px; padding: 6px 18px; min-width: 64px; }}
QMessageBox QPushButton:hover {{ background: {hover}; border-color: {accent}; color: {accent}; }}
QInputDialog, QInputDialog QLabel {{ background: {card}; color: {fg}; }}
QInputDialog QLineEdit {{ background: {card_rgba}; color: {fg}; }}
QMenu {{ background: {card}; color: {fg}; border: 1px solid {border2}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {accent_checked}; color: {accent_checked_fg}; }}
"""


# 半透明容器的自我绘制参数：颜色、(基准不透明度, 通透度系数)、圆角、边框
# 之所以自己画而不是走样式表：改一次 QSS 会让 Qt 重解析全部规则并重新 polish 所有控件
# （实测 app 级 280ms、窗口级 85ms），拖滑块根本跟不上；自绘只要一次重绘（约 11ms）。
# 通透度滑块上限（150%）：0~100% 时面板从默认色渐透，100% 以上继续往下压到接近纯背景
_GLASS_MAX = 1.5
_GLASS_BASES = {
    "深色": {"card": ((31, 41, 55), 88, 18), "sidebar": ((15, 23, 42), 86, 16),
             "drop": ((30, 41, 59), 80, 14), "seg": ((17, 24, 39), 75, 12)},
    "紫色": {"card": ((247, 244, 252), 80, 14), "sidebar": ((237, 232, 247), 78, 12),
             "drop": ((247, 244, 252), 70, 10), "seg": ((243, 239, 251), 66, 8)},
    "浅色": {"card": ((255, 255, 255), 78, 14), "sidebar": ((248, 250, 252), 76, 12),
             "drop": ((248, 251, 255), 70, 10), "seg": ((241, 245, 249), 64, 8)},
}

# 每种容器：圆角半径、边框色取自哪个主题色、边框画在哪
_GLASS_KINDS = {
    "card": dict(radius=14, border="border", side="all"),
    "drop": dict(radius=12, border="border_soft", side="all", dash=True),
    "seg": dict(radius=10, border="border3", side="all"),
    "sidebar": dict(radius=0, border="border", side="right"),
    "statusbar": dict(radius=0, border="border", side="top"),
}

# 当前生效的颜色（含通透度数值），由 _make_qss / _preview_glass 写入，自绘容器读取
_PAINT = {"colors": {}, "glass": {}}


def _glass_alphas(theme, glass):
    """返回 {容器: ((r,g,b), 不透明度百分数)}；glass 0~1.5，越大越透。

    0~1 段沿用原来的线性映射，老设置里 0~100% 的观感一分不变；
    1~1.5 段（滑块 100%~150%）再乘一个衰减系数（1.0 → 0.3），
    让「还想再透一点」这一段真的看得出来，越往上越接近纯背景。
    """
    try:
        glass = max(0.0, min(_GLASS_MAX, float(glass)))
    except Exception:
        glass = 0.0
    base = _GLASS_BASES.get(theme, _GLASS_BASES["浅色"])
    extra = max(0.0, glass - 1.0)
    k = 1.0 - 1.4 * extra                    # 100% → 1.0，150% → 0.3
    out = {}
    for key, (rgb, a0, drop) in base.items():
        a = (a0 - drop * min(glass, 1.0)) * k
        out[key] = (rgb, max(6, min(100, int(a + 0.5))))
    out["statusbar"] = out["card"]           # 状态栏与卡片同透明度
    return out


def _rgba_css(rgb, a):
    return "rgba(%d,%d,%d,%d%%)" % (rgb[0], rgb[1], rgb[2], a)


def _make_qss(theme="浅色", font="Microsoft YaHei UI",
              accent=None, text_color=None, glass=0.0):
    colors = THEMES.get(theme, THEMES["浅色"])
    # 深色主题用深色半透明卡片，浅色主题用浅色半透明卡片，让自定义背景能透出
    is_dark = theme == "深色"
    colors = dict(colors)
    # 通透度（glass 0~1.5）：0=默认不透明，1=原上限，1.5=几乎全透。设置背景图后下调卡片/侧栏不透明度，
    # 让背景图从半透明面板中清晰透出。
    try:
        glass = max(0.0, min(_GLASS_MAX, float(glass)))
    except Exception:
        glass = 0.0
    # 自定义强调色：覆盖 accent/accent2，并派生 soft/checked 系列
    if accent:
        c = QColor(accent)
        if c.isValid():
            accent_hex = c.name()
            colors["accent"] = accent_hex
            colors["accent2"] = accent_hex
            colors["accent_soft"] = _alpha(accent_hex, 0.14)
            colors["accent_checked"] = _alpha(accent_hex, 0.18)
            colors["accent_checked_fg"] = _darken_or_lighten(accent_hex, is_dark)
            colors["focus_border"] = accent_hex
            colors["border_soft"] = accent_hex
    # 自定义文字颜色：覆盖全局所有文字（含标题、正文、说明小字、导航栏文字）
    if text_color:
        c = QColor(text_color)
        if c.isValid():
            t_hex = c.name()
            colors["fg"] = t_hex
            colors["text_strong"] = t_hex
            colors["text_mid"] = t_hex
            colors["hint"] = t_hex
            colors["muted"] = t_hex
    # 通透度统一由 _glass_alphas 计算，自绘容器读同一份数值，避免两处算法漂移
    ga = _glass_alphas(theme, glass)
    colors["card_rgba"] = _rgba_css(*ga["card"])
    colors["sidebar_rgba"] = _rgba_css(*ga["sidebar"])
    colors["drop_rgba"] = _rgba_css(*ga["drop"])
    colors["seg_rgba"] = _rgba_css(*ga["seg"])
    colors["status_rgba"] = _rgba_css(*ga["statusbar"])
    # 供自绘容器（卡片/侧栏/拖放区/分段/状态栏）读取当前生效的颜色
    _PAINT["colors"] = dict(colors)
    _PAINT["glass"] = ga
    return _QSS_TEMPLATE.format(font=font, **colors)


def _alpha(hex_color, a):
    """把 #rrggbb 转成 rgba(r,g,b,a%) 形式（a 为 0~1）。"""
    try:
        c = QColor(hex_color)
        return "rgba(%d,%d,%d,%d%%)" % (c.red(), c.green(), c.blue(), int(a * 100))
    except Exception:
        return hex_color


def _darken_or_lighten(hex_color, is_dark):
    """强调色的选中态文字：深色主题下用更亮，浅色主题下用更深。"""
    try:
        c = QColor(hex_color)
        if is_dark:
            l = c.lighter(150)
        else:
            l = c.darker(140)
        return l.name()
    except Exception:
        return hex_color




# 默认主题（启动时使用，之后由设置里的主题覆盖）
QSS = _make_qss("浅色", "Microsoft YaHei UI")


def _short(text, n=30):
    return text if len(text) <= n else text[:n - 1] + "…"


def _unique(path):
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 1
    while os.path.exists("%s_%d%s" % (stem, i, ext)):
        i += 1
    return "%s_%d%s" % (stem, i, ext)


# 拖放区那个「↓」：用的是界面主字体自带字形（微软雅黑有 U+2193），
# 千万不要换成「⇩」这类雅黑没有的符号——Qt 会为了找替代字形把系统里
# 几百上千个字体挨个打开扫一遍，一次 0.45~0.8s，正好卡在启动过渡页上。
_ICO_FONT = "Microsoft YaHei UI"


def _ico_css(color):
    return ('font-family: "%s"; font-size: 30px; font-weight: 700; color: %s;'
            % (_ICO_FONT, color))


def _gpu_name():
    """显卡型号：优先用启动时后台探好的结果（见 envprobe），没有再现查。"""
    g = envprobe.cached_gpu()
    if g:
        return g
    return envprobe.gpu_name()


def _gpu_mem():
    """显存占用：优先用启动时后台探好的结果（见 envprobe），没有再现查。"""
    m = envprobe.cached_mem()
    if m is not envprobe.MISSING:
        return m
    return envprobe.gpu_mem_now()


def _collect_hardware():
    """采集本机硬件信息（图吧工具箱风格），返回 [(分类, 内容), ...] 列表。

    优先用 PowerShell CIM（Win10/11 通用），wmic 已在新系统弃用。
    """
    import platform as _platform
    info = []
    try:
        info.append(("系统", "%s %s" % (_platform.system(), _platform.machine())))
    except Exception:
        pass
    # 用 PowerShell CIM 一次性取齐关键硬件，避免多次起进程
    try:
        ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
              "$c=(Get-CimInstance Win32_Processor|Select -First 1).Name;"
              "$m=(Get-CimInstance Win32_PhysicalMemory|Measure Capacity -Sum).Sum;"
              "$mb=(Get-CimInstance Win32_BaseBoard|Select -First 1).Product;"
              "$bi=(Get-CimInstance Win32_BIOS|Select -First 1).Manufacturer;"
              "$os=(Get-CimInstance Win32_OperatingSystem|Select -First 1).Caption;"
              "Write-Output ('CPU|' + $c);"
              "Write-Output ('RAM|' + [math]::Round($m/1GB,1));"
              "Write-Output ('MB|' + $mb);"
              "Write-Output ('BIOS|' + $bi);"
              "Write-Output ('OS|' + $os)")
        p = procutil.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True, timeout=8,
                         encoding="utf-8", errors="replace")
        for ln in (p.stdout or "").splitlines():
            if "|" in ln:
                k, v = ln.split("|", 1)
                v = v.strip()
                if not v:
                    continue
                if k == "CPU":
                    info.append(("处理器", v))
                elif k == "RAM":
                    info.append(("内存", "%sGB" % v))
                elif k == "MB":
                    info.append(("主板", v))
                elif k == "OS":
                    info.append(("操作系统", v))
    except Exception:
        pass
    # 显卡（含显存）
    try:
        gpu = _gpu_name()
        mem = _gpu_mem()
        gpu_txt = gpu
        if mem:
            gpu_txt = "%s（%dMB）" % (gpu, mem[1])
        if gpu_txt:
            info.append(("显卡", gpu_txt))
    except Exception:
        pass
    # 磁盘
    try:
        ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
              "Get-CimInstance Win32_DiskDrive | ForEach-Object {"
              "Write-Output ($_.Model + '|' + [math]::Round($_.Size/1GB,0) + 'GB')}")
        p = procutil.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True, timeout=8,
                         encoding="utf-8", errors="replace")
        for ln in (p.stdout or "").splitlines():
            if "|" in ln:
                model, size = ln.split("|", 1)
                model = model.strip()
                if model:
                    info.append(("磁盘", "%s（%s）" % (model, size.strip())))
    except Exception:
        pass
    return info


def _target_size(w, h, mode):
    mode = (mode or "").strip()
    if not mode or mode in ("源分辨率", "原分辨率", "100%"):
        return None
    try:
        if mode.endswith("%"):
            f = float(mode[:-1]) / 100.0
            tw, th = int(round(w * f)), int(round(h * f))
        else:
            presets = {"HD 720p": 720, "HD 1080p": 1080, "UHD 2K": 1440, "UHD 4K": 2160}
            th = presets.get(mode)
            if not th:
                return None
            tw = int(round(th * w / float(h)))
    except Exception:
        return None
    tw, th = max(2, tw - tw % 2), max(2, th - th % 2)
    return (tw, th)


class Backdrop(QWidget):
    """铺满窗口的自定义背景（静态图 / 视频）+ 半透明蒙版。

    - 静态图：按 KeepAspectRatioByExpanding 居中裁剪铺满。
    - 视频（视频壁纸）：用 QGraphicsVideoItem 放进 QGraphicsScene，视频项
      z=0 垫底，UI 由 QGraphicsProxyWidget 包住浮在 z=1。这样视频走 GPU
      硬解 + 硬件合成（和浏览器 <video> 一样流畅），又因图形场景统一按
      z 值合成，彻底避免 native 视频窗口浮在 UI 之上的问题。
    上面再盖一层半透明蒙版保证文字可读。未设内容时退回纯色背景。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.pix = None
        self.dark = 0.42      # 蒙版不透明度 0~1
        self.min_dark = 0.18  # 有背景内容时蒙版最低托底（保证 UI 可读）
        self._base = QColor(21, 23, 31)   # 无图时的兜底底色
        self._mask = QColor(8, 10, 16)    # 蒙版颜色（深色主题暗化/浅色主题提亮）
        self._player = None               # QMediaPlayer
        self._video_item = None           # QGraphicsVideoItem
        self._scene = None                # QGraphicsScene
        self._view = None                 # QGraphicsView（视频容器，垫底）
        self._mask_item = None            # scene 里的蒙版矩形

    def _ensure_player(self):
        if self._player is not None:
            return
        try:
            from PySide6.QtMultimedia import QMediaPlayer
            from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
            from PySide6.QtWidgets import QGraphicsScene, QGraphicsView
            from PySide6.QtWidgets import QGraphicsRectItem
            self._scene = QGraphicsScene(self)
            self._video_item = QGraphicsVideoItem()
            # 铺满整个背景、超出部分裁剪（等价 QVideoWidget 的 KeepAspectRatioByExpanding）
            self._video_item.setAspectRatioMode(Qt.KeepAspectRatioByExpanding)
            self._scene.addItem(self._video_item)
            # 蒙版层：z 高于视频，半透明矩形盖在视频上保证文字可读
            self._mask_item = QGraphicsRectItem()
            self._mask_item.setPen(Qt.NoPen)
            self._mask_item.setZValue(1.0)
            self._scene.addItem(self._mask_item)
            self._view = QGraphicsView(self._scene, self)
            self._view.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self._view.setFrameShape(QFrame.NoFrame)
            self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._view.setStyleSheet("background: transparent;")
            self._view.hide()
            self._player = QMediaPlayer(self)
            self._player.setVideoOutput(self._video_item)
            self._player.setLoops(QMediaPlayer.Loops.Infinite)
            self._player.errorOccurred.connect(self._on_video_error)
        except Exception:
            self._player = None
            self._video_item = None
            self._scene = None
            self._view = None
            self._mask_item = None

    def _update_mask_item(self):
        """按窗口尺寸 + 蒙版暗度刷新 scene 里的蒙版矩形。"""
        if self._mask_item is None:
            return
        a = max(self.dark, self.min_dark)
        c = QColor(self._mask)
        c.setAlpha(int(255 * a))
        self._mask_item.setBrush(c)
        if self._view is not None:
            self._mask_item.setRect(0, 0, self._view.width(), self._view.height())

    def _on_video_error(self, err, err_str):
        # 视频解码失败时静默回退到纯色背景，避免崩溃；错误写日志便于排查
        try:
            with open(os.path.join(paths.APP_DIR, "logs", "bg_video.log"), "a",
                      encoding="utf-8") as _f:
                _f.write("[%s] video error %s: %s\n"
                         % (time.strftime("%Y-%m-%d %H:%M:%S"), err, err_str))
        except Exception:
            pass
        if self._view is not None:
            self._view.hide()
        self.update()

    def _attach_video_widget(self, root, under_widget):
        """把视频视图(QGraphicsView)铺满本 Backdrop。

        视频视图是本类的子控件，本类已 stackUnder(sidebar) 垫底，视频自然垫底。
        """
        if self._view is None:
            return
        self._view.setGeometry(self.rect())
        self._view.lower()

    def _sync_video_geometry(self):
        """同步视频视图几何（窗口尺寸变化时兜底）。"""
        if self._view is not None:
            self._view.setGeometry(self.rect())
            if self._video_item is not None:
                self._video_item.setSize(self._view.size())
            self._update_mask_item()

    def set_video(self, path):
        """播放视频壁纸；path 为空则停止视频回到静态/纯色背景。"""
        if not path or not os.path.isfile(path):
            if self._player is not None:
                try:
                    self._player.stop()
                except Exception:
                    pass
            if self._view is not None:
                self._view.hide()
            self.update()
            return
        self._ensure_player()
        if self._player is None:
            return
        from PySide6.QtCore import QUrl
        self.pix = None
        if self._view is not None:
            self._view.setGeometry(self.rect())
            self._view.show()
            if self._video_item is not None:
                self._video_item.setSize(self._view.size())
            self._update_mask_item()
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()

    def pause_video(self):
        """拖动期间临时暂停视频壁纸（仅在用户开启"拖动时暂停动态壁纸"时调用）。"""
        if self._player is None or getattr(self, "_paused_by_ui", False):
            return
        try:
            if self._player.isPlaying():
                self._player.pause()
                self._paused_by_ui = True
        except Exception:
            pass

    def resume_video(self):
        """恢复被临时暂停的视频壁纸；未暂停时是空操作。"""
        if self._player is None or not getattr(self, "_paused_by_ui", False):
            return
        self._paused_by_ui = False
        try:
            self._player.play()
        except Exception:
            pass

    def set_image(self, path):
        # 切回静态图：停止视频
        if self._player is not None:
            try:
                self._player.stop()
            except Exception:
                pass
        if self._view is not None:
            self._view.hide()
        if path and os.path.isfile(path):
            p = QPixmap(path)
            self.pix = p if not p.isNull() else None
        else:
            self.pix = None
        self.update()

    def set_dark(self, val):
        self.dark = max(0.0, min(1.0, float(val)))
        self._update_mask_item()
        self.update()

    def set_base(self, color):
        self._base = QColor(color)
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._view is not None:
            self._view.setGeometry(self.rect())
            if self._video_item is not None:
                self._video_item.setSize(self._view.size())
            self._update_mask_item()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        r = self.rect()
        # 视频播放时本 widget 什么都不画（视频 + 蒙版都在 QGraphicsScene 里），
        # 静态图则画图 + 蒙版，无内容画纯色兜底。
        video_active = (self._view is not None and self._view.isVisible()
                        and self._player is not None)
        if video_active:
            # 视频背景完全交给 QGraphicsView 渲染，这里不画
            return
        if self.pix is not None:
            scaled = self.pix.scaled(r.size(), Qt.KeepAspectRatioByExpanding,
                                     Qt.SmoothTransformation)
            x = (scaled.width() - r.width()) // 2
            y = (scaled.height() - r.height()) // 2
            p.drawPixmap(-x, -y, scaled)
            c = QColor(self._mask)
            a = max(self.dark, self.min_dark)
            c.setAlpha(int(255 * a))
            p.fillRect(r, c)
        else:
            p.fillRect(r, self._base)


class GlassPanel(QFrame):
    """半透明容器（卡片 / 侧栏 / 拖放区 / 分段栏 / 状态栏）——背景自己画。

    走样式表的话，改一次通透度就要重建整份 QSS 并让 Qt 重新 polish 所有控件
    （实测 280ms），拖滑块会卡成 PPT；自绘只要 update() 重绘，约 11ms，
    拖动时就能真正实时预览。
    """

    def __init__(self, kind="card", parent=None):
        super().__init__(parent)
        self._kind = kind
        self.setObjectName(kind)
        # 以前 1px 边框由 QSS 画，Qt 会据此把内容整体内缩 1px；改自绘后要手动补回来，
        # 否则卡片里的文字/控件会整体偏移 1px（和旧版截图比对能看出来）
        side = (_GLASS_KINDS.get(kind) or {}).get("side")
        if side == "right":
            self.setContentsMargins(0, 0, 1, 0)
        elif side == "top":
            self.setContentsMargins(0, 1, 0, 0)
        else:
            self.setContentsMargins(1, 1, 1, 1)

    def paintEvent(self, event):
        colors = _PAINT.get("colors") or {}
        glass = (_PAINT.get("glass") or {}).get(self._kind)
        spec = _GLASS_KINDS.get(self._kind)
        if not colors or not glass or not spec:
            super().paintEvent(event)
            return
        rgb, alpha = glass
        pen_c = QColor(colors.get(spec["border"], "#dbe3ee"))
        radius = spec["radius"]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect())
        if radius:
            rect = rect.adjusted(0.5, 0.5, -0.5, -0.5)
        fill = QBrush(QColor(rgb[0], rgb[1], rgb[2], int(alpha * 255 / 100 + 0.5)))
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        if radius:
            p.drawRoundedRect(rect, radius, radius)
        else:
            p.fillRect(self.rect(), fill)
        # 边框：圆角容器整圈；侧栏/状态栏只画朝内那一条
        pen = QPen(pen_c)
        pen.setWidth(1)
        if spec.get("dash"):
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        side = spec["side"]
        if side == "all":
            p.drawRoundedRect(rect, radius, radius)
        elif side == "right":
            p.drawLine(self.width() - 1, 0, self.width() - 1, self.height() - 1)
        elif side == "top":
            p.drawLine(0, 0, self.width() - 1, 0)


class Card(GlassPanel):
    def __init__(self, parent=None, name="card"):
        super().__init__(name, parent)
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(18, 16, 18, 16)
        self.v.setSpacing(10)


class _ClickLabel(QLabel):
    """可点击的图片标签（点击回调由调用方给），用于收款码放大查看。"""

    def __init__(self, on_click, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._on_click:
            self._on_click()
        super().mouseReleaseEvent(event)


class MainWindow(QMainWindow):
    # 硬件采集完成信号（后台线程 emit，自动走 QueuedConnection 回主线程）
    hw_ready = Signal(list)
    # 更新检查完成信号（后台线程 emit，回主线程刷新更新页）
    update_ready = Signal(object)

    def __init__(self, tick=None, boot_qss=None):
        super().__init__()
        # 构建进度回调（过渡页用）：tick(阶段文字, 0~1 进度)
        self._tick = tick or (lambda text=None, progress=None: None)
        # 启动阶段：样式表已在 run() 里按最终主题铺好，构建期间不再重复 setStyleSheet
        # （每刷一次要 0.2~0.3s，三次就是三段动画冻住），收尾时按需补一次。
        self._boot = True
        self._boot_qss = boot_qss
        self.setWindowTitle("CHEN-V · 补帧 + 超分")
        self.setAcceptDrops(True)
        _ico = os.path.join(paths.APP_DIR, "icon.ico")
        if os.path.isfile(_ico):
            self.setWindowIcon(QIcon(_ico))

        self.setting = self._load_settings()
        self.theme = self.setting.get("theme") or "浅色"
        self.font_family = self.setting.get("font_family") or "Microsoft YaHei UI"
        self.accent_color = self.setting.get("accent_color", "")
        self.text_color = self.setting.get("text_color", "")
        try:
            self.glass = max(0.0, min(_GLASS_MAX, float(self.setting.get("glass", 0.0))))
        except Exception:
            self.glass = 0.0
        self.text_outline = int(self.setting.get("text_outline", 0))
        _i18n.set_lang(self.setting.get("lang", "zh-CN"))
        # 通透度滑块：拖动时容器自绘即时预览，停手 1.5 秒再统一提交样式表 + 写盘
        self._glass_timer = QTimer(self)
        self._glass_timer.setSingleShot(True)
        self._glass_timer.setInterval(1500)
        self._glass_timer.timeout.connect(self._apply_glass_refresh)
        self._glass_cache = []
        # 字体描边滑块节流：拖动时延迟写盘，避免卡顿
        self._outline_timer = QTimer(self)
        self._outline_timer.setSingleShot(True)
        self._outline_timer.setInterval(300)
        self._outline_timer.timeout.connect(self._on_outline_released)
        self.ffmpeg = paths.find_ffmpeg()
        # 编码器 / 显卡名都是子进程查出来的（合计约 0.15s）。main.py 在过渡页
        # 一起来就调了 envprobe.start()，这里取结果时一般已经探好；万一还在跑，
        # 也只等它剩下的那点时间，不再整段冻住动画。
        envprobe.start(self.ffmpeg)
        self._yield()
        self.encoders = envprobe.encoders()
        self.gpu = envprobe.gpu()
        self._yield()

        self.sr_map = {}
        self.sr_desc = {}
        # 超分模型分类：原始 key -> (显示名, 用途说明)
        _sr_cat = {
            "up2x-latest-denoise3x":   ("Real-CUGAN 2x（动漫·主推）",  "默认主推动漫：平衡画质/速度/部署，漫剪素材首选"),
            "up2x-latest-conservative": ("Real-CUGAN 2x 保守（动漫）", "动漫保守修复：更少改动原画风，线条更自然"),
            "up2x-latest-denoise1x":   ("Real-CUGAN 2x 轻降噪（动漫）", "动漫轻降噪：轻度去噪"),
            "up2x-latest-denoise2x":   ("Real-CUGAN 2x 中降噪（动漫）", "动漫中降噪：中等去噪强度"),
            "up2x-latest-no-denoise":  ("Real-CUGAN 2x 无降噪（动漫）", "动漫无降噪：仅放大不降噪"),
            "up3x-latest-denoise3x":   ("Real-CUGAN 3x 强降噪（动漫）", "动漫 3x：一步放大到 3 倍，强降噪，画质增强更明显"),
            "up3x-latest-conservative": ("Real-CUGAN 3x 保守（动漫）", "动漫 3x：更少改动原画风"),
            "up3x-latest-no-denoise":  ("Real-CUGAN 3x 无降噪（动漫）", "动漫 3x：仅放大不降噪"),
            "up4x-latest-denoise3x":   ("Real-CUGAN 4x 强降噪（动漫）", "动漫 4x：一步放大到 4K，强降噪，画质增强最强"),
            "up4x-latest-conservative": ("Real-CUGAN 4x 保守（动漫）", "动漫 4x：更少改动原画风"),
            "up4x-latest-no-denoise":  ("Real-CUGAN 4x 无降噪（动漫）", "动漫 4x：仅放大不降噪"),
            "realesr-animevideov3-x4":  ("AnimeVideo-v3（老番修复）",  "老番/压缩严重素材：动漫视频专用修复"),
            "realesrgan-x4plus":        ("Real-ESRGAN x4plus（真人/游戏）", "真人/游戏录屏：通用照片与实拍"),
        }
        def _sr_disp(_raw):
            # 去掉 (onnx)/(ncnn) 后缀做匹配，找不到就保留原样
            _base = _raw.rsplit("（", 1)[0]
            _hit = _sr_cat.get(_base)
            if not _hit:
                _hit = _sr_cat.get(_base.lower())
            if not _hit:
                # ncnn 版模型名不带 "latest-"（如 up2x-denoise3x），
                # 尝试去掉/插入 latest- 再匹配一次，复用 onnx 版的友好描述
                _no_latest = _base.replace("latest-", "")
                for _k, _v in _sr_cat.items():
                    if _no_latest.lower() == _k.replace("latest-", "").lower():
                        _hit = _v
                        break
            if not _hit:
                for _k, _v in _sr_cat.items():
                    if _base.lower().startswith(_k.lower()):
                        _hit = _v
                        break
            return _hit or (_raw, "")
        for _n, _p in paths.find_sr_models().items():
            _raw = "%s（onnx）" % _n
            _disp, _desc = _sr_disp(_raw)
            self.sr_map[_disp] = ("onnx", _p)
            self.sr_desc[_disp] = _desc
        try:
            for _label, _v in sr_ncnn.list_ncnn_sr().items():
                # SVFI 来源的模型（标记含「SVFI」）直接用原始名，避免与本地同名模型混淆
                if "SVFI" in _label:
                    _disp = _label
                    _desc = "来自 SVFI 的 Real-CUGAN 模型（ncnn 内核）"
                else:
                    _disp, _desc = _sr_disp(_label)
                    # 若与已有 onnx 显示名冲突，追加内核标识，避免覆盖且便于区分
                    if _disp in self.sr_map:
                        _disp = "%s（ncnn 内核）" % _disp
                self.sr_map[_disp] = ("ncnn", _v)
                self.sr_desc[_disp] = _desc
        except Exception:
            pass
        self.rife_map = {}
        self.rife_desc = {}
        try:
            order = ["rife-v4.18", "rife-v4.26-large", "rife-v4.25-heavy",
                     "rife-v4.6", "rife-v4.26", "rife-v4.25", "rife-v4.22",
                     "rife-v4.6_ensembleTrue", "rife-v4.6_ensembleFalse"]
            # 用途分类：模型目录名 -> (下拉框显示名, 用途说明)
            # 注：rife-v4.8 已在当前内核上验证会触发 Vulkan DEVICE_LOST 导致黑屏，已移除
            cat = {
                "rife-v4.18":       ("RIFE 4.18（真人/游戏）", "真人 / 游戏录屏：大运动更稳"),
                "rife-v4.26-large": ("RIFE 4.26 large（高画质）", "画质上限高，显存消耗较大（最新版大模型）"),
                "rife-v4.25-heavy": ("RIFE 4.25 heavy（高画质）", "画质上限最高，显存消耗最大（真 heavy 大模型，社区公认最稳）"),
                "rife-v4.6":        ("RIFE 4.6（通用）",       "通用：2 代稳定老模型，非整数倍率"),
                "rife-v4.26":       ("RIFE 4.26（通用）",      "通用：较新标准版，均衡画质与速度"),
                "rife-v4.25":       ("RIFE 4.25（通用）",      "通用：标准版，均衡"),
                "rife-v4.22":       ("RIFE 4.22（通用）",      "通用：标准版"),
            }
            for _n, _info in sorted(paths.find_rife_engines().items(),
                                    key=lambda kv: (order.index(kv[0]) if kv[0] in order else 99, kv[0])):
                label, desc = cat.get(_n, ("RIFE " + _n.replace("rife-", ""), ""))
                self.rife_map[label] = _info
                self.rife_desc[label] = desc
        except Exception:
            pass

        self.items = []            # 队列
        self.item_bars = {}        # idx -> QProgressBar
        self.running = False
        self.stop_event = threading.Event()
        self.msg = queue.Queue()
        self.cur_item = -1
        self.cfg = {}
        self._sr_cache = {}
        self.conv_files = []
        self.conv_running = False
        self.bench_running = False

        self._build()
        self._restore()
        self._yield()
        self._refresh_env()
        self._yield()
        self._refresh_table()
        self._yield()

        # 输入框默认会接管拖放（把文件路径当文本插入），这里统一关闭，
        # 让所有拖放都由主窗口处理：既能稳定触发壁纸暂停，也不会误写路径
        for _w in self.findChildren(QLineEdit):
            _w.setAcceptDrops(False)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(120)

        self.hw_ready.connect(self._on_hw_ready)
        self.update_ready.connect(self._apply_update_state)

        self._center()

    # ------------------------------------------------------------ 设置
    def _load_settings(self):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_settings(self):
        try:
            d = self._snapshot()
            d["out_dir"] = self.out_edit.text().strip()
            d["suffix"] = self.name_edit.text().strip()
            d["theme"] = self.theme
            # 背景图 + 视频背景 + 蒙版暗度必须一并持久化，否则关窗重开就丢
            d["bg"] = self.setting.get("bg", "")
            d["bg_video"] = self.setting.get("bg_video", "")
            d["bg_dark"] = self.setting.get("bg_dark", 42)
            d["glass"] = getattr(self, "glass", 0.0)
            # 拖动时是否暂停动态壁纸（默认关闭，壁纸连续播放）
            d["pause_bg_on_drag"] = self.setting.get("pause_bg_on_drag", 0)
            # 界面强调色 + 文字颜色 + 字体描边强度
            d["accent_color"] = self.setting.get("accent_color", "")
            d["text_color"] = self.setting.get("text_color", "")
            d["text_outline"] = getattr(self, "text_outline", 0)
            d["lang"] = self.setting.get("lang", "zh-CN")
            if hasattr(self, "cb_font"):
                d["font"] = self.cb_font.currentText()
                d["font_family"] = self.font_family
            if hasattr(self, "path_edits"):
                d["paths"] = {k: e.text() for k, e in self.path_edits.items()
                              if k not in ("work", "cache")}
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _center(self):
        scr = QApplication.primaryScreen().availableGeometry()
        w = min(1360, max(1060, scr.width() - 120))
        h = min(900, max(720, scr.height() - 120))
        self.resize(w, h)
        self.move(scr.x() + max(0, (scr.width() - w) // 2),
                  scr.y() + max(0, (scr.height() - h) // 2))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "bg"):
            self.bg.setGeometry(self.centralWidget().rect())
            self.bg._sync_video_geometry()

    def showEvent(self, e):
        super().showEvent(e)
        # 窗口显示后兜底：确保背景层铺满且始终位于侧栏/主区之下
        if hasattr(self, "bg"):
            self.bg.setGeometry(self.centralWidget().rect())
            if hasattr(self, "_sidebar"):
                self.bg.stackUnder(self._sidebar)
            self.bg.lower()
            self.bg._sync_video_geometry()

    # ------------------------------------------------------------ 背景图
    def _pick_bg(self):
        f, _ = QFileDialog.getOpenFileName(
            self, _tl("选择背景图片"), "",
            _tl("图片 (*.png *.jpg *.jpeg *.webp *.bmp);;全部 (*.*)"))
        if f:
            self._apply_bg(f, save=True)

    def _on_pause_bg_toggled(self, on):
        """记录"拖动时暂停动态壁纸"开关，默认关闭。"""
        self.setting["pause_bg_on_drag"] = 1 if on else 0
        self._save_settings()

    def _pick_wallpaper(self):
        """选择壁纸目录，扫描目录内的图片/视频文件作为背景。"""
        try:
            import wallpaper as wemod
        except Exception as e:
            QMessageBox.warning(self, _tl("壁纸"), _tl("无法加载壁纸模块：%s") % e)
            return

        # 记住上次选择的目录
        last_dir = self.setting.get("wallpaper_dir", "")
        if not last_dir or not os.path.isdir(last_dir):
            last_dir = ""

        directory = QFileDialog.getExistingDirectory(
            self, _tl("选择壁纸文件夹"), last_dir,
            QFileDialog.ShowDirsOnly)
        if not directory:
            return

        items = wemod.list_wallpapers(directory)
        if not items:
            QMessageBox.information(
                self, _tl("壁纸"),
                _tl("所选文件夹内没有找到壁纸文件。") + "\n\n" +
                _tl("支持的视频：mp4 / webm / mkv / mov / avi") + "\n" +
                _tl("支持的图片：png / jpg / jpeg / webp / bmp / gif"))
            return

        self.setting["wallpaper_dir"] = directory
        self._save_settings()

        dlg = QDialog(self)
        dlg.setWindowTitle(_tl("选择壁纸"))
        dlg.resize(760, 580)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        nvid = sum(1 for w in items if w["type"] == "video")
        tip = QLabel(_tl("共 %d 个壁纸（%d 个视频、%d 个图片）\n目录：%s")
                     % (len(items), nvid, len(items) - nvid, directory),
                     objectName="muted")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        # 搜索框
        search = QLineEdit()
        search.setPlaceholderText(_tl("搜索壁纸文件名…"))
        lay.addWidget(search)
        lst = QListWidget()
        lst.setIconSize(QSize(96, 54))
        lay.addWidget(lst, 1)
        # 预览
        prev = QLabel(_tl("选择左侧壁纸查看预览"), objectName="muted")
        prev.setMinimumHeight(160)
        prev.setAlignment(Qt.AlignCenter)
        prev.setScaledContents(False)
        lay.addWidget(prev)

        def _fill(keyword=""):
            lst.clear()
            for w in items:
                if keyword and keyword.lower() not in w["title"].lower():
                    continue
                tag = _tl("[视频]") if w["type"] == "video" else _tl("[图片]")
                it = QListWidgetItem("%s %s" % (tag, w["title"]))
                it.setData(Qt.UserRole, w)
                p = w["file"]
                if p and os.path.isfile(p):
                    it.setIcon(QIcon(p))
                lst.addItem(it)
        _fill()
        search.textChanged.connect(lambda t: _fill(t))

        def _on_sel():
            it = lst.currentItem()
            if not it:
                return
            w = it.data(Qt.UserRole)
            p = w["file"]
            if p and os.path.isfile(p):
                pm = QPixmap(p)
                if not pm.isNull():
                    prev.setPixmap(pm.scaled(prev.width(), prev.height(),
                                             Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    return
            prev.setText(_tl("无预览图"))

        lst.currentItemChanged.connect(lambda *_: _on_sel())

        btns = QHBoxLayout()
        btns.addStretch(1)
        ok = QPushButton(_tl("设为背景"), objectName="primary")
        cancel = QPushButton(_tl("取消"))
        btns.addWidget(ok)
        btns.addWidget(cancel)
        lay.addLayout(btns)

        def _confirm():
            it = lst.currentItem()
            if not it:
                return
            w = it.data(Qt.UserRole)
            if w["file"] and os.path.isfile(w["file"]):
                self._apply_bg(w["file"], save=True,
                               is_video=(w["type"] == "video"))
            else:
                QMessageBox.warning(self, _tl("壁纸"), _tl("这个壁纸文件不存在。"))
                return
            dlg.accept()

        ok.clicked.connect(_confirm)
        cancel.clicked.connect(dlg.reject)
        dlg.exec()

    def _clear_bg(self):
        if not hasattr(self, "bg"):
            return
        self.bg.set_image("")
        self.bg.set_video("")
        self.setting["bg"] = ""
        self.setting["bg_video"] = ""
        self._save_settings()
        self._update_bg_label()
        self._apply_text_shadow(self.text_outline)

    def _apply_bg(self, path, save=True, is_video=False):
        if not hasattr(self, "bg"):
            return
        if is_video or (path and path.lower().endswith((".mp4", ".webm", ".mkv", ".mov"))):
            self.bg.set_video(path)
            self.setting["bg_video"] = path
            self.setting["bg"] = ""
        else:
            self.bg.set_image(path)
            self.setting["bg"] = path
            self.setting["bg_video"] = ""
        if save:
            self._save_settings()
        self._update_bg_label()
        self._apply_text_shadow(self.text_outline)

    def _apply_text_shadow(self, enabled):
        """根据描边强度给文字加半透明描边阴影，保证在复杂背景上可读。

        enabled 为整数强度 0~10（0=关闭，越大描边越明显）。
        """
        root = self.centralWidget()
        if root is None:
            return
        level = int(enabled) if enabled is not None else 0
        # 描边颜色随主题：浅色主题文字为深色，用浅色描边在深色壁纸上分离；
        # 深色/紫色主题文字为浅色，用深色描边。
        theme = getattr(self, "theme", "浅色")
        if theme == "浅色":
            outline = QColor(255, 255, 255)
        else:
            outline = QColor(0, 0, 0)
        for w in root.findChildren(QLabel):
            if level <= 0:
                w.setGraphicsEffect(None)
                continue
            sh = w.graphicsEffect()
            if not isinstance(sh, QGraphicsDropShadowEffect):
                sh = QGraphicsDropShadowEffect(self)
                w.setGraphicsEffect(sh)
            # 描边强度映射：强度越高，模糊半径越小（越锐利）、透明度越高
            blur = max(1, 7 - level)          # level 1→6, level 10→1
            alpha = min(255, 90 + level * 15)  # level 1→105, level 10→240
            sh.setOffset(0, 0)
            sh.setBlurRadius(blur)
            sh.setColor(QColor(outline.red(), outline.green(), outline.blue(), alpha))

    def _apply_text_outline(self, val):
        """字体描边自调：拖动滑块实时调整描边强度并持久化。"""
        v = int(val)
        self.text_outline = v
        if hasattr(self, "lbl_outline"):
            self.lbl_outline.setText(("关闭" if v == 0 else "%d" % v))
        self._apply_text_shadow(v)
        if hasattr(self, "_outline_timer"):
            self._outline_timer.start()
        else:
            self.setting["text_outline"] = v
            self._save_settings()

    def _on_outline_released(self):
        self.setting["text_outline"] = self.text_outline
        self._save_settings()

    def _apply_bg_dark(self, val):
        if not hasattr(self, "bg"):
            return
        v = int(val)
        self.bg.set_dark(v / 100.0)
        self.setting["bg_dark"] = v
        if hasattr(self, "lbl_bg_dark"):
            self.lbl_bg_dark.setText("%d%%" % v)

    # ------------------------------------------------------------ 构建
    def _build(self):
        self._tick(_tl("正在搭建界面…"), 0.18)
        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        # 背景层：铺满窗口，放在最底层，作为 custom background
        self.bg = Backdrop(root)
        self.bg.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._sidebar = self._build_sidebar()
        self._yield()
        self._main = self._build_main()
        outer.addWidget(self._sidebar)
        outer.addWidget(self._main, 1)
        # 明确把背景层压到侧栏/主区之下，避免壁纸遮住 UI
        self.bg.stackUnder(self._sidebar)
        self.bg.lower()

        # 应用已保存的背景。注意：视频背景优先于静态图，且 _apply_bg 的
        # 静态图分支会清空 bg_video，所以必须先取出 bg_video 再恢复静态图。
        _bgv = self.setting.get("bg_video", "")
        _bg = self.setting.get("bg", "")
        if _bgv:
            # 有视频背景：直接恢复视频（内部会清掉 bg，无需再恢复静态图）
            self._apply_bg(_bgv, save=False, is_video=True)
        elif _bg:
            self._apply_bg(_bg, save=False)
        # 视频 widget 挂到 root 并压到 sidebar 之下（GPU 硬解，不抓帧不降帧率）
        self.bg._attach_video_widget(root, self._sidebar)
        # 恢复蒙版暗度 + 按主题适配蒙版颜色
        try:
            self.bg.set_dark(int(self.setting.get("bg_dark", 42)) / 100.0)
        except Exception:
            pass
        self._sync_bg_mask()
        self.bg.setGeometry(root.rect())
        self._yield()
        # 去掉下拉框弹出列表的系统默认浅色边框
        self._style_combo_popups()

    def _style_combo_popups(self):
        """给所有 QComboBox 的下拉视图兜底样式，消除白边与串色。

        下拉弹层是独立 popup，有时不受全局 QSS 控制；这里对每个 view
        直接设一套与当前主题一致的样式表，确保背景、文字、选中态都正确。
        """
        from PySide6.QtWidgets import QComboBox
        t = THEMES.get(getattr(self, "theme", "浅色"), THEMES["浅色"])
        card = t.get("card", "#ffffff")
        fg = t.get("fg", "#1f2937")
        border2 = t.get("border2", "#dbe3ee")
        acc_soft = t.get("accent_soft", "#eff6ff")
        acc_checked = t.get("accent_checked", "#e0efff")
        acc_checked_fg = t.get("accent_checked_fg", "#1d4ed8")
        text_strong = t.get("text_strong", "#0f172a")
        css = (
            "QAbstractItemView { background: %s; color: %s; border: 1px solid %s; "
            "border-radius: 8px; outline: none; } "
            "QAbstractItemView::item { min-height: 28px; padding: 6px 8px; color: %s; } "
            "QAbstractItemView::item:hover { background: %s; color: %s; } "
            "QAbstractItemView::item:selected { background: %s; color: %s; }"
            % (card, fg, border2, fg, acc_soft, text_strong, acc_checked, acc_checked_fg)
        )
        for cb in self.findChildren(QComboBox):
            v = cb.view()
            if v is None:
                continue
            try:
                v.setStyleSheet(css)
            except Exception:
                pass
            try:
                v.setFrameShape(QFrame.NoFrame)
            except Exception:
                pass

    def _build_sidebar(self):
        side = GlassPanel("sidebar")
        side.setFixedWidth(222)
        v = QVBoxLayout(side)
        v.setContentsMargins(16, 18, 16, 14)
        v.setSpacing(4)

        head = QHBoxLayout()
        _pic = os.path.join(paths.APP_DIR, "icon.png")
        if os.path.isfile(_pic):
            pm = QPixmap(_pic)
            if not pm.isNull():
                ico = QLabel()
                ico.setPixmap(pm.scaled(38, 38, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                head.addWidget(ico)
        logo = QLabel(objectName="logo")
        logo.setText("CHEN-V")
        head.addWidget(logo)
        head.addStretch(1)
        v.addLayout(head)
        sub = QLabel("CHEN-V  ·  版本 %s" % APP_VERSION, objectName="logoSub")
        v.addWidget(sub)
        v.addSpacing(14)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        # 图标字符只挑微软雅黑自带的字形（见 _app_font 注释），
        # 否则每换一个字符都可能触发一次系统字体扫描
        navs = [("超分补帧", "◆"), ("进度", "◎"),
                ("官网更新", "→"), ("设置", "≡"),
                ("界面美化", "◇"), ("硬件信息", "■"),
                ("关于", "⊙"), ("特别鸣谢", "☆")]
        self.nav_buttons = {}
        for text, icon in navs:
            b = QPushButton("%s   %s" % (icon, text), objectName="nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.nav_group.addButton(b)
            self.nav_buttons[text] = b
            v.addWidget(b)
        v.addStretch(1)

        card = QFrame(objectName="card")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(12, 10, 12, 10)
        t1 = QLabel("CHEN-V", objectName="h2")
        t2 = QLabel("补帧 + 超分 · 本地版", objectName="muted")
        cv.addWidget(t1)
        cv.addWidget(t2)
        v.addWidget(card)
        ver = QLabel("v%s  ·  %s" % (APP_VERSION.lstrip("V"), BUILD), objectName="muted")
        ver.setAlignment(Qt.AlignCenter)
        v.addWidget(ver)
        return side

    def _hw_fill_later(self, delay=120):
        """延后一点再采集：先让页面（或按钮状态）画出来，再去跑那一两秒的 WMI 查询。"""
        self._hw_done = True
        QTimer.singleShot(delay, self._fill_hardware)

    def _fill_hardware(self):
        """填充硬件信息页面的内容区域（图吧工具箱风格）。

        采集（PowerShell CIM ×2 + 显卡子进程）要 1~2 秒，最坏能卡 30 秒；
        放在后台线程里跑，主线程只画「正在检测」，不冻结界面，用户可以
        随时切到别的页面或点其他按钮。结果出来后经 QTimer 回主线程填 UI。
        """
        if not hasattr(self, "hw_body"):
            return
        # 清空旧项
        while self.hw_body.count():
            it = self.hw_body.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        hint = QLabel(_tl("正在检测本机硬件…"), objectName="hint")
        self.hw_body.addWidget(hint)

        def _work():
            try:
                hw = _collect_hardware()
            except Exception:
                hw = []
            # emit 信号跨线程安全（自动 QueuedConnection 投递回主线程）
            self.hw_ready.emit(hw)

        # 结果回主线程后填充（hw_ready 槽），这里只起线程
        threading.Thread(target=_work, daemon=True).start()

    def _on_hw_ready(self, hw):
        """后台采集完成，回主线程填充硬件页面。"""
        if not hasattr(self, "hw_body"):
            return
        # 清掉「正在检测」提示
        while self.hw_body.count():
            it = self.hw_body.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        if not hw:
            hw = [("提示", "未检测到硬件信息")]
        for cat, val in hw:
            row = QHBoxLayout()
            row.setSpacing(12)
            c = QLabel(cat, objectName="muted")
            c.setFixedWidth(64)
            c.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            row.addWidget(c)
            t = QLabel(val, objectName="hint")
            t.setWordWrap(True)
            t.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(t, 1)
            self.hw_body.addLayout(row)

    def _build_hardware_page(self):
        """独立的硬件信息页面：居中显示，图吧工具箱风格。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        scroll.setWidget(page)
        v = QVBoxLayout(page)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(12)
        v.addWidget(QLabel("硬件信息", objectName="h1"))
        v.addWidget(QLabel("本机硬件配置一览，可选中复制文字。", objectName="muted"))

        card = Card()
        # 刷新按钮
        head = QHBoxLayout()
        head.addWidget(QLabel("硬件配置", objectName="h2"))
        head.addStretch(1)
        b_refresh = QPushButton("重新检测")
        b_refresh.clicked.connect(self._hw_fill_later)
        head.addWidget(b_refresh)
        card.v.addLayout(head)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#eef2f7;border:none;")
        card.v.addWidget(line)

        self.hw_body = QVBoxLayout()
        self.hw_body.setSpacing(10)
        card.v.addLayout(self.hw_body)
        # 硬件采集要拉一串 WMI/PowerShell 查询（实测约 1.9 秒），放到首次打开这一页时再做，
        # 不然每次启动都要白等两秒
        self._hw_done = False
        self.hw_body.addWidget(QLabel(_tl("首次打开时自动检测本机硬件…"), objectName="hint"))

        v.addWidget(card)
        v.addStretch(1)
        return scroll

    def _build_main(self):
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.stack = QStackedWidget()
        v.addWidget(self.stack, 1)
        v.addWidget(self._build_statusbar())

        self.pages = {}
        builders = (("超分补帧", self._build_task_page),
                    ("进度", self._build_progress_page),
                    ("官网更新", self._build_update_page),
                    ("设置", self._build_settings_page),
                    ("界面美化", self._build_theme_page),
                    ("硬件信息", self._build_hardware_page),
                    ("关于", self._build_about_page),
                    ("特别鸣谢", self._build_thanks_page))
        total = len(builders)
        # 第一个页面（用户第一眼要看的）立刻入栈，其余的先攒着：
        # QStackedWidget.addWidget 每页要 60ms 左右（整棵树重新 polish），
        # 8 页连做就是 0.5s 的连续卡顿，正好卡在过渡页还在转的时候。
        # 主窗口出来后在事件循环里一页页补进去，用户看不到也感觉不到。
        self._pending_pages = []
        for i, (name, fn) in enumerate(builders):
            page = fn()
            self.pages[name] = page
            # 页面塞进 QStackedWidget 时，Qt 会先算一遍 sizeHint；这一页控件多、
            # 还有一堆自动换行的说明文字，实测算一次要 0.45~0.5s，正好卡在
            # 过渡页还在转的时候。窗口尺寸是显式 resize 的，不靠 sizeHint 撑，
            # 所以这里把策略设成 Ignored，让 Qt 跳过这次计算。
            page.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            self.nav_buttons[name].clicked.connect(
                lambda _=False, n=name: self._show_page(n))
            if i == 0:
                self.stack.addWidget(page)
            else:
                self._pending_pages.append((name, page))
            # 每建完一页回报一次：过渡页的粒子与进度条不会僵住
            self._tick(_tl("正在搭建界面…"), 0.22 + 0.68 * (i + 1) / total)
        self.nav_buttons["超分补帧"].setChecked(True)
        self._show_page("超分补帧")
        return wrap

    def _build_statusbar(self):
        bar = GlassPanel("statusbar")
        bar.setFixedHeight(34)
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 0, 16, 0)
        self.lbl_env = QLabel("环境：检查中…", objectName="env")
        self.lbl_env2 = QLabel("", objectName="env")
        # 环境信息不显示在状态栏（界面更清爽）；对象保留，_refresh_env 仍可写入
        self.lbl_env.hide()
        h.addStretch(1)
        h.addWidget(self.lbl_env2)
        return bar

    def _show_page(self, name):
        page = self.pages[name]
        if self.stack.indexOf(page) < 0:      # 还没入栈（启动时故意延后补的）
            self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        self.nav_buttons[name].setChecked(True)
        # 硬件信息首次打开才采集：先把页面画出来，再跑那两秒的 WMI 查询
        if name == "硬件信息" and not getattr(self, "_hw_done", False):
            self._hw_fill_later()

    def _flush_pending_pages(self):
        """主窗口出来之后，在事件循环的间隙里把剩余页面补进栈。

        每页要 60ms 左右，连做会卡；一页一调、中间留一帧空闲，
        界面已经显示出来了，用户只会在极短时间内感觉不到响应。
        """
        pending = getattr(self, "_pending_pages", None)
        if not pending:
            return
        name, page = pending.pop(0)
        self.stack.addWidget(page)
        if pending:
            QTimer.singleShot(16, self._flush_pending_pages)

    # ------------------------------------------------------------ 任务页
    def _build_task_page(self):
        # 左右两栏：左边调参数，右边拉素材 / 队列
        page = QWidget()
        root = QHBoxLayout(page)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        # ---------- 左栏：参数设置 ----------
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(560)   # 保证参数区不被右侧素材区挤压到只剩一条
        left_panel = QWidget()
        left_scroll.setWidget(left_panel)
        lv = QVBoxLayout(left_panel)
        lv.setContentsMargins(2, 2, 2, 2)
        lv.setSpacing(12)

        # 标题行：左侧标题 + 右侧紧凑的预设控件
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        tv = QVBoxLayout()
        tv.setSpacing(2)
        tv.addWidget(QLabel("创建增强任务", objectName="h1"))
        tv.addWidget(QLabel("左边调参数，右边拉素材；设置后点开始处理。", objectName="muted"))
        title_row.addLayout(tv)
        title_row.addStretch(1)

        # 参数预设（紧凑小控件，放标题右侧）
        title_row.addWidget(QLabel("预设", objectName="muted"))
        self.cb_preset = QComboBox()
        self.cb_preset.setFixedWidth(110)
        self.cb_preset.setToolTip("参数预设：一键加载已保存的整套参数组合")
        self.cb_preset.currentTextChanged.connect(self._load_preset)
        title_row.addWidget(self.cb_preset)
        self.btn_preset_save = QPushButton("保存预设")
        self.btn_preset_save.setFixedHeight(28)
        self.btn_preset_save.setToolTip("把当前所有参数保存为一个命名预设")
        self.btn_preset_save.clicked.connect(self._save_preset)
        title_row.addWidget(self.btn_preset_save)
        self.btn_preset_del = QPushButton("删除")
        self.btn_preset_del.setFixedHeight(28)
        self.btn_preset_del.setToolTip("删除当前选中的预设")
        self.btn_preset_del.clicked.connect(self._delete_preset)
        title_row.addWidget(self.btn_preset_del)
        lv.addLayout(title_row)
        # 预设下拉框的内容留到主窗口出来之后再填（见 _finish_boot）：
        # 往 QComboBox 里塞第一个选项会连带把下拉弹层建起来，实测要 0.6s，
        # 正好卡在过渡页还在转的时候。
        self._presets_pending = True

        # 模式
        seg = GlassPanel("seg")
        sh = QHBoxLayout(seg)
        sh.setContentsMargins(4, 4, 4, 4)
        sh.setSpacing(2)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_buttons = {}
        _mode_tips = {
            MODE_IMAGE: "图片超分：用超分模型把图片放大并增强画质，输出 PNG/JPG/WEBP",
            MODE_SR: "视频超分：保持源帧率不变，只用超分模型放大画面、增强清晰度",
            MODE_VFI: "视频补帧：用 RIFE 模型在两帧之间插帧，提升流畅度（帧率翻倍），不超分",
            MODE_BOTH: "超分并补帧：先补帧再超分，同时提升流畅度和清晰度（效果最好，耗时最长）",
        }
        for text in MODES:
            b = QPushButton(text, objectName="mode")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(_mode_tips.get(text, ""))
            self.mode_group.addButton(b)
            self.mode_buttons[text] = b
            sh.addWidget(b, 1)
        self.mode_buttons[MODE_BOTH].setChecked(True)
        self.mode_group.buttonClicked.connect(lambda b: self._on_mode_changed(b.text()))
        lv.addWidget(seg)

        self.lbl_mode_hint = QLabel("", objectName="hint")
        self.lbl_mode_hint.setWordWrap(True)
        lv.addWidget(self.lbl_mode_hint)
        self._yield()          # 这一页最重（约 0.28s），中间让一帧

        # 输入 / 输出 / 文件名
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)
        form.addWidget(QLabel("输入"), 0, 0)
        self.lbl_input = QLabel("尚未选择", objectName="muted")
        form.addWidget(self.lbl_input, 0, 1, 1, 3)
        form.addWidget(QLabel("输出目录"), 1, 0)
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("留空 = 素材所在目录")
        form.addWidget(self.out_edit, 1, 1, 1, 2)
        b_out = QPushButton("输出目录")
        b_out.clicked.connect(self._pick_out)
        form.addWidget(b_out, 1, 3)
        form.addWidget(QLabel("自动文件名"), 2, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("自动（源文件名_模式）；可填自定义后缀")
        form.addWidget(self.name_edit, 2, 1, 1, 3)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(2, 1)
        lv.addLayout(form)

        # 处理设置（默认展开）
        self.settings_panel = self._build_quick_settings()
        lv.addWidget(self.settings_panel)
        lv.addStretch(1)

        # ---------- 右栏：素材队列 ----------
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(2, 2, 2, 2)
        rv.setSpacing(12)

        # 拖放区
        drop = GlassPanel("drop")
        dh = QHBoxLayout(drop)
        dh.setContentsMargins(18, 16, 18, 16)
        dh.setSpacing(14)
        self.drop_ico = QLabel("↓")
        self.drop_ico.setStyleSheet(_ico_css("#3b82f6"))
        dh.addWidget(self.drop_ico)
        dv = QVBoxLayout()
        dv.setSpacing(2)
        dv.addWidget(QLabel("拖入图片、视频或文件夹", objectName="h2"))
        dv.addWidget(QLabel("单个素材直接处理，多个素材自动加入批量队列", objectName="muted"))
        dh.addLayout(dv)
        dh.addStretch(1)
        b_files = QPushButton("选择文件")
        b_files.clicked.connect(self._pick_files)
        b_files.setToolTip("选择一个或多个视频/图片文件加入队列")
        b_dir = QPushButton("选择文件夹批量")
        b_dir.clicked.connect(self._pick_folder)
        b_dir.setToolTip("选择整个文件夹，自动加入其中所有可处理的视频/图片素材")
        dh.addWidget(b_files)
        dh.addWidget(b_dir)
        rv.addWidget(drop)
        self.drop_area = drop

        # 队列
        qcard = Card()
        qh = QHBoxLayout()
        qv = QVBoxLayout()
        qv.setSpacing(2)
        qv.addWidget(QLabel("素材队列", objectName="h2"))
        self.lbl_queue_sub = QLabel("等待加入素材", objectName="muted")
        qv.addWidget(self.lbl_queue_sub)
        qh.addLayout(qv)
        qh.addStretch(1)
        qh.addWidget(QLabel("提示：右键可移除", objectName="muted"))
        qcard.v.addLayout(qh)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["文件", "模式", "模型", "状态", "进度"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        # 平滑滚动：按像素滚动，拖动滚动条时逐像素重绘，避免整格跳动导致的卡顿
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.Fixed)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.Fixed)
        hh.setSectionResizeMode(4, QHeaderView.Fixed)
        # 列宽保持原样：文件/模型两列 Stretch，模式/状态/进度固定列
        self.table.setColumnWidth(1, 104)
        self.table.setColumnWidth(3, 72)
        self.table.setColumnWidth(4, 150)
        self.table.setMinimumHeight(260)
        self.table.verticalHeader().setDefaultSectionSize(38)
        qcard.v.addWidget(self.table, 1)

        self.lbl_empty = QLabel("选择或拖入素材后，任务会在这里排队", objectName="muted")
        self.lbl_empty.setAlignment(Qt.AlignCenter)
        self.lbl_empty.setMinimumHeight(90)
        qcard.v.addWidget(self.lbl_empty)

        qb = QHBoxLayout()
        b_clear = QPushButton("清空队列")
        b_clear.clicked.connect(self._clear_queue)
        b_clear.setToolTip("清空素材队列中的所有任务（不影响正在处理的任务）")
        qb.addWidget(b_clear)
        b_del = QPushButton("移除选中")
        b_del.clicked.connect(self._remove_selected)
        b_del.setToolTip("从队列中移除当前选中的素材（也可右键选移除）")
        qb.addWidget(b_del)
        qb.addStretch(1)
        self.btn_start = QPushButton("△  开始队列", objectName="primary")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setToolTip("开始依次处理队列中的所有素材，并跳转到进度页查看实时日志")
        self.btn_start.clicked.connect(self._start_queue)
        qb.addWidget(self.btn_start)
        qcard.v.addLayout(qb)
        rv.addWidget(qcard, 1)

        # 左右分栏：右侧素材区固定宽度，左侧参数区占据剩余全部空间
        # （改用 QHBoxLayout 直接固定右栏宽度，彻底避免 QSplitter 拖动/重分配把素材区撑大或压窄）
        right.setFixedWidth(360)
        root.addWidget(left_scroll, 1)
        root.addWidget(right, 0)
        return page


    def _build_quick_settings(self):
        card = Card()
        card.v.addWidget(QLabel("处理设置", objectName="h2"))
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)

        self.cb_sr = QComboBox()
        _fill_combo(self.cb_sr, list(self.sr_map) or ["（没有找到超分模型）"])
        self.cb_sr.setMinimumWidth(250)
        self.cb_sr.setToolTip("超分模型分类：动漫主推 / 老番修复 / 真人游戏等，悬停查看用途")
        for _i, _lbl in enumerate(self.sr_map):
            if "Real-CUGAN 2x" in _lbl and "主推" in _lbl:
                self.cb_sr.setCurrentIndex(_i)
                break
        else:
            # 没有主推模型时，回退到列表第一项
            if self.sr_map:
                self.cb_sr.setCurrentIndex(0)
        self.lbl_sr_desc = QLabel("")
        self.lbl_sr_desc.setObjectName("hint")
        self.lbl_sr_desc.setWordWrap(True)
        self.cb_sr.currentTextChanged.connect(self._sync_sr_desc)
        self.cb_vfi = QComboBox()
        _fill_combo(self.cb_vfi, list(self.rife_map) or ["（没有找到 RIFE 模型）"])
        self.cb_vfi.setMinimumWidth(150)
        self.cb_vfi.setToolTip("RIFE 补帧模型：动漫向 / 真人游戏 / 高画质 heavy 等分类，悬停查看用途")
        self.lbl_vfi_desc = QLabel("")
        self.lbl_vfi_desc.setObjectName("hint")
        self.lbl_vfi_desc.setWordWrap(True)
        self.cb_vfi.currentTextChanged.connect(self._sync_vfi_desc)

        self.cb_fps_mode = QComboBox()
        self.cb_fps_mode.addItems(["2×", "3×", "4×", "5×"])
        self.cb_fps_mode.setToolTip("补帧倍率：2× 即每两帧之间插一帧，帧率翻倍。\n"
                                    "倍率越高画面越流畅，但帧数越多、耗时越长、体积越大。")
        self.rb_mult = QRadioButton("按倍率")
        self.rb_fps = QRadioButton("按输出帧率")
        self.rb_mult.setToolTip("按倍率补帧：选择 2×/3×/4×/5×，在源帧率基础上翻倍（如 24fps→48fps）")
        self.rb_fps.setToolTip("按输出帧率补帧：直接指定目标帧率（如 60fps、120fps），\n"
                               "适合把任意源帧率统一到标准帧率")
        self.fps_group = QButtonGroup(self)
        self.fps_group.setExclusive(True)
        self.fps_group.addButton(self.rb_mult)
        self.fps_group.addButton(self.rb_fps)
        self.sp_fps = QSpinBox()
        self.sp_fps.setRange(8, 480)
        self.sp_fps.setSuffix(" fps")
        self.sp_fps.setValue(120)
        self.sp_fps.setEnabled(False)
        self.sp_fps.setToolTip("目标输出帧率：60 流畅、120 顺滑。帧率越高帧数越多，\n"
                               "耗时和体积成正比增加，建议按素材类型选择")
        self.rb_mult.toggled.connect(lambda c: self._sync_fps())
        self.rb_fps.toggled.connect(lambda c: self._sync_fps())
        self.mult_box = QWidget()
        mh = QHBoxLayout(self.mult_box)
        mh.setContentsMargins(0, 0, 0, 0)
        mh.setSpacing(8)
        mh.addWidget(self.rb_mult)
        mh.addWidget(self.cb_fps_mode, 1)
        self.fps_box = QWidget()
        fh = QHBoxLayout(self.fps_box)
        fh.setContentsMargins(0, 0, 0, 0)
        fh.setSpacing(8)
        fh.addWidget(self.rb_fps)
        fh.addWidget(self.sp_fps, 1)
        self.rb_mult.setChecked(True)

        self.cb_enc = QComboBox()
        self.cb_enc.addItems(self.encoders)
        self.cb_enc.setToolTip("编码器：H265 比 H264 体积更小、画质更好；NVENC/AMF/QSV 分别走\n"
                               "英伟达 / AMD / 英特尔显卡硬件编码，速度快、几乎不占 CPU；\n"
                               "10bit 色彩过渡更平滑。列表只显示当前显卡能用的硬件档")
        for _pref in ("H265 10bit NVENC", "H265 NVENC", "H264 NVENC"):
            if _pref in self.encoders:
                self.cb_enc.setCurrentText(_pref)
                break
        else:
            # 没有 NVENC（A 卡 / Intel / 纯软编机器）：按可用列表挑最合适的默认
            _d = vd.default_encoder(self.encoders)
            if _d in self.encoders:
                self.cb_enc.setCurrentText(_d)
        self.cb_rate = QComboBox()
        _fill_combo(self.cb_rate, ["CRF", "目标码率"])
        self.cb_rate.setToolTip("码率控制方式：CRF 按质量恒定（推荐，画质稳定）；\n"
                                "目标码率按固定码率（体积可控，但复杂画面可能糊）")
        self.sp_q = QSpinBox()
        self.sp_q.setRange(0, 200)
        self.sp_q.setValue(20)
        self.sp_q.setToolTip("CRF 越大体积越小、画质略降（推荐 18~23）；\n"
                             "16 接近无损但体积很大，20 是高画质与体积的平衡点，23 更省空间")
        self.lbl_q = QLabel(_tl("CRF / Mbps"), objectName="muted")
        self.cb_rate.currentTextChanged.connect(
            lambda s: self.lbl_q.setText(_tl("目标 Mbps" if _cb_val(self.cb_rate) == "目标码率"
                                             else "CRF / 质量")))

        self.cb_res = QComboBox()
        _fill_combo(self.cb_res, OUT_RES)
        self.cb_res.setToolTip("输出分辨率：源分辨率=保持原样（超分后按模型倍率放大输出）；\n"
                               "百分比=缩放；HD/UHD 预设=固定分辨率。注意超分模型自带固定倍率，\n"
                               "最终尺寸由「超分倍率 × 源分辨率」决定")
        self.cb_fmt = QComboBox()
        _fill_combo(self.cb_fmt, OUT_FMT)
        self.cb_fmt.setToolTip("输出格式：MP4/MKV 为视频文件；PNG/JPG/WEBP 序列为逐帧图片，\n"
                               "适合后期再处理，但比视频慢很多")
        self.cb_dev = QComboBox()
        self.cb_dev.addItems(["GPU", "CPU"])
        self.cb_dev.setToolTip("推理设备：GPU 走显卡（快几十倍，推荐）；CPU 走处理器（慢，\n"
                               "仅显卡不支持时使用）")
        self.cb_tile = QComboBox()
        _fill_combo(self.cb_tile, ["自动", "128", "192", "256", "512"])
        self.cb_tile.setToolTip("分块大小：超分时把画面切成小方块逐块推理。\n"
                                "自动 = 160（实测在本机 1080p 上最快，比 256 快约 17%）；\n"
                                "显存吃紧或超大分辨率时可手动选 256 / 512")
        self.cb_kernel = QComboBox()
        _fill_combo(self.cb_kernel, ["内置加速内核"])
        self.cb_kernel.setEnabled(False)
        self.cb_kernel.setToolTip("内置加速内核：常驻 VapourSynth 运行时，模型只加载一次，\n"
                                  "连续处理多个视频无需反复初始化，大幅缩短启动时间")

        self.chk_two = QCheckBox("先超分 → 再补帧（更快，推荐）")
        self.chk_two.setChecked(bool(self.setting.get("sr_first", 1)))
        self.chk_two.setToolTip(
            "勾选（推荐）：先超分，缩到目标分辨率，最后再做补帧。\n"
            "超分只跑源帧（例如 24 帧/秒），补帧在目标分辨率上进行，实测快 3~9 倍。\n\n"
            "取消勾选：先把视频补帧到高帧率，再对每一帧超分（原顺序）。\n"
            "超分的帧数会被放大 5 倍，明显更慢。")
        self.chk_workres = QCheckBox("超分按输出分辨率（更快）")
        self.chk_workres.setChecked(bool(self.setting.get("sr_workres", 0)))
        self.chk_workres.setToolTip(
            "勾选：先把画面缩到「目标分辨率 ÷ 超分倍数」再超分。\n"
            "例：1080p 源、输出 1080p、2× 模型 → 先缩到 540p 再超分到 1080p。\n"
            "省掉「先放大到 4K 再缩回 1080p」的无效算力，超分环节实测快约 3 倍。\n\n"
            "代价：源画面会被先缩小一次，极细的纹理/噪点会被磨平一些，\n"
            "动漫线条影响很小，真人实拍细节优先的话建议不勾。")
        self.chk_keep = QCheckBox("保留补帧中间片")
        self.chk_keep.setChecked(True)
        self.chk_keep.setToolTip(
            "勾选：超分+补帧拆成两段跑，第 1 段先落一个中间片（MKV）到\n"
            "「片子名_补帧中间片」目录里（勾了「先超分」则是 _超分中间片），\n"
            "方便对比画质或单独复用。代价是多一次编码+解码，整体大约慢一倍。\n\n"
            "不勾选：补帧和超分在同一条流水线里一次跑完，不产生中间文件（更快）。")
        self.chk_keep.setEnabled(False)
        self.chk_dedup = QCheckBox("帧流法")
        self.chk_dedup.setChecked(True)
        self.chk_dedup.setToolTip("帧流法：扫描相邻源帧，删除重复帧后重建时间轴，\n"
                                  "再按目标帧率插帧，避免把重复帧也拿去补帧造成伪影")
        self.chk_scene = QCheckBox("切镜保护")
        self.chk_scene.setToolTip("切镜保护：检测镜头切换，在切镜处不插帧，避免转场时出现\n"
                                  "撕裂/重影；动漫和剪辑视频建议开启")
        self.chk_hw = QCheckBox("硬件解码")
        self.chk_hw.setChecked(True)
        self.chk_hw.setToolTip("硬件解码：用显卡解码源视频，减轻 CPU 负担、加快读取速度；\n"
                               "个别特殊编码格式可能需关闭")
        self.chk_turbo = QCheckBox("日志增速")
        self.chk_turbo.setToolTip("日志增速：降低日志刷新频率、精简非关键日志，减少界面线程开销，\n"
                                  "从而加快处理速度；同时启用超分 fp16 推理（约快 2~3 倍）")
        self.chk_trt = QCheckBox("TensorRT 加速（NVIDIA 显卡）")
        self.chk_trt.setChecked(bool(self.setting.get("use_trt", 0)))
        self._trt_tip = (
            "用 NVIDIA TensorRT 跑超分，比默认的 ncnn 快约 2~4 倍。\n"
            "第一次处理某个模型 + 分辨率组合时要先构建引擎（几分钟），\n"
            "引擎会缓存复用，之后每次都秒开。\n\n"
            "要求：NVIDIA 显卡，且 vrt/plugins 内已放置 vstrt.dll 与 TensorRT 运行库。\n"
            "不满足条件时不生效，自动回退 ncnn，不影响正常处理。")
        self.chk_trt.setToolTip(self._trt_tip)
        self.sp_dup = QDoubleSpinBox()
        self.sp_dup.setRange(0.0, 5.0)
        self.sp_dup.setDecimals(2)
        self.sp_dup.setSingleStep(0.05)
        self.sp_dup.setValue(0.25)
        self.sp_dup.setToolTip("帧流法阈值：相邻帧差低于该值按重复帧丢弃；填 0 等于关闭。\n"
                               "数值越大判定越宽松、删得越多；默认 0.25 适合大多数素材")
        self.dedup_wrap = QWidget()
        dedup_h = QHBoxLayout(self.dedup_wrap)
        dedup_h.setContentsMargins(0, 0, 0, 0)
        dedup_h.setSpacing(6)
        dedup_h.addWidget(self.chk_dedup)
        dedup_h.addWidget(QLabel("阈值", objectName="muted"))
        dedup_h.addWidget(self.sp_dup)
        dedup_h.addStretch(1)

        rows = [
            ("内核", self.cb_kernel, "推理设备", self.cb_dev),
            ("超分模型", self.cb_sr, "补帧模型", self.cb_vfi),
            ("补帧方式", self.mult_box, "输出帧率", self.fps_box),
            ("编码器", self.cb_enc, "码率", self.cb_rate),
            ("", self.sp_q, "", self.lbl_q),
            ("输出分辨率", self.cb_res, "输出格式", self.cb_fmt),
            ("分块", self.cb_tile, "", QLabel("", objectName="muted")),
        ]
        r = 0
        for l1, w1, l2, w2 in rows:
            if l1:
                g.addWidget(QLabel(l1, objectName="muted"), r, 0)
            g.addWidget(w1, r, 1)
            if l2:
                g.addWidget(QLabel(l2, objectName="muted"), r, 2)
            g.addWidget(w2, r, 3)
            r += 1
        chk = QGridLayout()
        chk.setHorizontalSpacing(22)
        chk.setVerticalSpacing(6)
        for _i, w in enumerate((self.chk_two, self.chk_workres, self.chk_trt,
                                self.chk_keep, self.dedup_wrap, self.chk_scene,
                                self.chk_hw, self.chk_turbo)):
            chk.addWidget(w, _i // 3, _i % 3)
        g.addWidget(self.lbl_sr_desc, r, 0, 1, 4)
        r += 1
        g.addWidget(self.lbl_vfi_desc, r, 0, 1, 4)
        r += 1
        g.addLayout(chk, r, 0, 1, 4)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)
        card.v.addLayout(g)

        for cb in (self.cb_sr, self.cb_vfi, self.cb_enc):
            cb.currentIndexChanged.connect(lambda _=0: self._refresh_table())
        self.cb_kernel.currentTextChanged.connect(lambda _=0: self._sync_mode())
        self.cb_kernel.currentTextChanged.connect(lambda _=0: self._refresh_table())
        self.chk_dedup.toggled.connect(lambda _=0: self._sync_mode())
        return card

    # ------------------------------------------------------------ 其它页
    def _build_progress_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(12)
        v.addWidget(QLabel("进度", objectName="h1"))
        v.addWidget(QLabel("当前任务的处理进度与日志。", objectName="muted"))
        card = Card()
        self.lbl_cur = QLabel("尚无任务", objectName="h2")
        card.v.addWidget(self.lbl_cur)
        self.pb_main = QProgressBar()
        self.pb_main.setRange(0, 100)
        self.pb_main.setValue(0)
        self.pb_main.setFixedHeight(18)
        card.v.addWidget(self.pb_main)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        card.v.addWidget(self.log, 1)
        h = QHBoxLayout()
        h.addStretch(1)
        self.btn_stop = QPushButton("停止", objectName="stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_queue)
        h.addWidget(self.btn_stop)
        card.v.addLayout(h)
        v.addWidget(card, 1)
        return page

    def _build_convert_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(12)
        v.addWidget(QLabel("格式转换", objectName="h1"))
        v.addWidget(QLabel("只换容器 / 编码，不做 AI 处理。", objectName="muted"))
        card = Card()
        self.conv_list = QListWidget()
        self.conv_list.setMinimumHeight(220)
        card.v.addWidget(self.conv_list)
        h = QHBoxLayout()
        b_add = QPushButton("添加视频")
        b_add.clicked.connect(self._conv_add)
        b_clr = QPushButton("清空")
        b_clr.clicked.connect(self._conv_clear)
        h.addWidget(b_add)
        h.addWidget(b_clr)
        h.addStretch(1)
        card.v.addLayout(h)
        g = QGridLayout()
        g.addWidget(QLabel("输出目录", objectName="muted"), 0, 0)
        self.conv_out = QLineEdit()
        self.conv_out.setPlaceholderText("留空 = 源目录")
        g.addWidget(self.conv_out, 0, 1)
        b_out = QPushButton("浏览")
        b_out.clicked.connect(self._pick_conv_out)
        g.addWidget(b_out, 0, 2)
        g.addWidget(QLabel("容器", objectName="muted"), 1, 0)
        self.conv_fmt = QComboBox()
        self.conv_fmt.addItems(["MP4", "MKV"])
        g.addWidget(self.conv_fmt, 1, 1)
        g.addWidget(QLabel("编码器", objectName="muted"), 2, 0)
        self.conv_enc = QComboBox()
        self.conv_enc.addItems(self.encoders)
        for _pref in ("H265 10bit NVENC", "H265 NVENC", "H264 NVENC"):
            if _pref in self.encoders:
                self.conv_enc.setCurrentText(_pref)
                break
        g.addWidget(self.conv_enc, 2, 1)
        g.setColumnStretch(1, 1)
        card.v.addLayout(g)
        h2 = QHBoxLayout()
        h2.addStretch(1)
        self.btn_conv = QPushButton("开始转换", objectName="primary")
        self.btn_conv.clicked.connect(self._start_convert)
        h2.addWidget(self.btn_conv)
        card.v.addLayout(h2)
        v.addWidget(card, 1)
        return page

    def _build_bench_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(12)
        v.addWidget(QLabel("GPU 性能测试", objectName="h1"))
        v.addWidget(QLabel("用当前超分模型跑 512×512 基准，测本机实际速度。", objectName="muted"))
        card = Card()
        self.lbl_gpu = QLabel("显卡：%s" % self.gpu, objectName="h2")
        self.lbl_bench = QLabel("尚未测试", objectName="muted")
        self.lbl_bench.setWordWrap(True)
        card.v.addWidget(self.lbl_gpu)
        card.v.addWidget(self.lbl_bench)
        self.pb_bench = QProgressBar()
        self.pb_bench.setRange(0, 100)
        self.pb_bench.setValue(0)
        card.v.addWidget(self.pb_bench)
        h = QHBoxLayout()
        h.addStretch(1)
        self.btn_bench = QPushButton("超分测试", objectName="primary")
        self.btn_bench.clicked.connect(self._start_bench)
        self.btn_bench_vfi = QPushButton("补帧测试")
        self.btn_bench_vfi.clicked.connect(self._start_bench_vfi)
        h.addWidget(self.btn_bench_vfi)
        h.addWidget(self.btn_bench)
        card.v.addLayout(h)
        v.addWidget(card)
        v.addStretch(1)
        return page

    def _build_update_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(12)
        v.addWidget(QLabel("官网更新", objectName="h1"))
        v.addWidget(QLabel("检查新版本、查看作者公告；更新源为 GitHub。", objectName="muted"))
        card = Card()
        card.v.addWidget(QLabel("%s · %s" % (APP_NAME, APP_VERSION), objectName="h2"))
        _build_lb = QLabel(_tl("构建：%s") % BUILD, objectName="muted")
        _build_lb.setProperty("i18n_build", True)
        card.v.addWidget(_build_lb)

        # 更新状态标签：默认「尚未检查」，点击检查后动态更新
        self.lbl_update_state = QLabel("尚未检查更新。", objectName="muted")
        self.lbl_update_state.setWordWrap(True)
        card.v.addWidget(self.lbl_update_state)

        # 公告展示区（默认隐藏，拉到公告后显示）
        self.ann_card = Card()
        self.ann_card.setVisible(False)
        self.lbl_ann_title = QLabel("", objectName="h2")
        self.lbl_ann_title.setProperty("i18n_key", "__announce__")
        self.lbl_ann_body = QLabel("", objectName="muted")
        self.lbl_ann_body.setWordWrap(True)
        self.lbl_ann_body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.ann_card.v.addWidget(self.lbl_ann_title)
        self.ann_card.v.addWidget(self.lbl_ann_body)
        v.addWidget(self.ann_card)

        h = QHBoxLayout()
        b_dir = QPushButton("打开程序目录")
        b_dir.clicked.connect(lambda: os.startfile(paths.ROOT))
        self.b_check = QPushButton("检查更新")
        self.b_check.clicked.connect(self._check_update_online)
        b_bili = QPushButton("哔哩哔哩主页")
        b_bili.clicked.connect(lambda: self._open_bilibili())
        b_group = QPushButton("加入聊群")
        b_group.clicked.connect(lambda: self._show_group_dialog())
        b_github = QPushButton("GitHub 官网")
        b_github.setToolTip("打开 CHEN-V 的 GitHub 项目主页（源码、更新日志、提 Issue）")
        b_github.clicked.connect(lambda: self._open_github())
        b_support = QPushButton("支持 CHEN-V", objectName="primary")
        b_support.setToolTip("作者独立开发、全部功能免费；如果它帮到了你，可以自愿支持一下")
        b_support.clicked.connect(lambda: self._show_support_dialog())
        h.addWidget(b_dir)
        h.addWidget(self.b_check)
        h.addWidget(b_bili)
        h.addWidget(b_group)
        h.addWidget(b_github)
        h.addWidget(b_support)
        h.addStretch(1)
        card.v.addLayout(h)
        v.addWidget(card)
        v.addStretch(1)
        return page

    def _check_update_online(self):
        """后台检查更新 + 公告，结果回主线程刷新 UI。"""
        if not hasattr(self, "lbl_update_state"):
            return
        self.b_check.setEnabled(False)
        self.b_check.setText("检查中…")
        self.lbl_update_state.setText("正在连接更新源…")
        self.lbl_update_state.setObjectName("muted")
        self.lbl_update_state.style().unpolish(self.lbl_update_state)
        self.lbl_update_state.style().polish(self.lbl_update_state)

        local_ver = APP_VERSION.lstrip("Vv")
        try:
            lang_code = self.cb_lang.currentData() or "zh-CN"
        except Exception:
            lang_code = "zh-CN"

        def _done(st):
            # 通过信号回主线程刷新控件（QTimer.singleShot 从后台线程调用不可靠）
            self.update_ready.emit(st)

        updater.check_updates(local_ver, _done, lang=lang_code)

    def _apply_update_state(self, st):
        """把检查结果写回界面（必须在主线程调用）。"""
        if not hasattr(self, "lbl_update_state"):
            return
        self.b_check.setEnabled(True)
        self.b_check.setText("检查更新")

        # 版本
        if st.error and st.latest_ver is None:
            self.lbl_update_state.setText(
                "检查失败：无法连接更新源。\n"
                "可能是网络问题或更新源暂不可用，稍后再试即可。")
            self.lbl_update_state.setObjectName("muted")
        elif st.has_update:
            self.lbl_update_state.setText(
                "发现新版本 %s（当前 %s）。\n"
                "点击下方按钮前往 GitHub 下载。" % (st.latest_tag, APP_VERSION))
            self.lbl_update_state.setObjectName("hint")
        else:
            self.lbl_update_state.setText(
                "已是最新版本（%s）。" % APP_VERSION)
            self.lbl_update_state.setObjectName("muted")
        self.lbl_update_state.style().unpolish(self.lbl_update_state)
        self.lbl_update_state.style().polish(self.lbl_update_state)

        # 公告
        if st.announce_title or st.announce_body:
            if st.announce_title:
                self.lbl_ann_title.setText(st.announce_title)
            if st.announce_body:
                self.lbl_ann_body.setText(st.announce_body)
            self.ann_card.setVisible(True)

    def _show_group_dialog(self):
        """聊群弹窗：显示 QQ 群二维码 + 群号，方便用户扫码加入。"""
        img = os.path.join(paths.ASSETS, "join_group.jpg")
        if not os.path.isfile(img):
            QMessageBox.information(
                self, _tl("加入聊群"),
                _tl("没有找到群聊二维码图片（素材目录：assets）。\n"
                    "程序所有功能依然可以正常使用。"))
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(_tl("加入聊群"))
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)

        title = QLabel(_tl("加入聊群"), objectName="h1")
        lay.addWidget(title)
        sub = QLabel(_tl("欢迎加入 CHEN-V 交流群，反馈问题、交流用法、获取更新。"),
                     objectName="muted")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        pic = QLabel()
        pic.setAlignment(Qt.AlignCenter)
        pix = QPixmap(img)
        if pix.isNull():
            QMessageBox.warning(self, _tl("加入聊群"), _tl("群聊二维码图片无法读取。"))
            return
        # 竖版二维码，缩到合适高度居中显示
        pic.setPixmap(pix.scaled(320, 460, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lay.addWidget(pic)

        no = QLabel(_tl("群号：1130651819"), objectName="h2")
        no.setAlignment(Qt.AlignCenter)
        lay.addWidget(no)

        b_close = QPushButton(_tl("关闭"))
        b_close.clicked.connect(dlg.accept)
        bh = QHBoxLayout()
        bh.addStretch(1)
        bh.addWidget(b_close)
        lay.addLayout(bh)

        dlg.adjustSize()
        dlg.exec()

    def _show_support_dialog(self):
        """打赏弹窗：微信 / 支付宝收款码 + 自愿说明。图片缺失时提示而不是弹空窗。"""
        shots = [(os.path.join(paths.ASSETS, "support_wechat.png"), "微信支付"),
                 (os.path.join(paths.ASSETS, "support_alipay.jpg"), "支付宝")]
        shots = [(p, n) for p, n in shots if os.path.isfile(p)]
        if not shots:
            QMessageBox.information(
                self, _tl("支持 CHEN-V"),
                _tl("没有找到收款码图片（素材目录：assets）。\n"
                    "程序所有功能依然可以正常使用。"))
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(_tl("支持 CHEN-V"))
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)

        title = QLabel(_tl("支持 CHEN-V"), objectName="h1")
        lay.addWidget(title)
        sub = QLabel(_tl("所有功能完全免费。如果这个工具帮你省下了时间，可以请作者喝杯咖啡。"),
                     objectName="muted")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        row = QHBoxLayout()
        row.setSpacing(16)
        for path, name in shots:
            col = QVBoxLayout()
            col.setSpacing(6)
            lb = _ClickLabel(lambda p=path: os.startfile(p))
            lb.setAlignment(Qt.AlignCenter)
            lb.setToolTip(_tl("点击用系统看图工具打开，方便扫码"))
            lb.setFixedSize(268, 372)
            lb.setStyleSheet("border-radius:10px;background:rgba(127,127,127,0.10);")
            pix = QPixmap(path)
            if not pix.isNull():
                lb.setPixmap(pix.scaled(264, 368, Qt.KeepAspectRatio,
                                        Qt.SmoothTransformation))
            cap = QLabel(_tl(name), objectName="h2")
            cap.setAlignment(Qt.AlignCenter)
            col.addWidget(lb)
            col.addWidget(cap)
            row.addLayout(col)
        row.addStretch(1)
        lay.addLayout(row)

        note = QLabel(_tl("自愿支持作者。捐赠与否不影响任何功能使用。"), objectName="hint")
        note.setAlignment(Qt.AlignCenter)
        note.setWordWrap(True)
        lay.addWidget(note)

        b_close = QPushButton(_tl("关闭"))
        b_close.clicked.connect(dlg.accept)
        bh = QHBoxLayout()
        bh.addStretch(1)
        bh.addWidget(b_close)
        lay.addLayout(bh)

        dlg.adjustSize()
        dlg.exec()

    def _open_bilibili(self):
        """在系统默认浏览器打开作者的哔哩哔哩主页。"""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl("https://b23.tv/X2FYRsA"))

    def _open_github(self):
        """在系统默认浏览器打开 CHEN-V 的 GitHub 项目主页。"""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(updater.project_page_url()))

    def _build_settings_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        # 滚动条常驻：展开/收起工具路径时内容高度变化，若滚动条时有时无，
        # 视口宽度会跟着变 10px，整页控件会横向重排一次，看着像闪一下。
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        page = QWidget()
        scroll.setWidget(page)
        v = QVBoxLayout(page)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(12)
        v.addWidget(QLabel("设置", objectName="h1"))
        v.addWidget(QLabel("工作目录、默认输出、运行环境与工具路径。", objectName="muted"))
        card = Card()

        # 语言
        lang_row = QHBoxLayout()
        lang_row.setSpacing(10)
        lang_row.addWidget(QLabel("语言", objectName="muted"))
        self.cb_lang = QComboBox()
        for code, name in _i18n.LANG_NAMES.items():
            self.cb_lang.addItem(name, code)
        self.cb_lang.setMinimumWidth(160)
        self.cb_lang.setToolTip("选择界面显示语言")
        self.cb_lang.currentIndexChanged.connect(self._apply_language)
        lang_row.addWidget(self.cb_lang)
        lang_row.addStretch(1)
        card.v.addLayout(lang_row)

        dr = QHBoxLayout()
        dr.addWidget(QLabel("默认输出目录", objectName="muted"))
        self.set_out = QLineEdit()
        self.set_out.setPlaceholderText("留空 = 源目录")
        dr.addWidget(self.set_out, 1)
        b_out = QPushButton("浏览")
        b_out.clicked.connect(self._pick_set_out)
        dr.addWidget(b_out)
        card.v.addLayout(dr)

        # 运行环境
        eh = QHBoxLayout()
        ev = QVBoxLayout()
        ev.setSpacing(2)
        ev.addWidget(QLabel("运行环境", objectName="h2"))
        ev.addWidget(QLabel("处理工具与组件状态", objectName="muted"))
        eh.addLayout(ev)
        eh.addStretch(1)
        b_check = QPushButton("检查")
        b_check.clicked.connect(self._check_tools)
        eh.addWidget(b_check)
        card.v.addLayout(eh)
        self.env_grid = QGridLayout()
        self.env_grid.setHorizontalSpacing(28)
        self.env_grid.setVerticalSpacing(14)
        card.v.addLayout(self.env_grid)

        self.btn_paths = QPushButton(_tl("工具路径（高级）") + "  ▾", objectName="link")
        self.btn_paths.setStyleSheet(
            "text-align:left;border:none;background:transparent;padding:6px 0;")
        self.btn_paths.clicked.connect(self._toggle_paths)
        card.v.addWidget(self.btn_paths)
        self.paths_panel = QWidget()
        self.path_grid = QGridLayout(self.paths_panel)
        self.path_grid.setHorizontalSpacing(12)
        self.path_grid.setVerticalSpacing(10)
        self.path_edits = {}
        self.paths_panel.setVisible(False)
        card.v.addWidget(self.paths_panel)

        h = QHBoxLayout()
        b_open = QPushButton("打开工作目录")
        b_open.clicked.connect(lambda: os.startfile(paths.WORK_DIR))
        b_clear = QPushButton("清理缓存")
        b_clear.clicked.connect(self._purge_cache)
        h.addWidget(b_open)
        h.addWidget(b_clear)
        h.addStretch(1)
        b_save = QPushButton("保存设置", objectName="primary")
        b_save.clicked.connect(self._save_from_settings)
        h.addWidget(b_save)
        card.v.addLayout(h)
        v.addWidget(card)
        v.addStretch(1)
        self._rebuild_env()
        return scroll

    # ------------------------------------------------------------ 界面美化页
    def _build_theme_page(self):
        """独立的界面美化页面：主题 + 颜色 + 字体 + 背景图 + 通透度 + 蒙版暗度。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        scroll.setWidget(page)
        v = QVBoxLayout(page)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(12)
        v.addWidget(QLabel("界面美化", objectName="h1"))
        v.addWidget(QLabel("主题、配色、字体与背景，打造你的专属界面。", objectName="muted"))

        card = Card()

        # ---- 界面风格（主题）----
        th_wrap = QVBoxLayout()
        th_wrap.setSpacing(8)
        th_head = QHBoxLayout()
        th_head.addWidget(QLabel("界面风格", objectName="h2"))
        th_head.addWidget(QLabel("选择配色主题，立即应用到整个界面", objectName="muted"))
        th_head.addStretch(1)
        th_wrap.addLayout(th_head)
        self.theme_group = QButtonGroup(self)
        self.theme_group.setExclusive(True)
        self.theme_buttons = {}
        th_row = QHBoxLayout()
        th_row.setSpacing(10)
        for name in ["浅色", "深色", "紫色"]:
            b = QPushButton(name, objectName="mode")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(34)
            self.theme_group.addButton(b)
            self.theme_buttons[name] = b
            b.clicked.connect(lambda _=False, n=name: self._apply_theme(n))
            th_row.addWidget(b, 1)
        th_wrap.addLayout(th_row)
        card.v.addLayout(th_wrap)

        line_a = QFrame()
        line_a.setFixedHeight(1)
        line_a.setStyleSheet("background:#eef2f7;border:none;")
        card.v.addWidget(line_a)

        # ---- 界面颜色（强调色 + 文字颜色）----
        color_wrap = QVBoxLayout()
        color_wrap.setSpacing(8)
        color_head = QHBoxLayout()
        color_head.addWidget(QLabel("界面颜色", objectName="h2"))
        color_head.addWidget(QLabel("自定义主题强调色与文字颜色", objectName="muted"))
        color_head.addStretch(1)
        color_wrap.addLayout(color_head)
        ac_row = QHBoxLayout()
        ac_row.setSpacing(10)
        ac_row.addWidget(QLabel("主题色（强调色）", objectName="muted"))
        self.sw_accent = QLabel()
        self.sw_accent.setFixedSize(28, 28)
        ac_row.addWidget(self.sw_accent)
        b_accent = QPushButton("选择颜色")
        b_accent.clicked.connect(self._pick_accent_color)
        ac_row.addWidget(b_accent)
        ac_row.addStretch(1)
        color_wrap.addLayout(ac_row)
        tx_row = QHBoxLayout()
        tx_row.setSpacing(10)
        tx_row.addWidget(QLabel("文字颜色", objectName="muted"))
        self.sw_text = QLabel()
        self.sw_text.setFixedSize(28, 28)
        tx_row.addWidget(self.sw_text)
        b_text = QPushButton("选择颜色")
        b_text.clicked.connect(self._pick_text_color)
        tx_row.addWidget(b_text)
        b_reset = QPushButton("恢复默认")
        b_reset.clicked.connect(self._reset_colors)
        tx_row.addWidget(b_reset)
        tx_row.addStretch(1)
        color_wrap.addLayout(tx_row)
        card.v.addLayout(color_wrap)
        self._update_color_swatches()

        # ---- 字体描边（自调强度）----
        outline_row = QHBoxLayout()
        outline_row.setSpacing(10)
        outline_row.addWidget(QLabel("字体描边", objectName="muted"))
        self.sl_outline = QSlider(Qt.Horizontal)
        self.sl_outline.setRange(0, 10)
        self.sl_outline.setValue(int(getattr(self, "text_outline", 0)))
        self.sl_outline.valueChanged.connect(self._apply_text_outline)
        self.sl_outline.sliderReleased.connect(self._on_outline_released)
        outline_row.addWidget(self.sl_outline, 1)
        self.lbl_outline = QLabel(("关闭" if self.sl_outline.value() == 0 else "%d" % self.sl_outline.value()), objectName="muted")
        self.lbl_outline.setFixedWidth(42)
        outline_row.addWidget(self.lbl_outline)
        card.v.addLayout(outline_row)
        card.v.addWidget(QLabel("数值越大，文字描边越明显，背景复杂时更清晰（0=关闭）", objectName="hint"))

        line_b = QFrame()
        line_b.setFixedHeight(1)
        line_b.setStyleSheet("background:#eef2f7;border:none;")
        card.v.addWidget(line_b)

        # ---- 界面字体 ----
        fr = QHBoxLayout()
        fv = QVBoxLayout()
        fv.setSpacing(2)
        fv.addWidget(QLabel("界面字体", objectName="h2"))
        fv.addWidget(QLabel("可选择系统已安装字体", objectName="muted"))
        fr.addLayout(fv)
        fr.addStretch(1)
        self.cb_font = QComboBox()
        self._fill_system_fonts()
        self.cb_font.setMinimumWidth(200)
        self.cb_font.setEditable(True)
        self.cb_font.setInsertPolicy(QComboBox.NoInsert)
        self.cb_font.lineEdit().setPlaceholderText("输入关键字搜索字体…")
        self.cb_font.view().setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.cb_font.view().setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.cb_font.currentTextChanged.connect(lambda _=0: self._apply_font_choice())
        fr.addWidget(self.cb_font)
        card.v.addLayout(fr)

        line_c = QFrame()
        line_c.setFixedHeight(1)
        line_c.setStyleSheet("background:#eef2f7;border:none;")
        card.v.addWidget(line_c)

        # ---- 背景图 ----
        bg_head = QHBoxLayout()
        bg_fv = QVBoxLayout()
        bg_fv.setSpacing(2)
        bg_fv.addWidget(QLabel("界面背景", objectName="h2"))
        bg_fv.addWidget(QLabel("选择一张图片作为全窗口背景（半透明透出）", objectName="muted"))
        bg_head.addLayout(bg_fv)
        bg_head.addStretch(1)
        b_bg = QPushButton("选择背景图")
        b_bg.clicked.connect(self._pick_bg)
        b_bgc = QPushButton("清除背景")
        b_bgc.clicked.connect(self._clear_bg)
        b_we = QPushButton("选择壁纸目录")
        b_we.clicked.connect(self._pick_wallpaper)
        bg_head.addWidget(b_bg)
        bg_head.addWidget(b_we)
        bg_head.addWidget(b_bgc)
        card.v.addLayout(bg_head)
        self.lbl_bg = QLabel("", objectName="muted")
        card.v.addWidget(self.lbl_bg)

        # 拖动性能：可选在拖动期间暂停动态壁纸（默认关闭，壁纸正常播放）
        self.chk_pause_bg = QCheckBox("拖动时暂停动态壁纸")
        self.chk_pause_bg.setChecked(bool(self.setting.get("pause_bg_on_drag", 0)))
        self.chk_pause_bg.setToolTip(
            "开启后：拖着文件经过程序窗口时临时暂停视频壁纸，把显卡与主线程让给拖放响应，\n"
            "拖动手感更跟手；松手或拖走立即恢复播放。\n"
            "关闭后：壁纸全程连续播放（默认）。")
        self.chk_pause_bg.toggled.connect(self._on_pause_bg_toggled)
        card.v.addWidget(self.chk_pause_bg)

        line_d = QFrame()
        line_d.setFixedHeight(1)
        line_d.setStyleSheet("background:#eef2f7;border:none;")
        card.v.addWidget(line_d)

        # ---- 通透度 ----
        gl_row = QHBoxLayout()
        gl_row.addWidget(QLabel("界面通透度", objectName="muted"))
        self.sl_glass = QSlider(Qt.Horizontal)
        self.sl_glass.setRange(0, int(_GLASS_MAX * 100))
        self.sl_glass.setValue(int(getattr(self, "glass", 0.0) * 100))
        self.sl_glass.valueChanged.connect(self._on_glass_changed)
        self.sl_glass.sliderReleased.connect(self._on_glass_released)
        gl_row.addWidget(self.sl_glass, 1)
        self.lbl_glass = QLabel("%d%%" % self.sl_glass.value(), objectName="muted")
        self.lbl_glass.setFixedWidth(46)
        gl_row.addWidget(self.lbl_glass)
        card.v.addLayout(gl_row)
        card.v.addWidget(QLabel("数值越大，面板越透明，背景图透出越明显", objectName="hint"))

        line_e = QFrame()
        line_e.setFixedHeight(1)
        line_e.setStyleSheet("background:#eef2f7;border:none;")
        card.v.addWidget(line_e)

        # ---- 蒙版暗度 ----
        bg_row = QHBoxLayout()
        bg_row.addWidget(QLabel("蒙版暗度", objectName="muted"))
        self.sl_bg_dark = QSlider(Qt.Horizontal)
        self.sl_bg_dark.setRange(0, 90)
        self.sl_bg_dark.setValue(int(self.setting.get("bg_dark", 42)))
        self.sl_bg_dark.valueChanged.connect(self._apply_bg_dark)
        bg_row.addWidget(self.sl_bg_dark, 1)
        self.lbl_bg_dark = QLabel("%d%%" % self.sl_bg_dark.value(), objectName="muted")
        self.lbl_bg_dark.setFixedWidth(42)
        bg_row.addWidget(self.lbl_bg_dark)
        card.v.addLayout(bg_row)
        card.v.addWidget(QLabel("暗度越低背景越亮，越高背景越暗；配合通透度调整", objectName="hint"))

        v.addWidget(card)
        v.addStretch(1)
        self._update_bg_label()
        return scroll

    def _update_bg_label(self):
        if hasattr(self, "lbl_bg"):
            v = self.setting.get("bg_video", "")
            p = self.setting.get("bg", "")
            if v and os.path.isfile(v):
                self.lbl_bg.setText("● 已设置视频背景")
            elif p and os.path.isfile(p):
                self.lbl_bg.setText("● 已设置背景图")
            else:
                self.lbl_bg.setText("● 未设置背景图")

    # 通透度拖动：只更新数值 + 标签，样式表通过节流定时器延迟刷新，避免卡顿
    def _on_glass_changed(self, val):
        v = int(val)
        self.glass = v / 100.0
        if hasattr(self, "lbl_glass"):
            self.lbl_glass.setText("%d%%" % v)
        # 拖动中：只让半透明容器重绘自己（约 11ms），样式表一概不动
        self._preview_glass(self.glass)
        if hasattr(self, "_glass_timer"):
            self._glass_timer.start()          # 停手 1.5 秒后统一提交

    def _glass_panels(self):
        """缓存自绘容器，避免每次拖动都遍历整棵控件树。"""
        if not self._glass_cache:
            self._glass_cache = self.findChildren(GlassPanel)
        return self._glass_cache

    def _preview_glass(self, glass):
        """实时预览：只更新自绘容器的背景透明度并重绘，不动 QSS。"""
        _PAINT["glass"] = _glass_alphas(self.theme, glass)
        for f in self._glass_panels():
            f.update()

    def _apply_glass_refresh(self):
        """停手后一次性提交：重建样式表让按钮/输入框等也跟上，再写盘。"""
        self.setting["glass"] = self.glass
        self._refresh_stylesheet(scope="window")
        self._save_settings()

    def _on_glass_released(self):
        # 松手不立刻提交，交给 1.5 秒防抖（键盘/点凹槽也会走到同一个计时器）
        if hasattr(self, "_glass_timer"):
            self._glass_timer.start()

    def _tool_specs(self):
        """运行环境检测项（每次重建都重新探测，状态实时）。

        字段说明：
          key       标识，与设置里保存的路径键一致
          name/desc 标题与说明（中文原文，显示时按当前语言翻译）
          path      对应路径，显示在「工具路径（高级）」里
          ok        是否就绪
          kind      file / dir，决定「选择」按钮选文件还是目录
          pickable  是否允许手改路径（模型、内核是内置的，只能打开查看）
          optional  缺失是否算可选组件（可选缺失只提示，不算未配置）
          count     非 None 时状态显示为「● N 个模型」
        """
        models = paths.MODELS
        sr_dir = os.path.join(models, "sr")                       # Real-CUGAN onnx 权重
        esr_root = os.path.join(models, "sr_ncnn", "ncnnRealESR", "models")
        esr = os.path.join(esr_root, "realesrgan-x4plus")
        vfi = os.path.join(models, "vfi_rife")
        plugins = os.path.join(paths.ROOT, "vrt", "plugins")
        trt_dir = os.path.join(plugins, "vsmlrt-cuda")
        kernel_py = os.path.join(paths.ROOT, "vrt", "python", "python.exe")

        def has(p):
            return bool(p) and os.path.exists(p)

        def count_files(folder, patterns=("*",)):
            if not os.path.isdir(folder):
                return 0
            n = 0
            for pat in patterns:
                n += len(glob.glob(os.path.join(folder, pat)))
            return n

        # Real-CUGAN：models/sr 下的 up2x/3x/4x -latest 系列 onnx
        cugan_n = count_files(sr_dir, ("up2x-*.onnx", "up3x-*.onnx", "up4x-*.onnx"))
        # Real-ESRGAN：ncnn 权重按模型名分目录存放
        esr_n = len([d for d in glob.glob(os.path.join(esr_root, "*")) if os.path.isdir(d)])
        # RIFE：models/vfi_rife 下的 rife-v* 目录（下划线开头的是坏档，跳过）
        rife_n = len([d for d in glob.glob(os.path.join(vfi, "rife-v*"))
                      if os.path.isdir(d) and not os.path.basename(d).startswith("_")])
        # VapourSynth 内核：缺任一个推理插件都跑不起来
        vs_ok = has(os.path.join(plugins, "vsncnn.dll")) and \
            has(os.path.join(plugins, "librife.dll"))
        trt_ok = kernel_backend.has_trt()

        return [
            dict(key="ffmpeg", name="FFmpeg", desc="视频解码与编码",
                 path=self.ffmpeg or "", ok=has(self.ffmpeg), kind="file",
                 pickable=True, optional=False, count=None),
            dict(key="realcugan", name="Real-CUGAN", desc="动漫超分 · 降噪 / 保守",
                 path=sr_dir, ok=cugan_n > 0, kind="dir",
                 pickable=False, optional=False, count=cugan_n),
            dict(key="realesrgan", name="Real-ESRGAN", desc="通用超分 · 实拍修复",
                 path=esr, ok=esr_n > 0, kind="dir",
                 pickable=False, optional=False, count=esr_n),
            dict(key="rife", name="RIFE", desc="视频补帧 · 插帧引擎",
                 path=vfi, ok=rife_n > 0, kind="dir",
                 pickable=False, optional=False, count=rife_n),
            dict(key="kernel", name="内置加速内核", desc="常驻补帧 / 超分进程",
                 path=kernel_py, ok=kernel_backend.available(), kind="file",
                 pickable=False, optional=False, count=None),
            dict(key="vapoursynth", name="VapourSynth", desc="视频处理内核与推理插件",
                 path=plugins, ok=vs_ok, kind="dir",
                 pickable=False, optional=False, count=None),
            dict(key="tensorrt", name="TensorRT", desc="NVIDIA 显卡推理加速 · 快 2~3 倍",
                 path=trt_dir, ok=trt_ok, kind="dir",
                 pickable=False, optional=True, count=None),
        ]

    def _env_badge(self, sp):
        """环境项右侧的状态徽标：已配置 / N 个模型 / 未配置 / 未安装（可选）。"""
        ok = bool(sp["ok"])
        cnt = sp.get("count")
        if ok and cnt is not None:
            txt = _tl("● %d 个模型") % cnt
        elif ok:
            txt = _tl("● 已配置")
        elif sp.get("optional"):
            txt = _tl("● 未安装（可选）")
        else:
            txt = _tl("● 未配置")
        st = QLabel(txt)
        st.setStyleSheet("color:%s;font-size:12px;" %
                         ("#16a34a" if ok else ("#64748b" if sp.get("optional") else "#94a3b8")))
        if sp.get("optional") and not ok:
            st.setToolTip(_tl("可选加速组件：装好后勾选「TensorRT 加速」可快 2~3 倍，"
                              "未装则自动使用 ncnn。"))
        return st

    def _rebuild_env(self):
        # 关闭重绘，避免销毁重建过程闪烁
        target = self.env_grid.parentWidget()
        if target is not None:
            target.setUpdatesEnabled(False)
        try:
            old = {k: e.text() for k, e in getattr(self, "path_edits", {}).items() if e.text()}
            while self.env_grid.count():
                it = self.env_grid.takeAt(0)
                w = it.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()
            specs = self._tool_specs()
            for i, sp in enumerate(specs):
                ok = bool(sp["ok"])
                box = QWidget()
                h = QHBoxLayout(box)
                h.setContentsMargins(0, 0, 0, 0)
                v = QVBoxLayout()
                v.setSpacing(1)
                v.addWidget(QLabel(_tl(sp["name"]), objectName="h2"))
                v.addWidget(QLabel(_tl(sp["desc"]), objectName="muted"))
                h.addLayout(v)
                h.addStretch(1)
                h.addWidget(self._env_badge(sp))
                self.env_grid.addWidget(box, i // 2, i % 2)

            while self.path_grid.count():
                it = self.path_grid.takeAt(0)
                w = it.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()
            self.path_edits = {}
            for i, sp in enumerate(specs):
                path = sp["path"]
                self.path_grid.addWidget(QLabel(_tl(sp["name"]), objectName="muted"), i, 0)
                ed = QLineEdit(str(path or ""))
                ed.setReadOnly(True)
                self.path_edits[sp["key"]] = ed
                self.path_grid.addWidget(ed, i, 1)
                if sp["pickable"]:
                    b = QPushButton(_tl("选择"))
                    b.clicked.connect(lambda _=False, k=sp["key"], kd=sp["kind"]:
                                      self._choose_tool(k, kd))
                else:
                    # 内置组件（模型 / 内核 / 运行库）路径固定，只给「打开」定位
                    b = QPushButton(_tl("打开"))
                    b.setEnabled(bool(path) and os.path.exists(path))
                    b.clicked.connect(lambda _=False, pp=path: os.startfile(
                        pp if os.path.isdir(pp) else os.path.dirname(pp)))
                self.path_grid.addWidget(b, i, 2)
            extra = [("work", "工作目录", paths.WORK_DIR, "dir"),
                     ("cache", "缓存目录", os.path.join(paths.CACHE_DIR, "vfi_cache"), "dir")]
            start = len(specs)
            for j, (key, name, p, kind) in enumerate(extra):
                r = start + j
                self.path_grid.addWidget(QLabel(_tl(name), objectName="muted"), r, 0)
                ed = QLineEdit(p)
                ed.setReadOnly(True)
                self.path_edits[key] = ed
                self.path_grid.addWidget(ed, r, 1)
                b = QPushButton(_tl("打开"))
                b.clicked.connect(lambda _=False, pp=p: os.startfile(pp if os.path.isdir(pp) else os.path.dirname(pp)))
                self.path_grid.addWidget(b, r, 2)
            self.path_grid.setColumnStretch(1, 1)
            for k, v in old.items():
                if k in self.path_edits:
                    self.path_edits[k].setText(v)
        finally:
            if target is not None:
                target.setUpdatesEnabled(True)

    def _toggle_paths(self):
        """展开 / 收起「工具路径」。

        直接 setVisible 的毛病：布局要到下一轮事件循环才算完，滚动区会先按旧高度
        画一帧，于是下面那排按钮（打开工作目录 / 清理缓存 / 保存设置）先闪一下再
        归位。这里改成：先冻结重绘 → 当场把布局算完 → 再解冻重绘，全程只出一帧。
        另外收起时若焦点在路径输入框里，Qt 会顺手滚到新焦点让画面跳一下，先挪走焦点。
        """
        vis = not self.paths_panel.isVisible()
        panel = self.paths_panel
        card = panel.parentWidget()
        page = card.parentWidget() if card is not None else None
        scroll = None
        w = page
        while w is not None:
            if isinstance(w, QScrollArea):
                scroll = w
                break
            w = w.parentWidget()
        if not vis:
            fw = panel.focusWidget()
            if fw is not None and panel.isAncestorOf(fw):
                self.btn_paths.setFocus(Qt.OtherFocusReason)
        bar = scroll.verticalScrollBar() if scroll is not None else None
        pos = bar.value() if bar is not None else 0
        guard = [x for x in (page, card) if x is not None]
        if scroll is not None:
            guard.append(scroll.viewport())
            guard.append(scroll)
        for x in guard:
            x.setUpdatesEnabled(False)
        try:
            self.btn_paths.setText(_tl("工具路径（高级）") + ("  ▴" if vis else "  ▾"))
            panel.setVisible(vis)
            # page 的布局先把卡片高度改掉，卡片的布局再摆内部控件，顺序不能反
            for x in (page, card):
                if x is None:
                    continue
                lay = x.layout()
                if lay is not None:
                    lay.invalidate()
                    lay.activate()
            if bar is not None:
                bar.setValue(pos)
        finally:
            for x in guard:
                x.setUpdatesEnabled(True)
                x.update()

    def _choose_tool(self, key, kind):
        if kind == "dir":
            p = QFileDialog.getExistingDirectory(self, _tl("选择目录"))
        else:
            p, _ = QFileDialog.getOpenFileName(self, _tl("选择文件"), "",
                                               _tl("程序 (*.exe);;全部 (*.*)"))
        if p and key in self.path_edits:
            self.path_edits[key].setText(p)

    def _check_tools(self):
        self._apply_tool_paths(silent=True)
        self._rebuild_env()
        specs = self._tool_specs()
        ok = sum(1 for x in specs if x["ok"])
        msg = _tl("已配置 %d / %d 项工具。") % (ok, len(specs))
        need = [x["name"] for x in specs if not x["ok"] and not x.get("optional")]
        if need:
            msg += "\n\n" + _tl("缺少：") + "、".join(need)
        opt = [x["name"] for x in specs if not x["ok"] and x.get("optional")]
        if opt:
            msg += "\n" + _tl("可选未装：") + "、".join(opt)
        QMessageBox.information(self, _tl("检查完成"), msg)

    def _fill_system_fonts(self):
        """枚举系统已安装字体族，填充字体下拉框。"""
        fams = set()
        try:
            db = QFontDatabase()
            for fam in db.families():
                if fam and not fam.startswith("."):
                    fams.add(fam)
        except Exception:
            pass
        # 优先显示常用中文字体
        prefer = ["Microsoft YaHei UI", "微软雅黑", "Microsoft YaHei",
                  "SimHei", "黑体", "SimSun", "宋体", "DengXian", "等线",
                  "KaiTi", "楷体", "FangSong", "仿宋", "Consolas",
                  "Segoe UI", "Arial"]
        # 兜底：若系统枚举为空（如无字体环境的离屏平台），至少给一组常用项
        if not fams:
            fams = set(prefer)
        ordered = ["系统默认"]
        for p in prefer:
            if p in fams:
                ordered.append(p)
                fams.discard(p)
        ordered += sorted(fams)
        self.cb_font.blockSignals(True)
        self.cb_font.clear()
        self.cb_font.addItem(_tl("系统默认"), "系统默认")
        for _nm in ordered[1:]:
            self.cb_font.addItem(_nm, _nm)
        self.cb_font.setProperty("i18n_combo", True)
        self.cb_font.blockSignals(False)

    def _apply_theme(self, name=None):
        """应用主题配色，并同步刷新选中态与字体。"""
        if name is None:
            name = getattr(self, "theme", "浅色")
        if name not in THEMES:
            name = "浅色"
        self.theme = name
        # 切换主题时清除遗留的自定义强调色/文字色，让新主题默认配色完整生效；
        # 用户如需自定义，可切完主题后再单独「选择颜色」。
        if self.accent_color:
            self.accent_color = ""
            self.setting["accent_color"] = ""
        if self.text_color:
            self.text_color = ""
            self.setting["text_color"] = ""
        self._save_settings()
        if hasattr(self, "theme_buttons"):
            for tn, b in self.theme_buttons.items():
                b.setChecked(tn == name)
        self._refresh_stylesheet()
        self._update_color_swatches()
        self._sync_bg_mask()
        self._apply_titlebar_theme()

    def _apply_titlebar_theme(self):
        """让 Windows 原生标题栏跟随主题（深色主题用深色标题栏，消除白色标题栏）。"""
        if os.name != "nt" or getattr(self, "_boot", False):
            return                      # 启动阶段先不碰 winId()：会提前创建原生窗口，实测 +90ms
        try:
            import ctypes
            hwnd = int(self.winId())
            dark = 1 if self.theme == "深色" else 0
            # DWMWA_USE_IMMERSIVE_DARK_MODE = 20（Win10 1809+）；旧系统回退属性 19
            for attr in (20, 19):
                try:
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr, ctypes.byref(ctypes.c_int(dark)),
                        ctypes.sizeof(ctypes.c_int))
                    break
                except Exception:
                    continue
        except Exception:
            pass

    def _sync_bg_mask(self):
        """根据主题调整背景蒙版：深色主题暗化背景，浅色主题提亮背景，保证文字可读。"""
        if not hasattr(self, "bg"):
            return
        if self.theme == "深色":
            self.bg._mask = QColor(8, 10, 16)
            self.bg.set_base(QColor(17, 24, 39))
        elif self.theme == "紫色":
            # 紫色主题用淡紫蒙版与淡紫基底，保持浅色通透
            self.bg._mask = QColor(243, 240, 250)
            self.bg.set_base(QColor(243, 240, 250))
        else:
            self.bg._mask = QColor(255, 255, 255)
            self.bg.set_base(QColor(238, 242, 247))
        self.bg.update()

    def _refresh_stylesheet(self, scope="app"):
        """重设样式表。

        scope="app"    ：主题/字体/强调色这类全局变更，刷全应用（含弹窗）
        scope="window" ：通透度这类只影响主窗口的变更，只刷本窗口，省掉 3/4 的耗时
        """
        if getattr(self, "_boot", False):
            # 启动阶段：窗口还没显示，刷了也看不见；run() 已按最终主题铺过一遍，
            # 这里只记一笔，等 _finish_boot() 一次性核对
            return
        app = QApplication.instance()
        if app is None:
            return
        fam = self.font_family or "Microsoft YaHei UI"
        accent = getattr(self, "accent_color", "") or self.setting.get("accent_color", "")
        text_c = getattr(self, "text_color", "") or self.setting.get("text_color", "")
        glass = getattr(self, "glass", 0.0)
        qss = _make_qss(self.theme, fam, accent, text_c, glass)
        if scope == "window":
            self.setStyleSheet(qss)
        else:
            app.setFont(_app_font(fam))
            self.setStyleSheet("")          # 清掉窗口级覆盖，避免压住全局样式
            app.setStyleSheet(qss)
        # 动态刷新硬编码颜色的控件，使其跟随当前主题强调色
        self._refresh_accent_widgets()
        # 下拉弹层是独立 popup，主题刷新后需重新兜底其样式
        self._style_combo_popups()

    def _yield(self):
        """构建过程中让出一帧：过渡页粒子据此继续转（没有过渡页时就是空操作）。"""
        self._tick()

    def _finish_boot(self, apply_titlebar=True):
        """主窗口 show() 之后收尾：一次性核对样式表、补下拉弹层样式、修标题栏。"""
        if not getattr(self, "_boot", False):
            return
        self._boot = False
        qss = _make_qss(self.theme, self.font_family or "Microsoft YaHei UI",
                        getattr(self, "accent_color", "") or "",
                        getattr(self, "text_color", "") or "",
                        getattr(self, "glass", 0.0))
        # 常见情况：启动时已按最终主题铺过一遍，这里算出来一模一样 → 直接跳过，
        # 省掉那次全局重新 polish（约 0.2~0.3s，窗口刚出来就卡一下很明显）
        if qss != self._boot_qss:
            app = QApplication.instance()
            if app is not None:
                app.setFont(_app_font(self.font_family or "Microsoft YaHei UI"))
                self.setStyleSheet("")
                app.setStyleSheet(qss)
        try:
            self._refresh_accent_widgets()
            self._style_combo_popups()
            # 显卡探测此时必然已完成：启动时若因探测未出结果而先按「有 N 卡」
            # 放行，这里会纠正过来（无 N 卡的机器上把 TensorRT 置灰）
            self._refresh_trt_available()
            # 碰 winId() 会把原生窗口提前建出来（实测约 0.1s），有过渡页时留给
            # show() 之后的 singleShot 去做，别卡在过渡页还没散的这一下
            if apply_titlebar:
                self._apply_titlebar_theme()
        except Exception:
            pass
        # 剩余页面在主窗口出来之后一页页补进栈（详见 _flush_pending_pages）
        QTimer.singleShot(0, self._flush_pending_pages)
        if getattr(self, "_presets_pending", False):
            self._presets_pending = False
            QTimer.singleShot(0, self._refresh_presets)

    def _refresh_accent_widgets(self):
        """把拖放区图标等硬编码蓝色控件更新为当前主题强调色。"""
        accent = getattr(self, "accent_color", "") or ""
        if not accent:
            accent = THEMES.get(getattr(self, "theme", "浅色"), {}).get("accent", "#2563eb")
        if hasattr(self, "drop_ico"):
            self.drop_ico.setStyleSheet(_ico_css(accent))

    def _pick_accent_color(self):
        """选择界面强调色（主题色）。"""
        cur = getattr(self, "accent_color", "") or self.setting.get("accent_color", "")
        def_accent = THEMES.get(getattr(self, "theme", "浅色"), {}).get("accent", "#2563eb")
        c = QColorDialog.getColor(QColor(cur) if cur else QColor(def_accent), self,
                                  _tl("选择界面主题色"))
        if c.isValid():
            self.accent_color = c.name()
            self.setting["accent_color"] = c.name()
            self._update_color_swatches()
            self._refresh_stylesheet()
            self._save_settings()

    def _pick_text_color(self):
        """选择界面文字颜色。"""
        cur = getattr(self, "text_color", "") or self.setting.get("text_color", "")
        def_text = THEMES.get(getattr(self, "theme", "浅色"), {}).get("text_strong", "#1f2937")
        c = QColorDialog.getColor(QColor(cur) if cur else QColor(def_text), self,
                                  _tl("选择文字颜色"))
        if c.isValid():
            self.text_color = c.name()
            self.setting["text_color"] = c.name()
            self._update_color_swatches()
            self._refresh_stylesheet()
            self._save_settings()

    def _reset_colors(self):
        """清空自定义强调色与文字色，恢复主题默认。"""
        self.accent_color = ""
        self.text_color = ""
        self.setting["accent_color"] = ""
        self.setting["text_color"] = ""
        self._update_color_swatches()
        self._refresh_stylesheet()
        self._save_settings()

    def _update_color_swatches(self):
        """刷新颜色预览色块（跟随当前主题默认色，而非硬编码蓝色）。"""
        t = THEMES.get(getattr(self, "theme", "浅色"), THEMES["浅色"])
        accent_def = t.get("accent", "#2563eb")
        text_def = t.get("text_strong", "#1f2937")
        border = t.get("border2", "#cbd5e1")
        if hasattr(self, "sw_accent"):
            c = getattr(self, "accent_color", "") or ""
            self.sw_accent.setStyleSheet(
                "background:%s;border:2px solid %s;border-radius:8px;" % (c or accent_def, border))
        if hasattr(self, "sw_text"):
            c = getattr(self, "text_color", "") or ""
            self.sw_text.setStyleSheet(
                "background:%s;border:2px solid %s;border-radius:8px;" % (c or text_def, border))

    def _apply_font_choice(self):
        if not hasattr(self, "cb_font"):
            return
        # 「系统默认」这一项的显示文本会跟随语言，取值要走 itemData
        name = _cb_val(self.cb_font)
        fam = "Microsoft YaHei UI" if name in ("", "系统默认") else name
        self.font_family = fam
        self._refresh_stylesheet()

    # ------------------------------------------------------------ 多语言
    def _apply_language(self, idx=None):
        code = self.cb_lang.currentData() or "zh-CN"
        _i18n.set_lang(code)
        # Qt 自己绘制的弹窗（选色、消息框等）走官方语言包，需同步换装
        _i18n.install_qt_translator()
        self.setting["lang"] = code
        self._retranslate_ui()
        self._save_settings()

    def _retranslate_ui(self):
        """遍历界面所有控件，把文字从当前译文切换为目标语言译文。"""
        from PySide6.QtWidgets import QWidget as _QW
        # 遍历整棵 widget 树。从窗口自身开始找（而不是 centralWidget），
        # 这样标题栏、背景层这些挂在窗口上的控件也一并覆盖。
        all_w = [self] + self.findChildren(_QW)
        # 启动阶段还在排队入栈的页面（_pending_pages 里是 (name, page)）不是窗口后代，
        # 单独补进来，否则刚启动就切语言时那几页会保持旧语言
        for _item in getattr(self, "_pending_pages", None) or []:
            _p = _item[1] if isinstance(_item, tuple) else _item
            if _p is not None:
                all_w.append(_p)
                all_w.extend(_p.findChildren(_QW))
        # 去重保序
        seen = set()
        ordered = []
        for w in all_w:
            if id(w) not in seen:
                seen.add(id(w))
                ordered.append(w)
        for w in ordered:
            if isinstance(w, QLabel):
                _k = w.property("i18n_key")
                if _k:
                    # 长段落：按稳定标识重取译文，不受标点差异影响
                    w.setText(_i18n.kv(_k, w.property("i18n_src") or ""))
                elif w.property("i18n_build"):
                    # 带版本号的构建信息，插值后无法整串查表，按模板重组
                    w.setText(_tl("构建：%s") % BUILD)
                else:
                    w.setText(_i18n.translate(w.text()))
            elif isinstance(w, QPushButton):
                t = w.text()
                # 导航按钮形如「◆   超分补帧」，拆分图标与文字分别翻译
                if t and len(t) > 2 and not t[0].isalnum() and not t[0].isspace():
                    icon = t[0]
                    body = t[1:].strip()
                    w.setText(icon + "   " + _i18n.translate(body))
                else:
                    w.setText(_i18n.translate(t))
            elif isinstance(w, (QCheckBox, QRadioButton)):
                w.setText(_i18n.translate(w.text()))
            elif isinstance(w, QComboBox) and w.count() and w.property("i18n_combo"):
                # 选项文本按语言重刷；itemData 是中文原文，业务读取不受影响
                idx = w.currentIndex()
                w.blockSignals(True)
                for i in range(w.count()):
                    d = w.itemData(i)
                    if isinstance(d, str):
                        w.setItemText(i, _tl_combo_name(d))
                w.setCurrentIndex(idx)
                w.blockSignals(False)
            # 工具提示（悬停说明）也要跟着换语言。这里直接整串查表：
            # translate() 会先用反向索引把当前译文还原成中文原文再翻译，所以反复切换也是幂等的；
            # 表里没有的（路径、带数字的动态状态等）原样返回，不会破坏内容。
            _tip = w.toolTip()
            if _tip:
                w.setToolTip(_i18n.translate(_tip))
        # 下拉项文本变了不会触发信号，手动刷一次与选项联动的说明文字
        if hasattr(self, "btn_paths"):
            # 按钮文字带 ▾/▴ 箭头，整串查不到译文，按当前展开状态重新拼一次
            self.btn_paths.setText(_tl("工具路径（高级）")
                                   + ("  ▴" if self.paths_panel.isVisible() else "  ▾"))
        if hasattr(self, "cb_sr"):
            self._sync_sr_desc()
            self._sync_vfi_desc()
            self.lbl_q.setText(_tl("目标 Mbps" if _cb_val(self.cb_rate) == "目标码率"
                                   else "CRF / 质量"))
            self._refresh_mode_hint()
        # 运行环境项含「N 个模型」这类带数字的状态，直接按当前语言重建一遍
        if hasattr(self, "env_grid"):
            self._rebuild_env()
        self._refresh_env()

    def _apply_tool_paths(self, silent=False):
        if not self.path_edits:
            return
        ff = self.path_edits.get("ffmpeg")
        if ff and ff.text().strip() and os.path.isfile(ff.text().strip()):
            new_ff = ff.text().strip()
            if new_ff != self.ffmpeg:
                self.ffmpeg = new_ff
                try:
                    self.encoders = vd.available_encoders(self.ffmpeg, envprobe.vendors()) or self.encoders
                    cur = self.cb_enc.currentText()
                    self.cb_enc.blockSignals(True)
                    self.cb_enc.clear()
                    self.cb_enc.addItems(self.encoders)
                    if cur in self.encoders:
                        self.cb_enc.setCurrentText(cur)
                    self.cb_enc.blockSignals(False)
                except Exception:
                    pass
        if not silent:
            self._refresh_env()


    def _build_about_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(26, 22, 26, 22)
        v.addWidget(QLabel("关于", objectName="h1"))
        card = Card()
        # 拆成多段并用稳定标识取译文：整段带 \n 的长文本当 key 很容易匹配失败
        for _i, (_key, _line) in enumerate((
                ("about.intro.1", "CHEN-V · 补帧 + 超分"),
                ("about.intro.2",
                 "RIFE ncnn 补帧 + Real-CUGAN / Real-ESRGAN 超分，"
                 "支持视频 / 图片 / 批量队列 / 图片序列输出。"),
                ("about.intro.3",
                 "内置加速内核常驻运行，底层使用本地 ncnn / ONNX 模型。"))):
            if _i:
                card.v.addSpacing(6)
            card.v.addWidget(_i18n_label(_line, _key))
        card.v.addWidget(QLabel("%s · %s" % (APP_VERSION, BUILD), objectName="muted"))
        card.v.addSpacing(6)
        # 免费声明：单独一行，避免和上面三段简介混在一起
        try:
            import integrity as _itg
            _author = getattr(_itg, "AUTHOR", "辰师")
        except Exception:
            _author = "辰师"
        _free = _i18n_label(
            "该应用由%s独立开发，所有功能免费使用。你可以转载与分享本软件，"
            "但请勿将其收费出售。" % _author, "about.free.1", object_name="notice")
        card.v.addWidget(_free)
        v.addWidget(card)

        disc = Card()
        dt = QLabel("免责声明", objectName="h2")
        disc.v.addWidget(dt)
        for _i, _line in enumerate((
                "1. 本软件为本地视频处理工具，仅供个人学习、研究与合法用途，请勿用于任何违反法律法规的活动。",
                "2. 软件内置的超分与补帧模型均来自第三方开源项目，其著作权归原作者所有；"
                "本软件仅提供推理调用，不主张对模型权重的任何权利。",
                "3. 处理结果的质量取决于源素材，本软件不对输出内容的准确性、可用性或商业价值作任何明示或默示保证。",
                "4. 使用本软件处理他人作品时，请自行确认已获得相应授权，遵守相关版权与肖像权规定。",
                "5. 因使用本软件造成的任何直接或间接损失，开发者不承担相关责任。")):
            if _i:
                disc.v.addSpacing(6)
            disc.v.addWidget(_i18n_label(_line, "about.disclaimer.%d" % (_i + 1)))
        v.addWidget(disc)

        # 第三方软件声明：程序内所有模型与组件的许可类型
        v.addWidget(QLabel("第三方软件声明", objectName="h2"))
        lic_card = Card()
        licenses = [
            ("FFmpeg", "lic.ffmpeg",
             "采用 GNU LGPL 2.1 或更高版本许可；包含 GPL 组件的构建受 GPL 约束。"),
            ("Real-ESRGAN", "lic.esrgan",
             "版权归其作者所有（Xintao Wang 等），采用 BSD 3-Clause 许可。"),
            ("Real-CUGAN", "lic.cugan",
             "版权归 bilibili AI 实验室所有，采用 MIT 许可；"
             "本程序仅调用随软件提供的本地模型与组件，不对模型权重主张任何权利。"),
            ("RIFE", "lic.rife",
             "版权归旷视研究院所有，rife-ncnn-vulkan 采用 MIT 许可，模型源自 RIFE 项目。"),
            ("ncnn / Vulkan", "lic.ncnn",
             "版权归腾讯优图 nihui 等所有（Tencent/ncnn），采用 BSD 3-Clause 许可。"),
            ("vs-mlrt / vsncnn", "lic.vsmlrt",
             "版权归 Amusement Club 及其贡献者所有，采用 GNU GPL 3.0 许可。"
             "本程序将 vsncnn 作为内置内核在独立进程中运行，仅通过标准输入输出管道传递任务，"
             "主程序代码与其不构成链接关系。许可全文见 vrt/licenses/GPL-3.0.txt，"
             "源码：https://github.com/AmusementClub/vs-mlrt 。"),
            ("VapourSynth", "lic.vapoursynth",
             "版权归 Fredrik Mellbin 等所有，采用 GNU LGPL 2.1 许可，作为视频处理内核。"),
            ("onnxruntime-directml", "lic.onnxruntime",
             "版权归 Microsoft 所有，采用 MIT 许可，用于 ONNX 模型推理。"),
            ("NVIDIA TensorRT", "lic.tensorrt",
             "版权归 NVIDIA Corporation 所有，为闭源专有软件，"
             "受 NVIDIA Software License Agreement 约束；"
             "可随本软件以二进制形式免费分发，仅限在 NVIDIA GPU 上运行，"
             "不得单独分发、逆向工程或用于非 NVIDIA 硬件。"),
            ("PySide6 / Qt", "lic.qt",
             "版权归 The Qt Company 所有，采用 LGPL/GPL 许可，用于图形界面。"),
        ]
        for name, key, lic in licenses:
            row = QHBoxLayout()
            row.setSpacing(10)
            row.setAlignment(Qt.AlignTop)
            nm = QLabel(name, objectName="h2")
            nm.setFixedWidth(150)
            nm.setWordWrap(True)
            row.addWidget(nm)
            lt = _i18n_label(lic, key)
            row.addWidget(lt, 1)
            lic_card.v.addLayout(row)
        v.addWidget(lic_card)

        note = QLabel("完整许可文本随程序附带于 vrt/licenses/ 目录。"
                      "上述组件的著作权均归各自作者所有，本程序仅在其许可范围内使用。",
                      objectName="muted")
        note.setWordWrap(True)
        v.addWidget(note)
        v.addStretch(1)
        # 内容较长：放进滚动区，窗口变矮时不会挤成一团
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _build_thanks_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(26, 22, 26, 22)
        v.addWidget(QLabel("特别鸣谢", objectName="h1"))
        v.addWidget(QLabel("本项目使用了以下开源项目与模型（含少量专有组件），"
                           "谨向各位作者致以诚挚谢意。",
                           objectName="muted"))
        card = Card()
        thanks = [
            ("Real-CUGAN", "bilibili AI 实验室（bilibili/ailab）", "动漫超分模型"),
            ("Real-ESRGAN", "Xintao Wang 等（xinntao/Real-ESRGAN）", "通用超分模型"),
            ("RIFE", "旷视研究院（megvii-research/RIFE）", "视频补帧模型"),
            ("FFmpeg", "FFmpeg 团队", "音视频编解码"),
            ("ncnn / Vulkan", "腾讯优图 nihui 等（Tencent/ncnn）", "推理框架"),
            ("VapourSynth", "Fredrik Mellbin 等", "视频处理内核"),
            ("vs-mlrt", "AmusementClub（vs-mlrt）", "推理插件 · GPL-3.0"),
            ("NVIDIA TensorRT", "NVIDIA Corporation", "GPU 加速 · 专有许可"),
            ("PySide6 / Qt", "The Qt Company", "界面框架"),
            ("onnxruntime-directml", "Microsoft", "ONNX 推理运行时"),
        ]
        for name, author, desc in thanks:
            row = QHBoxLayout()
            row.setSpacing(10)
            nm = QLabel(name, objectName="h2")
            nm.setFixedWidth(180)                       # 容纳 onnxruntime-directml 这类长名
            row.addWidget(nm)
            au = QLabel(_tl(author), objectName="hint")
            row.addWidget(au, 1)
            ds = QLabel(_tl(desc), objectName="muted")
            row.addWidget(ds)
            card.v.addLayout(row)
        v.addWidget(card)

        v.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    # ------------------------------------------------------------ 环境 / 表格
    def _preflight(self):
        # 原为「开始前检查」确认框（高分辨率/图片序列/高帧率/显存不足时弹出确认）。
        # 按用户要求取消该弹窗，点「开始队列」直接开始处理。
        return True

    def _refresh_env(self):
        if not self.ffmpeg:
            self.lbl_env.setText("环境：缺少 ffmpeg.exe")
        else:
            mem = _gpu_mem()
            memtxt = ("  ·  显存 %d/%d MB" % mem) if mem else ""
            self.lbl_env.setText("环境：已就绪  ·  AI：%s  ·  编码：%s  ·  内核：%s%s" % (
                self.gpu, self.cb_enc.currentText(), self.cb_kernel.currentText(), memtxt))
        self.lbl_env2.setText("%s  ·  %s" % (APP_NAME, APP_VERSION))

    def _refresh_table(self):
        if not hasattr(self, "table"):
            return
        # 批量重建期间暂停重绘，避免每插一行都触发一次全表重绘造成卡顿
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(0)
            self.item_bars = {}
            for i, it in enumerate(self.items):
                self.table.insertRow(i)
                name = os.path.basename(it["path"])
                self.table.setItem(i, 0, QTableWidgetItem(name))
                self.table.item(i, 0).setToolTip(it["path"])
                mode = self._eff_mode(it)
                self.table.setItem(i, 1, QTableWidgetItem(mode))
                self.table.setItem(i, 2, QTableWidgetItem(self._model_text(mode)))
                st = QTableWidgetItem(it.get("status", "等待"))
                st.setForeground(self._status_color(it.get("status", "等待")))
                self.table.setItem(i, 3, st)
                bar = QProgressBar()
                bar.setRange(0, 100)
                bar.setValue(int(it.get("progress", 0)))
                bar.setFixedHeight(12)
                bar.setTextVisible(False)
                self.table.setCellWidget(i, 4, bar)
                self.item_bars[i] = bar
        finally:
            self.table.setUpdatesEnabled(True)
        has = bool(self.items)
        self.table.setVisible(has)
        self.lbl_empty.setVisible(not has)
        self.lbl_queue_sub.setText(_tl("等待加入素材") if not has
                                   else _tl("共 %d 个素材") % len(self.items))
        self.lbl_input.setText(_tl("尚未选择") if not has
                               else _tl("已选择 %d 个素材") % len(self.items))
        if hasattr(self, "lbl_mode_hint"):
            self._refresh_mode_hint()

    def _status_color(self, s):
        # "处理中"跟随当前主题强调色（accent），其余用语义色
        accent = getattr(self, "accent_color", "") or ""
        if not accent:
            accent = THEMES.get(getattr(self, "theme", "浅色"), {}).get("accent", "#2563eb")
        return QColor({"完成": "#16a34a", "失败": "#dc2626",
                       "处理中": accent, "取消": "#b45309"}.get(s, "#64748b"))

    def _model_text(self, mode):
        if mode == MODE_IMAGE or mode == MODE_SR:
            return _short(self.cb_sr.currentText().replace("（ncnn）", ""), 34)
        if mode == MODE_VFI:
            return self.cb_vfi.currentText()
        return "%s · %s" % (_short(self.cb_sr.currentText().replace("（onnx）", "").replace("（ncnn）", ""), 24),
                            self.cb_vfi.currentText())

    def _eff_mode(self, item):
        if item.get("kind") == "image":
            return MODE_IMAGE
        if self.mode == MODE_IMAGE:
            return MODE_SR
        return self.mode

    @property
    def mode(self):
        for text, b in self.mode_buttons.items():
            if b.isChecked():
                return text
        return MODE_BOTH

    def _on_mode_changed(self, text):
        if self.mode == MODE_IMAGE:
            if _cb_val(self.cb_fmt) not in ("PNG 序列", "JPG 序列", "WEBP 序列"):
                self.cb_fmt.setCurrentIndex(self.cb_fmt.findData("PNG 序列"))
        self._sync_mode()
        self._refresh_table()

    def _sync_mode(self):
        m = self.mode
        if m == MODE_IMAGE and _cb_val(self.cb_fmt) not in ("PNG 序列", "JPG 序列", "WEBP 序列"):
            i = self.cb_fmt.findData("PNG 序列")
            if i >= 0:
                self.cb_fmt.setCurrentIndex(i)
        vfi = m in (MODE_VFI, MODE_BOTH)
        sr = m in (MODE_IMAGE, MODE_SR, MODE_BOTH)
        for w in (self.cb_vfi, self.rb_mult, self.rb_fps):
            w.setEnabled(vfi)
        self.cb_sr.setEnabled(sr)
        self.cb_dev.setEnabled(sr)
        self.cb_tile.setEnabled(sr)
        self.cb_kernel.setEnabled(False)
        self._sync_fps()
        # 处理顺序开关：勾选=先超分再补帧（更快），取消=先补帧再超分
        self.chk_two.setEnabled(True)
        self._refresh_trt_available()
        self.chk_keep.setEnabled(m == MODE_BOTH)
        self.cb_enc.setEnabled(m != MODE_IMAGE)
        self.cb_rate.setEnabled(m != MODE_IMAGE)
        self.sp_q.setEnabled(m != MODE_IMAGE)
        self.chk_scene.setEnabled(vfi)
        self.chk_dedup.setEnabled(vfi)
        self.sp_dup.setEnabled(vfi and self.chk_dedup.isChecked())
        self._sync_fps()
        self._refresh_mode_hint()

    def _refresh_trt_available(self):
        """TensorRT 复选框该不该可勾。

        三件事同时成立才行：本模式会做超分、当前超分模型是 ONNX（TensorRT 只吃
        ONNX，带「ncnn 内核」字样的都是 .param）、本机确实有 NVIDIA 显卡且
        vstrt.dll + TensorRT 运行库齐全。不满足就置灰，并把原因写进 tooltip——
        打包发给别人时，对方才不会出现「勾得上、跑起来却回退 ncnn」的假可用。
        """
        if not hasattr(self, "chk_trt"):
            return
        sr_on = self.cb_sr.isEnabled()
        # 用 _cb_val 而不是 currentText：切过语言后下拉里显示的是译文，
        # 只有 itemData 里还留着原始中文名，否则这里会误判成「不是 ONNX」
        spec = (self.sr_map.get(_cb_val(self.cb_sr))
                if getattr(self, "sr_map", None) else None)
        is_onnx = bool(spec and spec[0] == "onnx")
        trt_ok, reason = kernel_backend.trt_status()

        if sr_on and is_onnx and trt_ok:
            self.chk_trt.setEnabled(True)
            self.chk_trt.setToolTip(_tl(self._trt_tip))
            return

        self.chk_trt.setEnabled(False)
        if not sr_on:
            why = "当前模式不做超分，TensorRT 用不上"
        elif not is_onnx:
            why = ("当前超分模型不是 ONNX 格式，TensorRT 只支持 ONNX；\n"
                   "带「ncnn 内核」字样的模型不走 TensorRT，直接用 ncnn 内核即可")
        elif reason == "no_nvidia":
            why = ("未检测到 NVIDIA 显卡，TensorRT 用不了（处理时会自动回退 ncnn 内核，\n"
                   "画质一样，只是慢一些）")
        elif reason == "no_resource":
            why = ("缺少当前显卡架构的 TensorRT 构建资源（nvinfer_builder_resource_smXX_10.dll）；\n"
                   "从 TensorRT 10.16 官方包的 bin 目录拷贝对应架构那份进来即可，\n"
                   "暂不补也能用，勾选后会回退 ncnn 内核")
        else:
            why = ("缺少 TensorRT 运行库：vrt/plugins 内需要 vstrt.dll，\n"
                   "以及 vsmlrt-cuda 里的 TensorRT DLL（含 trtexec.exe）")
        self.chk_trt.setToolTip(_tl(why))

    def _sync_fps(self):
        if not hasattr(self, "sp_fps"):
            return
        vfi = self.mode in (MODE_VFI, MODE_BOTH)
        by_fps = self.rb_fps.isChecked()
        self.cb_fps_mode.setEnabled(vfi and not by_fps)
        self.sp_fps.setEnabled(vfi and by_fps)
        if hasattr(self, "lbl_mode_hint"):
            self._refresh_mode_hint()

    def _sync_vfi_desc(self):
        """根据当前选中的补帧模型，更新用途说明文字。"""
        if not hasattr(self, "lbl_vfi_desc"):
            return
        name = _cb_val(self.cb_vfi)
        self.lbl_vfi_desc.setText(_tl(self.rife_desc.get(name, "")))

    def _sync_sr_desc(self):
        """根据当前选中的超分模型，更新用途说明文字。"""
        if not hasattr(self, "lbl_sr_desc"):
            return
        name = _cb_val(self.cb_sr)
        self.lbl_sr_desc.setText(_tl(self.sr_desc.get(name, "")))
        # 换模型可能把「ONNX → ncnn 内核」，TensorRT 是否可勾要跟着变
        self._refresh_trt_available()

    def _fps_desc(self):
        if getattr(self, "rb_fps", None) is not None and self.rb_fps.isChecked():
            return "%d fps" % self.sp_fps.value()
        return self.cb_fps_mode.currentText()

    def _refresh_mode_hint(self):
        if not hasattr(self, "cb_kernel") or not hasattr(self, "lbl_mode_hint"):
            return
        m = self.mode
        text = {
            MODE_IMAGE: _tl("图片超分：按超分模型倍率放大，输出 PNG / JPG / WEBP。"),
            MODE_SR: _tl("视频超分：按源帧率输出，只做超分。"),
            MODE_VFI: _tl("视频补帧：只补帧，输出到目标帧率。"),
            MODE_BOTH: _tl("逐段完成超分与补帧，兼顾清晰度、流畅度和临时空间。"),
        }.get(m, "")
        sr = self.cb_sr.currentText()
        vfi = self.cb_vfi.currentText()
        tail = _tl("超分：%s") % _short(sr, 28) if m in (MODE_IMAGE, MODE_SR, MODE_BOTH) else ""
        if m in (MODE_VFI, MODE_BOTH):
            tail += ("  ·  " if tail else "") + _tl("补帧：%s（%s）") % (vfi, self._fps_desc())
        if (m in (MODE_VFI, MODE_BOTH)
                and self.chk_dedup.isChecked()):
            tail += "  ·  " + _tl("帧流法：内置内核原生（改参数不重启）")
        self.lbl_mode_hint.setText(text + ("    " + tail if tail else ""))

    # ------------------------------------------------------------ 输入
    def _pick_files(self):
        fs, _ = QFileDialog.getOpenFileNames(
            self, _tl("选择素材"), "",
            _tl("素材 (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.ts *.png *.jpg *.jpeg *.webp *.bmp);;全部 (*.*)"))
        if fs:
            self._add_paths(fs)

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, _tl("选择文件夹"))
        if d:
            self._add_paths([d])

    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, _tl("选择输出目录"))
        if d:
            self.out_edit.setText(d)

    def _pick_set_out(self):
        d = QFileDialog.getExistingDirectory(self, _tl("选择默认输出目录"))
        if d:
            self.set_out.setText(d)
            self.out_edit.setText(d)

    def _pick_conv_out(self):
        d = QFileDialog.getExistingDirectory(self, _tl("选择输出目录"))
        if d:
            self.conv_out.setText(d)

    def _add_paths(self, paths_in, append=True):
        if self.running:
            QMessageBox.information(self, _tl("提示"), _tl("任务正在跑，等结束再加素材"))
            return
        found = []
        for p in paths_in:
            p = p.strip().strip('"')
            if os.path.isdir(p):
                for base, _dirs, files in os.walk(p):
                    for f in sorted(files):
                        if f.lower().endswith(VIDEO_EXT + IMAGE_EXT):
                            found.append(os.path.join(base, f))
            elif os.path.isfile(p):
                found.append(p)
        have = {os.path.normcase(os.path.abspath(it["path"])) for it in self.items}
        for p in found:
            key = os.path.normcase(os.path.abspath(p))
            if key in have:
                continue
            ext = os.path.splitext(p)[1].lower()
            kind = "image" if ext in IMAGE_EXT else "video"
            self.items.append({"path": p, "kind": kind, "status": "等待", "progress": 0})
            have.add(key)
        self._refresh_table()

    def _remove_selected(self):
        if self.running:
            return
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self.items):
                self.items.pop(r)
        self._refresh_table()

    def _clear_queue(self):
        if self.running:
            return
        self.items = []
        self._refresh_table()

    def _table_menu(self, pos):
        if self.running:
            return
        idx = self.table.indexAt(pos)
        if not idx.isValid():
            return
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        a = m.addAction("移除")
        b = m.addAction("打开所在文件夹")
        act = m.exec(self.table.viewport().mapToGlobal(pos))
        if act == a:
            self.items.pop(idx.row())
            self._refresh_table()
        elif act == b:
            p = self.items[idx.row()]["path"]
            d = p if os.path.isdir(p) else os.path.dirname(p)
            if os.path.isdir(d):
                os.startfile(d)

    # ------------------------------------------------------------ 队列运行
    def _snapshot(self):
        fmt = FMT_KEYS.get(_cb_val(self.cb_fmt), "MP4")
        by_fps = self.rb_fps.isChecked()
        fps_mode = "自定义" if by_fps else self.cb_fps_mode.currentText()
        mult = 1
        fps = 0.0
        if by_fps:
            fps = float(self.sp_fps.value())
        else:
            try:
                mult = int(self.cb_fps_mode.currentText()[0])
            except Exception:
                mult = 2
        rate = "bitrate" if _cb_val(self.cb_rate) == "目标码率" else "crf"
        q = int(self.sp_q.value())
        return {
            "mode": self.mode,
            "out_dir": self.out_edit.text().strip(),
            "suffix": self.name_edit.text().strip(),
            "sr": _cb_val(self.cb_sr),
            "vfi": _cb_val(self.cb_vfi),
            "kernel": _cb_val(self.cb_kernel),
            "fps_mode": fps_mode,
            "mult": mult, "fps": fps,
            "encoder": self.cb_enc.currentText(),
            "rate": _cb_val(self.cb_rate),
            "rate_mode": rate,
            "crf": q if rate == "crf" else 16,
            "bitrate": float(q if rate == "bitrate" else 20),
            "preset": "balanced",
            "out_res": _cb_val(self.cb_res),
            "out_fmt": _cb_val(self.cb_fmt),
            "out_format": fmt,
            "device": "dml" if self.cb_dev.currentText() == "GPU" else "cpu",
            "tile": 0 if _cb_val(self.cb_tile) == "自动" else int(_cb_val(self.cb_tile)),
            "dev": self.cb_dev.currentText(),
            "tile_label": _cb_val(self.cb_tile),
            "two_pass": False,
            "sr_first": bool(self.chk_two.isChecked()),
            "sr_workres": bool(self.chk_workres.isChecked()),
            "use_trt": bool(self.chk_trt.isChecked()),
            "keep": self.chk_keep.isChecked(),
            "dedup": self.chk_dedup.isChecked(),
            "dup_thr": float(self.sp_dup.value()),
            "scene": self.chk_scene.isChecked(),
            "hwdec": self.chk_hw.isChecked(),
            "turbo": self.chk_turbo.isChecked(),
            "sr_fp16": 1 if self.chk_turbo.isChecked() else 0,
            "start": 0.0, "duration": 0.0,
        }

    # ------------------------------------------------------------ 参数预设
    def _preset_path(self, name):
        safe = re.sub(r'[\\/:*?"<>|]+', "_", str(name)).strip(" .") or "预设"
        return os.path.join(PRESETS_DIR, safe + ".json")

    def _refresh_presets(self):
        """刷新预设下拉框（保留「默认」占位项）。"""
        if not hasattr(self, "cb_preset"):
            return
        names = []
        try:
            if os.path.isdir(PRESETS_DIR):
                for f in os.listdir(PRESETS_DIR):
                    if f.endswith(".json"):
                        names.append(f[:-5])
        except Exception:
            pass
        cur = self.cb_preset.currentText()
        self.cb_preset.blockSignals(True)
        self.cb_preset.clear()
        self.cb_preset.addItem(_tl("（无预设）"), "（无预设）")
        for _nm in sorted(names):
            self.cb_preset.addItem(_nm, _nm)
        self.cb_preset.setProperty("i18n_combo", True)
        if cur and cur != _tl("（无预设）"):
            i = self.cb_preset.findData(cur)
            if i >= 0:
                self.cb_preset.setCurrentIndex(i)
        self.cb_preset.blockSignals(False)

    def _save_preset(self):
        name, ok = QInputDialog.getText(self, _tl("保存预设"), _tl("预设名称："))
        if not ok or not name.strip():
            return
        data = self._snapshot()
        try:
            os.makedirs(PRESETS_DIR, exist_ok=True)
            with open(self._preset_path(name.strip()), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._refresh_presets()
            i = self.cb_preset.findText(name.strip())
            if i >= 0:
                self.cb_preset.setCurrentIndex(i)
            QMessageBox.information(self, _tl("预设"), _tl("已保存预设「%s」") % name.strip())
        except Exception as e:
            QMessageBox.warning(self, _tl("预设"), _tl("保存失败：%s") % e)

    def _delete_preset(self):
        name = self.cb_preset.currentText()
        if name in ("", "（无预设）"):
            return
        try:
            p = self._preset_path(name)
            if os.path.isfile(p):
                os.remove(p)
            self._refresh_presets()
        except Exception as e:
            QMessageBox.warning(self, _tl("预设"), _tl("删除失败：%s") % e)

    def _load_preset(self, name):
        if name in ("", "（无预设）"):
            return
        p = self._preset_path(name)
        if not os.path.isfile(p):
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                s = json.load(f)
        except Exception:
            return
        # 回填各控件（复用 _restore 的字段映射逻辑）
        if s.get("mode") in self.mode_buttons:
            self.mode_buttons[s["mode"]].setChecked(True)
        for cb, key in ((self.cb_sr, "sr"), (self.cb_vfi, "vfi"),
                        (self.cb_enc, "encoder"), (self.cb_res, "out_res"),
                        (self.cb_fmt, "out_fmt"), (self.cb_rate, "rate"),
                        (self.cb_dev, "dev"), (self.cb_tile, "tile_label")):
            val = s.get(key)
            if val:
                _combo_select(cb, val)
        if s.get("fps"):
            try:
                self.sp_fps.setValue(int(float(s["fps"])))
            except Exception:
                pass
        fm = s.get("fps_mode")
        if fm == "自定义" or (not fm and s.get("fps")):
            self.rb_fps.setChecked(True)
        else:
            if fm:
                i = self.cb_fps_mode.findText(fm)
                if i >= 0:
                    self.cb_fps_mode.setCurrentIndex(i)
            self.rb_mult.setChecked(True)
        if s.get("rate_mode") == "bitrate" and s.get("bitrate"):
            try:
                self.sp_q.setValue(int(float(s["bitrate"])))
            except Exception:
                pass
        elif s.get("crf") is not None:
            try:
                self.sp_q.setValue(int(float(s["crf"])))
            except Exception:
                pass
        for w, key in ((self.chk_keep, "keep"), (self.chk_dedup, "dedup"),
                       (self.chk_scene, "scene"), (self.chk_hw, "hwdec"),
                       (self.chk_turbo, "turbo"), (self.chk_workres, "sr_workres"),
                       (self.chk_trt, "use_trt")):
            if key in s:
                w.setChecked(bool(s[key]))
        if s.get("dup_thr") is not None:
            try:
                self.sp_dup.setValue(float(s["dup_thr"]))
            except Exception:
                pass
        self._sync_mode()

    def _start_queue(self):
        if self.running:
            return
        if not self.items:
            QMessageBox.information(self, _tl("提示"), _tl("先拖入或选择素材"))
            return
        if not self.ffmpeg:
            QMessageBox.critical(self, _tl("缺少 ffmpeg"), _tl("找不到 ffmpeg.exe"))
            return
        if not self._preflight():
            return
        self.cfg = self._snapshot()
        self.stop_event.clear()
        self.running = True
        self.cur_item = -1
        self.log.clear()
        for it in self.items:
            it["mode"] = self._eff_mode(it)
            if it.get("status") in ("完成", "失败", "取消"):
                it["status"] = "等待"
                it["progress"] = 0
        self._refresh_table()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        for b in self.mode_buttons.values():
            b.setEnabled(False)
        self.settings_panel.setEnabled(False)
        self.pb_main.setValue(0)
        self.lbl_cur.setText("准备中…")
        self._show_page("进度")
        threading.Thread(target=self._run_queue, daemon=True).start()

    def _stop_queue(self):
        self.stop_event.set()
        self.lbl_cur.setText("正在停止…")

    def _run_queue(self):
        try:
            pending = [i for i, it in enumerate(self.items) if it.get("status", "等待") == "等待"]
            for idx in pending:
                if self.stop_event.is_set():
                    break
                it = self.items[idx]
                mode = it.get("mode") or self._eff_mode(it)
                self.msg.put(("current", idx, os.path.basename(it["path"]), len(pending)))
                self.msg.put(("item", idx, "处理中"))
                try:
                    if mode == MODE_IMAGE:
                        self._do_image(idx, it, mode)
                    else:
                        self._do_video(idx, it, mode)
                    self.msg.put(("item", idx, "完成"))
                    self.msg.put(("prog", idx, 100, 100))
                except jobmod.Cancelled:
                    self.msg.put(("item", idx, "取消"))
                    break
                except Exception as e:
                    self.msg.put(("log", "失败：%s\n%s" % (e, traceback.format_exc())))
                    self.msg.put(("item", idx, "失败"))
        finally:
            self.msg.put(("done", 0))

    def _do_video(self, idx, it, mode):
        c = self.cfg
        if not kernel_backend.available():
            raise RuntimeError("内置加速内核不可用：缺少 vrt 运行时或插件（librife.dll / lsmashsource.dll / slv_ncnn_models.dll / vsncnn.dll）")
        if c.get("dedup") and mode in (MODE_VFI, MODE_BOTH):
            self.msg.put(("log", "内置加速内核：帧流法在 worker 内完成；修改参数只重算帧，不启动独立进程"))
        # 超分模型解析
        sr_spec = None
        if mode in (MODE_SR, MODE_BOTH):
            sr_val = self.sr_map.get(c["sr"])
            if not sr_val:
                raise RuntimeError("没有可用的超分模型")
            sr_spec = kernel_backend.sr_param(sr_val[1])
            if not sr_spec:
                raise RuntimeError("超分模型参数解析失败：%s" % c["sr"])
            # TensorRT 只能跑 ONNX 模型；勾选且环境可用时，让 worker 走 trt 分支
            if c.get("use_trt") and sr_spec.get("kind") == "onnx" and kernel_backend.has_trt():
                sr_spec["use_trt"] = True
        # 勾了「保留补帧中间片」：超分+补帧要拆成两段跑，第 1 段落盘中间片才有东西可留。
        # 一次跑完的内核流水线（单段）内存里就把补帧和超分串起来了，不产生中间文件。
        if mode == MODE_BOTH and c.get("keep") and sr_spec:
            return self._do_video_two_pass(idx, it, c, sr_spec)
        return self._do_video_vs(idx, it, mode, c, sr_spec)

    def _do_video_two_pass(self, idx, it, c, sr_spec):
        """超分 + 补帧拆两段：第 1 段写中间片（MKV），第 2 段读中间片继续做完。

        代价是多一次编码 + 一次解码（约慢 1 倍），换来中间片可留可复用。
        两段的先后顺序跟着「先超分 → 再补帧」开关走，保证和单段跑出来的画面一致。
        """
        path = it["path"]
        src_stem = os.path.splitext(os.path.basename(path))[0]
        out_dir = c["out_dir"] or os.path.dirname(path)
        os.makedirs(out_dir, exist_ok=True)
        sr_first = bool(c.get("sr_first", 1))
        mid_dir = _unique(os.path.join(
            out_dir, "%s_%s中间片" % (src_stem, "超分" if sr_first else "补帧")))
        os.makedirs(mid_dir, exist_ok=True)

        def _mid_cfg(**kw):
            x = dict(c)
            x.update({"out_dir": mid_dir, "out_format": "MKV", "suffix": "中间片"})
            x.update(kw)
            return x

        if sr_first:
            # 第 1 段只超分：中间片已经是目标尺寸，第 2 段补帧时不再缩放
            c1 = _mid_cfg(start=c["start"], duration=c["duration"])
            c2 = dict(c)
            c2.update({"start": 0.0, "duration": 0.0, "out_res": "源分辨率"})
            m1, m2, sr1 = MODE_SR, MODE_VFI, sr_spec
            label1, label2 = "超分（补帧关闭）", "补帧（超分关闭）"
        else:
            # 第 1 段只补帧：中间片保持源分辨率，第 2 段超分时再按目标尺寸放大/缩放
            c1 = _mid_cfg(start=c["start"], duration=c["duration"], out_res="源分辨率")
            c2 = dict(c)
            c2.update({"start": 0.0, "duration": 0.0})
            m1, m2, sr1 = MODE_VFI, MODE_SR, None
            label1, label2 = "补帧（超分关闭）", "超分（补帧关闭）"
        c1["fps"] = c1["fps"] if m1 == MODE_VFI else 0.0
        c2["fps"] = c2["fps"] if m2 == MODE_VFI else 0.0

        self.msg.put(("log", "=" * 56))
        self.msg.put(("log", "第 1 段／%s：%s（中间片目录 %s）" % (
            label1, os.path.basename(path), mid_dir)))
        mid = self._do_video_vs(idx, it, m1, c1, sr1, span=(0.0, 0.5))
        if not mid or not os.path.isfile(mid):
            raise RuntimeError("第 1 段没有产出中间片：%s" % (mid or mid_dir))
        self.msg.put(("log", "中间片：%s" % mid))

        self.msg.put(("log", "-" * 56))
        self.msg.put(("log", "第 2 段／%s：%s" % (label2, os.path.basename(mid))))
        out = self._do_video_vs(idx, dict(it, path=mid), m2, c2,
                                sr_spec if m2 == MODE_SR else None,
                                span=(0.5, 1.0), out_stem=src_stem)
        self.msg.put(("log", "%s中间片保留在：%s" % (
            "超分" if sr_first else "补帧", mid_dir)))
        return out

    def _do_video_vs(self, idx, it, mode, c, sr_spec, span=(0.0, 1.0), out_stem=None):
        path = it["path"]
        info = vd.probe(self.ffmpeg, path)
        w, h = info["width"], info["height"]
        fps_in = info["fps"] or 24.0
        has_vfi = mode in (MODE_VFI, MODE_BOTH)
        has_sr = mode in (MODE_SR, MODE_BOTH)
        fps_out = (c["fps"] if c["fps"] > 0 else fps_in * c["mult"]) if has_vfi else fps_in
        target = _target_size(w, h, c["out_res"])
        fmt = c["out_format"]
        is_img = fmt in ("PNG", "JPG", "WEBP_IMG")
        out_dir = c["out_dir"] or os.path.dirname(path)
        os.makedirs(out_dir, exist_ok=True)
        tag = []
        if has_vfi:
            tag += ["%.2ffps" % fps_out, "rife"]
        if has_sr:
            tag.append("SR")
        # 两段式时第 2 段的输入是中间片，但片名要沿用原始视频（不然会出「xx_中间片_后缀.mp4」）
        stem = out_stem or os.path.splitext(os.path.basename(path))[0]
        name = c["suffix"] or "_".join(tag) or "out"
        base = "%s_%s" % (stem, name)
        if is_img:
            folder = _unique(os.path.join(out_dir, base))
            os.makedirs(folder, exist_ok=True)
            ext = {"PNG": ".png", "JPG": ".jpg", "WEBP": ".webp"}.get(fmt, ".png")
            output = os.path.join(folder, "frame_%08d" + ext)
        else:
            ext = vd.VIDEO_FORMATS.get(fmt, ".mp4")
            output = _unique(os.path.join(out_dir, base + ext))
        enc = c["encoder"]
        pix = vd.ENCODERS.get(enc, vd.ENCODERS["H265 NVENC"])[1]
        out_pix = "yuv420p10le" if "10" in pix else "yuv420p"
        # GIF / WEBP 动图输出：走专用编码器，忽略常规编码器选择
        if fmt == "GIF":
            codec_name = "gif"
            cargs = []
            out_pix = "yuv420p"
        elif fmt == "WEBP":
            codec_name = "libwebp"
            cargs = ["-quality", "95", "-lossless", "0"]
            out_pix = "yuv420p"
        else:
            codec_name = vd.ENCODERS.get(enc, vd.ENCODERS["H265 NVENC"])[0]
            cargs = kernel_backend.codec_args(enc, c["rate_mode"], c["crf"], c["bitrate"],
                                              c["preset"], c["turbo"], out_pix, is_img, fmt)
        vfi = None
        if has_vfi:
            ri = self.rife_map.get(c["vfi"])
            if not ri:
                raise RuntimeError("没有可用的 RIFE 模型")
            vfi = {"model": ri["model"], "gpu": 0,
                   "factor_num": int(c["mult"]), "factor_den": 1,
                   "scene": 1 if c["scene"] else 0,
                   "dedup": 1 if c["dedup"] else 0,
                   "dup_thr": float(c.get("dup_thr", 0.25))}
            if c["dedup"] or c["fps"] > 0:
                from fractions import Fraction
                fr = Fraction(str(round(float(fps_out), 6))).limit_denominator(100000)
                vfi.update({"fps_num": fr.numerator, "fps_den": fr.denominator})
        sr = None
        if has_sr and sr_spec:
            sr = dict(sr_spec)
            # fp16 推理开关：默认关闭（fp32 精确推理）；勾选「涡轮增速」时用 fp16 提速 2~3 倍
            sr.update({"tile": c["tile"] or 160, "gpu": 0,
                       "fp16": int(c.get("sr_fp16", 0))})
        # 工作分辨率：先缩到「目标尺寸 ÷ 超分倍数」再超分，由超分自己放大到目标尺寸。
        # 避免「先放大 k 倍再缩回目标」把算力浪费在最终会被缩掉的像素上（实测超分环节快约 3 倍）。
        pre_w = pre_h = 0
        if has_sr and sr and c.get("sr_workres") and target:
            _k = max(1, int(sr.get("scale", 2)))
            _pw, _ph = int(target[0]) // _k, int(target[1]) // _k
            if 0 < _pw < w and 0 < _ph < h:
                pre_w, pre_h = _pw - _pw % 2, _ph - _ph % 2
        tmp = tempfile.mkdtemp(prefix="kernel_job_", dir=paths.temp_root())
        cancel = os.path.join(paths.TEMP_DIR, "kernel_cancel_%d_%d.flag" % (idx, int(time.time())))
        spec = {
            "input": path, "output": output, "image_seq": is_img,
            "ffmpeg": self.ffmpeg, "tmp": tmp,
            "start": c["start"], "duration": c["duration"],
            "out_pix": out_pix, "codec": codec_name,
            "codec_args": cargs, "audio": not is_img, "cancel": cancel,
            "vfi": vfi, "sr": sr,
            "sr_first": bool(c.get("sr_first", 1)),
            "pre_w": pre_w, "pre_h": pre_h,
            "target_w": target[0] if target else 0,
            "target_h": target[1] if target else 0,
        }
        self.msg.put(("log", "内置内核：%s（%s）" % (
            os.path.basename(path),
            " + ".join((["RIFE"] if has_vfi else []) + (["SR"] if has_sr else [])) or "转码")))
        if is_img:
            self.msg.put(("log", "提示：图片序列要逐帧写图，比 MP4 慢很多；长片建议输出 MP4"))
        if has_sr and sr:
            k = int(sr.get("scale", 2))
            sw = w * k
            sh = h * k
            if not target:
                # 输出分辨率=源：超分后直接放大 k 倍输出，不缩回
                self.msg.put(("log", "超分 %d×：%d×%d -> %d×%d（输出分辨率=源，超分后放大输出）" % (
                    k, w, h, sw, sh)))
            elif target[1] < sh or target[0] < sw:
                self.msg.put(("log", "超分 %d× 后 Lanczos 缩回目标 %d×%d（保持清晰度）" % (
                    k, target[0], target[1])))
        last = [0]
        t_start = time.time()

        def on_prog(cur, total, fps):
            # 两段式时把本段进度压缩到它占的区间（第 1 段 0~50%、第 2 段 50~100%），
            # 否则进度条会在第 1 段结束时冲到 100% 又被打回 0
            if span != (0.0, 1.0):
                t_all = total or 1
                self.msg.put(("prog", idx, span[0] * t_all + (span[1] - span[0]) * cur, t_all))
            else:
                self.msg.put(("prog", idx, cur, total))
            step = max(1, (total or 1) // 20)
            if cur == 1 or cur == total or cur - last[0] >= step:
                last[0] = cur
                sp = fps if fps and fps > 0.01 else cur / max(time.time() - t_start, 1e-6)
                eta = (total - cur) / sp if sp > 0.01 else 0
                self.msg.put(("log", "  VS %d/%d（%.1f%%）  %.2f 帧/秒  剩余 %s" % (
                    cur, total, 100.0 * cur / max(total, 1), sp,
                    "%d:%02d:%02d" % (int(eta) // 3600, (int(eta) % 3600) // 60, int(eta) % 60)
                    if sp > 0.01 else "计算中…")))
        try:
            info2 = kernel_backend.BACKEND.run_video(
                spec,
                progress=on_prog,
                log=lambda s: self.msg.put(("log", s)),
                cancel_event=self.stop_event)
        except kernel_backend.Cancelled:
            raise jobmod.Cancelled()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            try:
                if os.path.exists(cancel):
                    os.remove(cancel)
            except Exception:
                pass
        self.msg.put(("log", "输出：%s  %d×%d  %s 帧  用时 %.1fs（内置加速内核）" % (
            output, int(info2.get("width") or 0), int(info2.get("height") or 0),
            info2.get("frames", 0), float(info2.get("elapsed", 0)))))
        return output

    def _ffmpeg_encode(self, video_in, audio_src, output, c, target):
        """用 ffmpeg 把（无音频）视频流按用户编码设置转成最终文件，并从 audio_src 复制音频。"""
        enc = c["encoder"]
        fmt = c["out_format"]
        is_img = fmt in ("PNG", "JPG", "WEBP_IMG")
        codec, pix, family = vd.ENCODERS.get(enc, vd.ENCODERS["H265 NVENC"])
        out_pix = "yuv420p10le" if "10" in pix else "yuv420p"
        cargs = kernel_backend.codec_args(enc, c["rate_mode"], c["crf"], c["bitrate"],
                                          c["preset"], c["turbo"], out_pix, is_img, fmt)
        cmd = [self.ffmpeg, "-y", "-i", video_in, "-i", audio_src]
        if target:
            # 用户指定了目标分辨率：Lanczos 缩放到目标
            vf = "scale=%d:%d:flags=lanczos" % (target[0], target[1])
        else:
            vf = None
        cmd += ["-map", "0:v:0", "-map", "1:a:0?"]
        cmd += ["-c:v", codec, "-pix_fmt", out_pix] + cargs
        if vf:
            cmd += ["-vf", vf]
        cmd += ["-c:a", "copy"]
        if fmt == "mp4":
            cmd += ["-movflags", "+faststart"]
        cmd += [output]
        self.msg.put(("log", "  ffmpeg 编码：%s" % codec))
        p = procutil.run(cmd, capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
        if p.returncode != 0:
            raise RuntimeError("ffmpeg 编码失败：%s" % ((p.stderr or "")[-400:]))

    # ------------------------------------------------------------ 进程内超分（ONNX，不补帧）
    def _build_job_opts(self, path, c, engine):
        """构造 job.py 流水线的 opts（engine=none 时只超分/转码，不补帧）。"""
        mult = c["mult"] if engine != "none" else 1
        fps = c["fps"] if engine != "none" else 0.0
        return {
            "inputs": [path], "out_dir": c["out_dir"] or os.path.dirname(path),
            "ffmpeg": self.ffmpeg,
            "mult": mult, "engine": engine,
            "encoder": c["encoder"], "rate_mode": c["rate_mode"],
            "crf": c["crf"], "bitrate": c["bitrate"], "preset": c["preset"],
            "out_format": c["out_format"],
            "ext": vd.VIDEO_FORMATS.get(c["out_format"], ".mp4"),
            "sr_device": c["device"], "sr_tile": c["tile"],
            "hwdecode": c["hwdec"], "dedup": False,
            "scene_skip": False, "cut_out": False,
            "cut_blend": True, "cut_extrap": False,
            "turbo": c["turbo"], "out_res_mode": c["out_res"],
            "start": c["start"], "duration": c["duration"],
            "fps": fps, "two_pass": False, "keep_intermediate": c["keep"],
            "sr_first": bool(c.get("sr_first", 1)),
            "name_suffix": c["suffix"],
        }

    def _attach_sr(self, opts, c):
        """把当前选中的超分模型（ONNX 或 ncnn）挂到 job opts 上。"""
        val = self.sr_map.get(c["sr"])
        if not val:
            raise RuntimeError("没有可用的超分模型")
        if val[0] == "onnx":
            opts["sr_model"] = val[1]
        else:
            opts["sr_ncnn"] = val[1]

    def _run_local_job(self, idx, opts):
        job = jobmod.Job(
            opts, log=lambda s: self.msg.put(("log", s)),
            progress=lambda d, t: self.msg.put(("prog", idx, d, t)),
            should_stop=self.stop_event.is_set)
        code = job.run()
        if code == 2:
            raise jobmod.Cancelled()
        if code != 0:
            raise RuntimeError("任务失败，退出码 %s" % code)

    def _do_video_local(self, idx, it, mode, c):
        """仅超分（不补帧）：ONNX 超分模型在进程内用 onnxruntime 跑。"""
        path = it["path"]
        self.msg.put(("log", "进程内 ONNX 超分（不补帧）：%s" % os.path.basename(path)))
        opts = self._build_job_opts(path, c, "none")
        self._attach_sr(opts, c)
        self._run_local_job(idx, opts)

    def _do_video_both_onnx(self, idx, it, mode, c):
        """超分并补帧 + ONNX 超分：两段式。

        第 1 段：内置内核只补帧（超分关）→ 中间片 MKV；
        第 2 段：进程内用 ONNX 引擎对中间片超分 → 最终片。
        """
        path = it["path"]
        stem = os.path.splitext(os.path.basename(path))[0]
        out_dir = c["out_dir"] or os.path.dirname(path)
        os.makedirs(out_dir, exist_ok=True)
        mid_dir = _unique(os.path.join(out_dir, "%s_补帧中间片" % stem))
        os.makedirs(mid_dir, exist_ok=True)

        self.msg.put(("log", "=" * 56))
        self.msg.put(("log", "第 1 段／内置内核补帧：%s（超分关闭，中间片 %s）" % (os.path.basename(path), mid_dir)))
        # 构造一个纯补帧的 cfg 快照：关掉超分、输出到中间片。
        # 关键：中间片必须是「视频文件」（强制 MKV），不能是图片序列——否则第 2 段 ONNX 超分
        # 无法读回中间片，且 _do_video_vs 返回的是 frame_%08d.png 模式串，os.path.isfile 恒为假。
        c1 = dict(c)
        c1["out_dir"] = mid_dir
        c1["out_format"] = "MKV"
        c1["suffix"] = ""
        mid = self._do_video_vs(idx, it, MODE_VFI, c1, None)
        if not os.path.isfile(mid):
            raise RuntimeError("第 1 段没有产出中间片")
        self.msg.put(("log", "中间片：%s" % mid))

        self.msg.put(("log", "-" * 56))
        self.msg.put(("log", "第 2 段／进程内 ONNX 超分：%s（补帧关闭）" % os.path.basename(mid)))
        opts = self._build_job_opts(mid, c, "none")
        opts["start"] = 0.0
        opts["duration"] = 0.0
        self._attach_sr(opts, c)
        self._run_local_job(idx, opts)
        if c.get("keep"):
            self.msg.put(("log", "补帧中间片保留在：%s" % mid_dir))
        else:
            try:
                shutil.rmtree(mid_dir, ignore_errors=True)
                self.msg.put(("log", "已删除补帧中间片目录（勾「保留补帧中间片」可留着）"))
            except Exception:
                pass

    def _do_image(self, idx, it, mode):
        np, Image = _np_pil()
        c = self.cfg
        label = c["sr"]
        if not label or label not in self.sr_map:
            raise RuntimeError("没有可用的超分模型")
        eng = self._get_sr(label, c)
        self.msg.put(("log", "图片超分：%s" % os.path.basename(it["path"])))
        img = Image.open(it["path"]).convert("RGB")
        arr = np.asarray(img)
        out = eng.upscale(arr)
        tw = _target_size(out.shape[1], out.shape[0], c["out_res"])
        if tw:
            rs = getattr(Image, "Resampling", Image).LANCZOS
            out = np.asarray(Image.fromarray(out).resize(tw, rs))
        ext = {"PNG 序列": ".png", "JPG 序列": ".jpg", "WEBP 序列": ".webp"}.get(c["out_format"], ".png")
        suffix = c["suffix"] or "SR"
        suffix = re.sub(r'[\\/:*?"<>|]+', "_", suffix).strip(" .") or "SR"
        out_dir = c["out_dir"] or os.path.dirname(it["path"])
        os.makedirs(out_dir, exist_ok=True)
        name = "%s_%s%s" % (os.path.splitext(os.path.basename(it["path"]))[0], suffix, ext)
        dst = _unique(os.path.join(out_dir, name))
        im = Image.fromarray(out)
        if ext == ".jpg":
            im.save(dst, quality=95, subsampling=0)
        elif ext == ".webp":
            im.save(dst, quality=95)
        else:
            im.save(dst, compress_level=3)
        self.msg.put(("log", "输出：%s  %dx%d" % (dst, out.shape[1], out.shape[0])))
        self.msg.put(("prog", idx, 100, 100))

    def _get_sr(self, label, c):
        val = self.sr_map[label]
        key = (label, c.get("device"), c.get("tile"))
        if key in self._sr_cache:
            return self._sr_cache[key]
        if val[0] == "onnx":
            eng = srmod.SrEngine(val[1], device=c["device"], tile=c["tile"],
                                 log=lambda s: self.msg.put(("log", s)))
        else:
            kind, model = val[1]
            eng = sr_ncnn.SrNcnn(kind, model, gpuid=0 if c["device"] != "cpu" else -1,
                                 log=lambda s: self.msg.put(("log", s)))
        self._sr_cache[key] = eng
        return eng

    # ------------------------------------------------------------ 消息循环
    def _poll(self):
        try:
            while True:
                m = self.msg.get_nowait()
                kind = m[0]
                if kind == "log":
                    self.log.append(m[1].rstrip())
                    sb = self.log.verticalScrollBar()
                    sb.setValue(sb.maximum())
                elif kind == "current":
                    idx, name, total = m[1], m[2], m[3]
                    self.cur_item = idx
                    self.lbl_cur.setText("第 %d/%d 个：%s" % (idx + 1, len(self.items), name))
                    self.pb_main.setValue(0)
                elif kind == "item":
                    idx, status = m[1], m[2]
                    if 0 <= idx < len(self.items):
                        self.items[idx]["status"] = status
                        cell = self.table.item(idx, 3)
                        if cell:
                            cell.setText(status)
                            cell.setForeground(self._status_color(status))
                elif kind == "prog":
                    idx, d, t = m[1], m[2], m[3]
                    pct = int(100.0 * d / t) if t else 0
                    if 0 <= idx < len(self.items):
                        self.items[idx]["progress"] = pct
                        bar = self.item_bars.get(idx)
                        if bar:
                            bar.setValue(pct)
                    if idx == self.cur_item:
                        self.pb_main.setValue(pct)
                elif kind == "done":
                    self.running = False
                    self.btn_start.setEnabled(True)
                    self.btn_stop.setEnabled(False)
                    for b in self.mode_buttons.values():
                        b.setEnabled(True)
                    self.settings_panel.setEnabled(True)
                    ok = sum(1 for it in self.items if it.get("status") == "完成")
                    self.lbl_cur.setText("队列结束：完成 %d / %d" % (ok, len(self.items)))
        except queue.Empty:
            pass

    # ------------------------------------------------------------ 格式转换
    def _conv_add(self):
        if self.conv_running:
            return
        fs, _ = QFileDialog.getOpenFileNames(self, _tl("选择视频"), "",
                                             _tl("视频 (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.ts);;全部 (*.*)"))
        for f in fs:
            if f not in self.conv_files:
                self.conv_files.append(f)
                self.conv_list.addItem(os.path.basename(f))

    def _conv_clear(self):
        if self.conv_running:
            return
        self.conv_files = []
        self.conv_list.clear()

    def _start_convert(self):
        if self.conv_running or self.running:
            return
        if not self.conv_files:
            return
        fmt = self.conv_fmt.currentText().lower()
        enc = self.conv_enc.currentText()
        out_dir = self.conv_out.text().strip() or os.path.dirname(self.conv_files[0])
        self.stop_event.clear()
        self.conv_running = True
        self.btn_conv.setEnabled(False)
        threading.Thread(target=self._run_convert,
                         args=(list(self.conv_files), out_dir, fmt, enc), daemon=True).start()

    def _run_convert(self, files, out_dir, fmt, enc):
        try:
            os.makedirs(out_dir, exist_ok=True)
            codec, pix, family = vd.ENCODERS.get(enc, vd.ENCODERS["H265 NVENC"])
            for i, src in enumerate(files):
                if self.stop_event.is_set():
                    break
                dst = _unique(os.path.join(
                    out_dir, "%s_conv.%s" % (os.path.splitext(os.path.basename(src))[0], fmt)))
                cmd = [self.ffmpeg, "-y", "-i", src, "-c:v", codec, "-pix_fmt", pix]
                if family == "nvenc":
                    cmd += ["-preset", "p5", "-rc", "vbr", "-cq", "18", "-b:v", "0"]
                elif family == "x265":
                    cmd += ["-preset", "fast", "-crf", "18"]
                else:
                    cmd += ["-preset", "fast", "-crf", "18"]
                cmd += ["-c:a", "copy"]
                if fmt == "mp4":
                    cmd += ["-movflags", "+faststart"]
                cmd += [dst]
                self.msg.put(("conv", i, "转换中…  " + os.path.basename(src)))
                p = procutil.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
                if p.returncode != 0:
                    self.msg.put(("conv", i, "失败  " + os.path.basename(src)))
                    self.msg.put(("log", (p.stderr or "")[-500:]))
                else:
                    self.msg.put(("conv", i, "完成  " + os.path.basename(dst)))
        finally:
            self.msg.put(("conv_done", 0))

    # ------------------------------------------------------------ 性能测试
    def _start_bench(self):
        if self.bench_running or self.running or self.conv_running:
            return
        self.bench_running = True
        self.btn_bench.setEnabled(False)
        self.btn_bench_vfi.setEnabled(False)
        threading.Thread(target=self._run_bench, daemon=True).start()

    def _start_bench_vfi(self):
        if self.bench_running or self.running or self.conv_running:
            return
        self.bench_running = True
        self.btn_bench.setEnabled(False)
        self.btn_bench_vfi.setEnabled(False)
        threading.Thread(target=self._run_vfi_bench, daemon=True).start()

    def _run_bench(self):
        np, Image = _np_pil()
        try:
            c = self._snapshot()
            label = c["sr"]
            self.msg.put(("bench", "加载模型…", 5))
            eng = self._get_sr(label, c)
            img = np.zeros((512, 512, 3), np.uint8)
            yy, xx = np.mgrid[0:512, 0:512]
            img[..., 0] = (xx % 256).astype(np.uint8)
            img[..., 1] = (yy % 256).astype(np.uint8)
            img[..., 2] = ((xx + yy) % 256).astype(np.uint8)
            eng.upscale(img)
            self.msg.put(("bench", "预热完成，测试中…", 30))
            n = 3
            t0 = time.time()
            for i in range(n):
                eng.upscale(img)
                self.msg.put(("bench", "测试中… %d/%d" % (i + 1, n), 30 + int(60 * (i + 1) / n)))
            dt = max(time.time() - t0, 1e-6)
            self.msg.put(("bench", "超分 512×512：%.0f ms/帧  ·  %.2f 帧/秒（3 次平均）" % (
                dt / n * 1000, n / dt), 100))
        except Exception as e:
            self.msg.put(("bench", "测试失败：%s" % e, 0))
        finally:
            self.msg.put(("bench_done", 0))

    def _run_vfi_bench(self):
        try:
            c = self._snapshot()
            info = self.rife_map.get(c["vfi"])
            if not info:
                raise RuntimeError("没有可用的 RIFE 模型")
            if not kernel_backend.available():
                raise RuntimeError("内置加速内核不可用")
            self.msg.put(("bench", "加载 RIFE 模型（内置加速内核）…", 10))
            import tempfile as _tf
            tmp = tempfile.mkdtemp(prefix="kernel_bench_", dir=paths.temp_root())
            in_dir = os.path.join(tmp, "in")
            os.makedirs(in_dir, exist_ok=True)
            yy, xx = np.mgrid[0:384, 0:640]
            base = np.stack([(xx % 256), (yy % 256), ((xx + yy) % 256)], -1).astype(np.uint8)
            for i in range(8):
                im = base.copy()
                im[..., 0] = (im[..., 0].astype(np.int16) + i * 8) % 256
                Image.fromarray(im).save(os.path.join(in_dir, "%08d.png" % (i + 1)))
            # 用一张 PNG 序列跑一次 RIFE（factor 2），测纯补帧速度
            spec = {
                "input": in_dir, "image_seq": True, "ffmpeg": self.ffmpeg, "tmp": tmp,
                "output": os.path.join(tmp, "out", "frame_%08d.png"),
                "start": 0, "duration": 0, "out_pix": "yuv420p",
                "codec": "png", "codec_args": [], "audio": False,
                "cancel": os.path.join(tmp, "cancel.flag"),
                "vfi": {"model": info["model"], "gpu": 0,
                        "factor_num": 2, "factor_den": 1, "scene": 0, "dedup": 0},
                "sr": None,
            }
            t0 = time.time()
            info2 = kernel_backend.BACKEND.run_video(
                spec,
                progress=lambda a, b, f: self.msg.put(
                    ("bench", "补帧测试 %d/%d" % (a, b), 10 + int(80 * a / max(b, 1)))),
                log=lambda s: self.msg.put(("log", s)))
            dt = max(time.time() - t0, 1e-6)
            frames = int(info2.get("frames", 0) or 0)
            self.msg.put(("bench", "补帧 8→%d 帧（640×384，内置加速内核）：%.0f ms  ·  %.2f 帧/秒" % (
                frames, dt * 1000, frames / dt), 100))
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception as e:
            self.msg.put(("bench", "补帧测试失败：%s" % e, 0))
        finally:
            self.msg.put(("bench_done", 0))

    # ------------------------------------------------------------ 设置/恢复
    def _restore(self):
        self._tick(_tl("正在恢复设置…"), 0.93)
        s = self.setting
        if s.get("out_dir"):
            self.out_edit.setText(s["out_dir"])
            self.set_out.setText(s["out_dir"])
        if s.get("suffix"):
            self.name_edit.setText(s["suffix"])
        if s.get("mode") in self.mode_buttons:
            self.mode_buttons[s["mode"]].setChecked(True)
        self._yield()
        for cb, key in ((self.cb_sr, "sr"), (self.cb_vfi, "vfi"),
                        (self.cb_enc, "encoder"), (self.cb_res, "out_res"),
                        (self.cb_fmt, "out_fmt"), (self.cb_rate, "rate"),
                        (self.cb_dev, "dev"), (self.cb_tile, "tile_label"),
                        (self.cb_kernel, "kernel")):
            val = s.get(key)
            if val:
                i = _combo_select(cb, val)
                if i < 0 and key in ("vfi", "sr"):
                    # 旧标签升级后带分类名/后缀，做前缀或包含匹配（匹配 itemData 原文）
                    for j in range(cb.count()):
                        _d = cb.itemData(j)
                        _t = _d if isinstance(_d, str) else cb.itemText(j)
                        if _t.startswith(str(val)) or str(val) in _t or _t in str(val):
                            cb.setCurrentIndex(j)
                            break
        self._sync_sr_desc()
        self._sync_vfi_desc()
        self._yield()
        if s.get("fps"):
            try:
                self.sp_fps.setValue(int(float(s["fps"])))
            except Exception:
                pass
        fm = s.get("fps_mode")
        if fm == "自定义" or (not fm and s.get("fps")):
            self.rb_fps.setChecked(True)
        else:
            if fm:
                i = self.cb_fps_mode.findText(fm)
                if i >= 0:
                    self.cb_fps_mode.setCurrentIndex(i)
            self.rb_mult.setChecked(True)
        if s.get("rate_mode") == "bitrate" and s.get("bitrate"):
            try:
                self.sp_q.setValue(int(float(s["bitrate"])))
            except Exception:
                pass
        elif s.get("crf") is not None:
            try:
                self.sp_q.setValue(int(float(s["crf"])))
            except Exception:
                pass
        if "sr_first" in s:
            self.chk_two.setChecked(bool(s["sr_first"]))
        for w, key in ((self.chk_keep, "keep"), (self.chk_dedup, "dedup"),
                       (self.chk_scene, "scene"),
                       (self.chk_hw, "hwdec"), (self.chk_turbo, "turbo"),
                       (self.chk_workres, "sr_workres"), (self.chk_trt, "use_trt")):
            if key in s:
                w.setChecked(bool(s[key]))
        if s.get("dup_thr") is not None:
            try:
                self.sp_dup.setValue(float(s["dup_thr"]))
            except Exception:
                pass
        if s.get("font_family"):
            _combo_select(self.cb_font, s["font_family"])
        elif s.get("font"):
            _combo_select(self.cb_font, s["font"])
        for k, v in (s.get("paths") or {}).items():
            if k in self.path_edits and v:
                self.path_edits[k].setText(str(v))
        self._apply_tool_paths(silent=True)
        self._yield()
        self._rebuild_env()
        self._apply_theme(s.get("theme") or self.theme)
        # 启动阶段 _refresh_stylesheet 是空操作（样式已按最终主题铺好），
        # 这里只把外观相关的控件状态补上，真正的全局刷新留给 _finish_boot()
        self._tick(_tl("正在应用外观…"), 0.96)
        self._apply_font_choice()
        self._sync_mode()
        self._yield()
        # 恢复语言选中项（含简体中文：Qt 内置对话框的文字也要跟随语言）
        lang_code = s.get("lang", "zh-CN")
        if hasattr(self, "cb_lang"):
            i = self.cb_lang.findData(lang_code)
            if i >= 0:
                self.cb_lang.blockSignals(True)
                self.cb_lang.setCurrentIndex(i)
                self.cb_lang.blockSignals(False)
        _i18n.set_lang(lang_code)
        _i18n.install_qt_translator()
        if lang_code != "zh-CN":
            self._retranslate_ui()

    def _save_from_settings(self):
        self._apply_tool_paths()
        self.out_edit.setText(self.set_out.text().strip())
        self._save_settings()
        QMessageBox.information(self, _tl("设置"), _tl("已保存"))

    def closeEvent(self, e):
        if self.running:
            self.stop_event.set()
        try:
            kernel_backend.BACKEND.stop()
        except Exception:
            pass
        try:
            self._save_settings()
        except Exception:
            pass
        super().closeEvent(e)

    # ------------------------------------------------------------ 杂项
    def _purge_cache(self):
        if self.running:
            QMessageBox.warning(self, _tl("清理缓存"), _tl("任务正在跑，等结束再清理"))
            return
        size = paths.dir_size(paths.TEMP_DIR) + paths.dir_size(paths.CACHE_DIR)
        for p in paths.legacy_cache_paths():
            size += paths.dir_size(p)
        if QMessageBox.question(
                self, _tl("清理缓存"),
                _tl("将删除补帧缓存和临时文件（含 C 盘旧缓存，约 %.0f MB）。\n继续？")
                % (size / 1048576.0)) != QMessageBox.Yes:
            return
        freed = paths.purge_caches()
        QMessageBox.information(self, _tl("清理缓存"), _tl("已释放 %.0f MB") % (freed / 1048576.0))

    def _drag_pause_bg(self):
        """是否在拖动期间暂停动态壁纸（跟随设置项，默认关闭）。"""
        cb = getattr(self, "chk_pause_bg", None)
        return bool(cb is not None and cb.isChecked())

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            if self._drag_pause_bg():
                self.bg.pause_video()

    def dragMoveEvent(self, e):
        # 轻量接受即可，避免默认实现反复做落点判定
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.bg.resume_video()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        try:
            if files:
                self._add_paths(files)
        finally:
            # 未暂停时是空操作，保证任何路径下壁纸都会恢复
            self.bg.resume_video()


def _boot_qss_from_settings():
    """按已保存的主题/字体先算一遍样式表，让界面从第一笔就画成最终样子。

    这样启动阶段就不用再反复 setStyleSheet（每次要整棵树重新 polish，
    实测 0.2~0.3s，正好把过渡页动画冻住）。
    """
    st = {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            st = json.load(f) or {}
    except Exception:
        st = {}
    fam = st.get("font_family") or "Microsoft YaHei UI"
    try:
        glass = max(0.0, min(_GLASS_MAX, float(st.get("glass", 0.0))))
    except Exception:
        glass = 0.0
    theme = st.get("theme") or "浅色"
    if theme not in THEMES:
        theme = "浅色"
    return fam, _make_qss(theme, fam, st.get("accent_color", "") or "",
                          st.get("text_color", "") or "", glass)


def run(splash=None):
    paths.ensure_work_dirs()
    atexit.register(kernel_backend.BACKEND.stop)
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    # 预装 Qt 官方语言包（语言由 MainWindow 恢复设置后再精确切换一次）
    _i18n.install_qt_translator(app)
    # 字体与样式表在「还没有任何控件」的时候装好，成本几乎是 0；
    # 之后 MainWindow 建出来的每个控件第一次 polish 就已经是最终样式
    fam, boot_qss = _boot_qss_from_settings()
    app.setFont(_app_font(fam))
    app.setStyleSheet(boot_qss)

    def _tick(text=None, progress=None):
        """构建过程中回报进度：过渡页据此更新文字并继续跑动画。"""
        if splash is not None:
            splash.set_stage(text, progress)

    _tick(_tl("正在搭建界面…"), 0.22)
    w = MainWindow(tick=_tick, boot_qss=boot_qss)
    _tick(_tl("即将完成…"), 0.97)
    # 收尾必须在 show() 之前：万一真的需要一次全局重新 polish，也是在过渡页
    # 还盖着的时候做完，不会让刚露面的窗口卡一下。
    # 标题栏要碰 winId()（提前建原生窗口，约 0.1s），有过渡页时挪到露面之后再做
    w._finish_boot(apply_titlebar=splash is None)
    w.show()
    if splash is not None:
        splash.finish(w)
        # 标题栏跟随主题要碰 winId()，等过渡页淡出之后再改，避免拖慢露面
        QTimer.singleShot(400, w._apply_titlebar_theme)
    return app.exec()
