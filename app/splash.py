# -*- coding: utf-8 -*-
"""启动过渡页：程序图标 + 环绕流动的彩色粒子。

单独成文件、只依赖 PySide6（不碰 numpy / PIL），所以 `main.py` 可以在
`import gui_main`（约 0.2s）之前就把它显示出来，点开程序立刻有反馈。

流畅度靠两件事：
  1. 静态层（卡片/投影/文字/轨道/进度槽）烘成一张图，每帧只贴一次，
     只重画粒子、光晕、进度这些真正在动的东西，单帧绘制约 1ms；
  2. `pump()` 主动让出一小段事件循环，主界面构建时在每个耗时步骤的边界
     调用它，动画就不会被一次几秒的连续构建冻住。

用法：
    s = splash.start()                  # 建 QApplication（已存在则复用）+ 显示 + 画首帧
    s.set_stage("正在搭建界面…", 0.3)    # 更新进度文字（内部会 pump 一帧）
    s.pump()                            # 只让出一帧，不改文字
    s.finish(win)                       # 主窗口 show() 之后调用，淡出并关闭
"""
import json
import math
import os
import sys

from PySide6.QtCore import (Qt, QElapsedTimer, QEventLoop, QEasingCurve, QPointF,
                            QPropertyAnimation, QRectF, QTimer)
from PySide6.QtGui import (QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap,
                           QRadialGradient)
from PySide6.QtWidgets import QApplication, QWidget

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# 粒子配色：落在图标的青→蓝→紫→品红范围内，避免出现「彩虹」那种廉价感
_HUE_FROM = 188.0
_HUE_SPAN = 152.0

# 色相→颜色的缓存（0.5° 精度）：每帧几百个粒子点，不走缓存要反复算 HSV
_HUE_CACHE = {}

# 布局常量（静态层与动态层共用，改这里就够）
_ICON_CY = 104.0
_ICON_R = 60.0

# 最短展示时长（秒）：界面构建很快时（热启动），过渡页会刚出来就被收掉，
# 观感上是「闪一下」，比不显示还糟。给个下限，让它把这一段动画走完再淡出。
_MIN_SHOW = 0.34

_CFG = {
    "深色": dict(card_top=(34, 43, 58, 246), card_bot=(17, 22, 31, 246),
                 border=(255, 255, 255, 28), fg=(240, 245, 250), sub=(150, 165, 182),
                 track=(255, 255, 255, 26), shadow=150),
    "紫色": dict(card_top=(250, 247, 255, 248), card_bot=(238, 233, 250, 248),
                 border=(120, 100, 170, 40), fg=(38, 30, 56), sub=(112, 102, 138),
                 track=(80, 60, 120, 26), shadow=110),
    "浅色": dict(card_top=(255, 255, 255, 250), card_bot=(238, 243, 249, 250),
                 border=(30, 50, 80, 30), fg=(28, 36, 48), sub=(120, 132, 148),
                 track=(30, 50, 80, 22), shadow=110),
}


def _read_prefs():
    """只读设置文件里的主题 / 语言，2ms 级别，不值得为它拉起整套 i18n。"""
    try:
        with open(os.path.join(APP_DIR, "settings_qt.json"), encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _apply_lang(prefs):
    """跟随设置里的界面语言（主界面恢复设置后会再切一次）。"""
    try:
        import i18n as _i18n
        _i18n.set_lang(prefs.get("lang", "zh-CN"))
    except Exception:
        pass


def _tr(text):
    try:
        import i18n as _i18n
        return _i18n.tr(text)
    except Exception:
        return text


def _rand(i):
    """稳定的伪随机（同一台机器每帧一致，不会闪）。"""
    v = math.sin(i * 12.9898) * 43758.5453
    return v - math.floor(v)


def _hue_color(hue_deg, dark):
    """色相查表：同一色相只构造一次 QColor，省掉每帧几百次 HSV 换算。"""
    key = (int(hue_deg * 2.0) % 720, dark)
    c = _HUE_CACHE.get(key)
    if c is None:
        c = QColor.fromHsvF(key[0] / 720.0, 0.72 if dark else 0.88, 1.0)
        _HUE_CACHE[key] = c
    return c


class Splash(QWidget):
    """无边框圆角过渡页：图标居中，彩色粒子沿椭圆轨道前后穿插旋转。"""

    def __init__(self):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("splash")
        self.setStyleSheet("background: transparent; border: none;")
        self.setFixedSize(452, 336)
        self.setWindowTitle("CHEN-V")

        prefs = _read_prefs()
        theme = prefs.get("theme") or "浅色"
        self._cfg = _CFG.get(theme, _CFG["浅色"])
        self._dark = theme != "浅色"
        _apply_lang(prefs)
        self._stage = _tr("正在启动…")
        self._prog = 0.04

        icon = os.path.join(APP_DIR, "icon.png")
        self._icon = QPixmap(icon) if os.path.isfile(icon) else QPixmap()
        self._icon_small = None            # 预缩放到最终尺寸，每帧直接贴
        self._base = None                  # 静态层缓存
        self._base_key = None

        # 字体只建一次：每帧 new QFont 会让 Qt 反复走字体匹配。
        # 这里把字体族写死（跟设置里的界面字体一致），是为了让它们不随
        # 之后 app.setFont()/setStyleSheet() 变化而重新解析——否则第一帧
        # 画字会再初始化一次字体引擎，实测要 0.6s，粒子就那样定住了。
        _fam = prefs.get("font_family") or "Microsoft YaHei UI"

        def _mk_font(px, bold=False):
            # 只给单一字体族：字体族列表要走另一条更贵的解析路径（实测多 230ms）
            f = QFont(_fam)
            f.setPixelSize(px)
            if bold:
                f.setBold(True)
            return f

        self._f_title = _mk_font(23, bold=True)
        self._f_title.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        self._f_sub = _mk_font(12)
        self._f_stage = _mk_font(11)

        # 粒子参数一次算好：轨道半径/速度/相位/大小/拖尾长度
        self._parts = []
        n = 30
        for i in range(n):
            r1, r2 = _rand(i + 1), _rand(i + 31)
            self._parts.append((
                r1 * math.tau,                       # 起始相位
                (0.85 + r2 * 0.9) * (1 if i % 2 else -1),   # 角速度（正反各半）
                96 + _rand(i + 61) * 34,             # 轨道 rx
                40 + _rand(i + 91) * 20,             # 轨道 ry
                1.15 + _rand(i + 121) * 1.5,         # 半径（大了就是一坨光斑）
                0.62 + _rand(i + 151) * 0.38,        # 亮度
                10 + int(_rand(i + 181) * 6),        # 拖尾点数（多而密才像流线）
            ))

        self._t = 0.0
        self._clock = QElapsedTimer()
        self._clock.start()
        self._last = 0.0
        self._fade = None
        self._delay = None
        self._warm_text()
        self._timer = QTimer(self)
        # Precise：默认的粗定时器允许 ±5% 抖动，粒子走起来会一顿一顿
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick_frame)

        self._center_on_screen()

    # ------------------------------------------------------------ 对外接口
    def set_stage(self, text=None, progress=None):
        """更新进度文字 / 进度值，并立刻跑一帧（构建主界面时靠它保持动画）。"""
        if text:
            self._stage = text
        if progress is not None:
            self._prog = max(0.0, min(1.0, float(progress)))
        self.pump()

    def tick(self, text=None, progress=None):
        self.set_stage(text, progress)

    def pump(self, budget_ms=10):
        """让出一小段事件循环用来画帧；构建主界面时在每个耗时步骤后调用。

        先 repaint() 同步把这一帧画出来，再放事件循环跑：只 update() 的话，
        事件队列一忙，Qt 可能在给的这 10ms 里根本没轮到绘制，构建期间就会出现
        「隔半秒才动一下」的观感。
        """
        self._advance()
        self.repaint()
        QApplication.processEvents(QEventLoop.ExcludeUserInputEvents, budget_ms)

    def finish(self, win=None):
        """主窗口已 show 之后调用：淡出，关闭。

        构建得快时（热启动）这里可能只隔了 0.1s，直接淡出就是「闪一下」，
        所以先补足最短展示时长，动画继续跑着，到点再淡出。
        """
        if self._fade is not None:          # 已经在收尾了，别重复
            return
        left = _MIN_SHOW - (self._clock.elapsed() / 1000.0 if self._clock.isValid()
                            else _MIN_SHOW)
        if left > 0.02:
            # 用挂在窗口上的定时器：窗口若提前销毁，它跟着一起走，不会回调到野指针
            self._delay = QTimer(self)
            self._delay.setSingleShot(True)
            self._delay.timeout.connect(self._do_finish)
            self._delay.start(int(left * 1000))
        else:
            self._do_finish()

    def _do_finish(self):
        if self._fade is not None:
            return
        try:
            self._timer.stop()
        except RuntimeError:                # 窗口已被销毁
            return
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(240)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.finished.connect(self._safe_close)
        self._fade.start()
        # 兜底：万一窗口透明度动画在某些合成器上不触发 finished，也一定要关掉
        QTimer.singleShot(600, self._safe_close)

    def _safe_close(self):
        try:
            self.close()
        except RuntimeError:      # 已随 WA_DeleteOnClose 销毁
            pass

    # ------------------------------------------------------------ 内部
    def _center_on_screen(self):
        scr = QApplication.primaryScreen()
        if scr is None:
            return
        geo = scr.availableGeometry()
        self.move(geo.center().x() - self.width() // 2,
                  geo.center().y() - self.height() // 2)

    def _warm_text(self):
        """先把 Qt 的字体引擎初始化掉（首次画字要 300ms 左右）。

        这笔开销无论如何都要付（主界面的第一行字同样要付），放在 show() 之前做，
        第一帧出来就是完整的，后面每一帧就只剩贴图和粒子，不会再突然定住。
        """
        try:
            pm = QPixmap(8, 8)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            # 用真实的字样预热：中文首帧要单独初始化字形，只画 "CHEN-V" 不够
            for f, txt in ((self._f_title, "CHEN-V"),
                           (self._f_sub, _tr("补帧 + 超分 · 本地运行")),
                           (self._f_stage, self._stage)):
                p.setFont(f)
                p.drawText(0, 6, txt)
            p.end()
        except Exception:
            pass

    def _advance(self):
        now = self._clock.elapsed() / 1000.0
        dt = min(0.10, max(0.0, now - self._last))    # 卡顿后不要一次跳太多
        self._last = now
        self._t += dt

    def _tick_frame(self, pump=False):
        self._advance()
        self.update()
        if pump:
            # 排除用户输入：构建界面期间被点到会重入到半成品状态
            QApplication.processEvents(QEventLoop.ExcludeUserInputEvents, 8)

    def showEvent(self, e):
        super().showEvent(e)
        self._clock.restart()
        self._last = 0.0
        self._timer.start()

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        t = self._t
        cfg = self._cfg
        W = self.width()

        # 静态层：卡片、投影、文字、轨道、进度槽 —— 贴图代替重画
        key = (W, self.height(), float(self.devicePixelRatioF() or 1.0))
        if self._base is None or self._base_key != key:
            self._base = self._render_base()
            self._base_key = key
        p.drawPixmap(0, 0, self._base)

        icon_c = QPointF(W / 2.0, _ICON_CY)
        accent = self._accent()

        # 图标背后的光晕（呼吸）
        pulse = 0.72 + 0.28 * math.sin(t * 2.2)
        glow = QRadialGradient(icon_c, _ICON_R * 1.9)
        c0 = QColor(accent)
        c0.setAlphaF(0.42 * pulse)
        c1 = QColor(accent)
        c1.setAlphaF(0.0)
        glow.setColorAt(0.0, c0)
        glow.setColorAt(0.55, QColor(accent.red(), accent.green(), accent.blue(),
                                     int(24 * pulse)))
        glow.setColorAt(1.0, c1)
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(icon_c, _ICON_R * 1.9, _ICON_R * 1.9)

        # 后半圈粒子（被图标挡住的部分先画）
        self._draw_particles(p, icon_c, front=False)
        # 图标
        if self._icon_small is not None:
            p.drawPixmap(QPointF(icon_c.x() - _ICON_R, icon_c.y() - _ICON_R),
                         self._icon_small)
        # 前半圈粒子（压在图标上方，形成前后穿插）
        self._draw_particles(p, icon_c, front=True)

        # 进度条填充 + 流光
        track = QRectF(96, 254, W - 192, 4)
        if self._prog > 0.001:
            fill = QRectF(track.x(), track.y(), max(6.0, track.width() * self._prog),
                          track.height())
            fg2 = QLinearGradient(fill.topLeft(), fill.topRight())
            a = QColor(accent)
            b = QColor(accent)
            b.setHslF((b.hueF() + 0.10) % 1.0, min(1.0, b.saturationF() + 0.1), 0.66)
            fg2.setColorAt(0.0, a)
            fg2.setColorAt(1.0, b)
            p.setPen(Qt.NoPen)
            p.setBrush(fg2)
            p.drawRoundedRect(fill, 2, 2)
            # 沿进度条跑的一小段高光，让等待有「在动」的感觉
            x = track.x() + (track.width() - 60) * ((math.sin(t * 1.1) + 1) / 2)
            hi = QRectF(x, track.y(), 60, track.height())
            hg = QLinearGradient(hi.topLeft(), hi.topRight())
            hg.setColorAt(0.0, QColor(255, 255, 255, 0))
            hg.setColorAt(0.5, QColor(255, 255, 255, 90))
            hg.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(hg)
            p.drawRoundedRect(hi, 2, 2)

        # 状态文字（每阶段才变一次，直接画）
        p.setFont(self._f_stage)
        p.setPen(QColor(*cfg["sub"]))
        p.drawText(QRectF(0, 268, W, 22), Qt.AlignHCenter | Qt.AlignVCenter, self._stage)

    def _render_base(self):
        """把不动的部分烘成一张图：卡片 + 投影 + 标题 + 轨道线 + 进度槽。"""
        dpr = float(self.devicePixelRatioF() or 1.0)
        W, H = self.width(), self.height()
        cfg = self._cfg
        pm = QPixmap(int(round(W * dpr)), int(round(H * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        card = QRectF(14, 14, W - 28, H - 28)
        # 投影：几层低透明度圆角矩形，比 QGraphicsDropShadowEffect 便宜得多
        p.setPen(Qt.NoPen)
        for k in (10, 7, 4):
            a = int(cfg["shadow"] * (0.10 if k == 10 else 0.14 if k == 7 else 0.18))
            p.setBrush(QColor(0, 0, 0, a))
            p.drawRoundedRect(card.adjusted(-k, -k + 4, k, k + 6), 20, 20)

        # 卡片本体
        g = QLinearGradient(card.topLeft(), card.bottomLeft())
        g.setColorAt(0.0, QColor(*cfg["card_top"]))
        g.setColorAt(1.0, QColor(*cfg["card_bot"]))
        p.setBrush(g)
        p.setPen(QPen(QColor(*cfg["border"]), 1))
        p.drawRoundedRect(card, 20, 20)

        # 轨道参考线（很淡，给粒子一个「在绕圈」的空间感）
        icon_c = QPointF(W / 2.0, _ICON_CY)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 16) if self._dark
                      else QColor(20, 40, 70, 16), 1))
        p.drawEllipse(icon_c, 108.0, 47.0)
        p.drawEllipse(icon_c, 122.0, 55.0)

        # 标题与副标题
        p.setFont(self._f_title)
        p.setPen(QColor(*cfg["fg"]))
        p.drawText(QRectF(0, 186, W, 34), Qt.AlignHCenter | Qt.AlignVCenter, "CHEN-V")
        p.setFont(self._f_sub)
        p.setPen(QColor(*cfg["sub"]))
        p.drawText(QRectF(0, 216, W, 20), Qt.AlignHCenter | Qt.AlignVCenter,
                   _tr("补帧 + 超分 · 本地运行"))

        # 进度槽
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(*cfg["track"]))
        p.drawRoundedRect(QRectF(96, 254, W - 192, 4), 2, 2)
        p.end()

        # 图标预缩放到最终显示尺寸（120 逻辑像素），避免每帧重采样
        if not self._icon.isNull():
            d = int(round(_ICON_R * 2 * dpr))
            self._icon_small = self._icon.scaled(d, d, Qt.KeepAspectRatio,
                                                 Qt.SmoothTransformation)
            self._icon_small.setDevicePixelRatio(dpr)
        return pm

    def _accent(self):
        """主题强调色（QColor 不能直接吃元组，必须拆成 r,g,b）。"""
        return QColor(96, 165, 250) if self._dark else QColor(37, 99, 235)

    def _draw_particles(self, p, c, front):
        t = self._t
        dark = self._dark
        p.setPen(Qt.NoPen)
        for a0, spd, rx, ry, rad, bright, trail in self._parts:
            th = a0 + spd * t
            z = math.sin(th)                       # >0 认为在近侧
            if (z >= 0) != front:
                continue
            depth = 0.55 + 0.45 * ((z + 1) / 2)    # 远侧更暗更小
            # 色相只跟粒子本身与全局时间有关，一次算好，整条拖尾共用
            base_col = _hue_color(_HUE_FROM + _HUE_SPAN * ((a0 / math.tau + t * 0.06) % 1.0),
                                  dark)
            step = math.copysign(0.024, spd)       # 点距小一点，拖尾才连成流线
            for k in range(trail):
                th_k = th - step * k
                x = c.x() + rx * math.cos(th_k)
                y = c.y() + ry * math.sin(th_k)
                fade = (1.0 - k / float(trail)) ** 1.6
                r = rad * depth * (0.30 + 0.70 * fade)
                al = int(255 * bright * depth * fade)
                if k == 0:
                    # 只在头部画一层薄光雾：光雾太大就会糊成一团
                    halo = QColor(base_col)
                    halo.setAlpha(max(0, int(al * 0.20)))
                    p.setBrush(halo)
                    p.drawEllipse(QPointF(x, y), r * 2.3, r * 2.3)
                col = QColor(base_col)
                col.setAlpha(max(0, al))
                p.setBrush(col)
                p.drawEllipse(QPointF(x, y), r, r)
            # 头部一点白色高光：给粒子一个「亮点」，而不是一坨光斑
            hc = QColor(255, 255, 255)
            hc.setAlpha(max(0, int(140 * bright * depth)))
            p.setBrush(hc)
            hr = rad * depth * 0.40
            p.drawEllipse(QPointF(c.x() + rx * math.cos(th),
                                  c.y() + ry * math.sin(th)), hr, hr)


def start():
    """显示过渡页并画出首帧；已有 QApplication 就复用。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    s = Splash()          # 构造时会读设置里的主题/语言
    s.show()
    s.raise_()
    app.processEvents()
    return s
