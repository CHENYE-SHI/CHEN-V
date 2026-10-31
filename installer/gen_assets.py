# -*- coding: utf-8 -*-
"""生成 CHEN-V 安装程序美化素材：深蓝紫渐变横幅 + 图标处理。"""
from PIL import Image, ImageDraw, ImageFilter
import os

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
os.makedirs(ASSETS, exist_ok=True)


def _v_gradient(w, h, top, bottom):
    """生成竖直渐变图。"""
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        d.line([(0, y), (w, y)], fill=(r, g, b))
    return img


def make_banner():
    """欢迎页/结束页横幅（NSIS 标准 150x57，这里做 2x 高清 300x114 再缩放可选）。
    直接用标准尺寸 150x57 以保证不拉伸。"""
    w, h = 150, 57
    # 深青蓝 → 紫 渐变（呼应图标背景）
    top = (0x1A, 0x5A, 0x7A)
    bottom = (0x6B, 0x2D, 0x8F)
    img = _v_gradient(w, h, top, bottom)
    d = ImageDraw.Draw(img)
    # 顶部玫红弧线装饰（呼应图标）
    d.arc([-20, -8, w + 20, 30], 200, 340, fill=(0xF0, 0x30, 0x6A), width=2)
    # 青色虚线环（装饰点）
    for i in range(6):
        x = 18 + i * 20
        y = 38
        d.ellipse([x, y, x + 4, y + 4], fill=(0x33, 0xD6, 0xCC))
    # 右下角星形点缀
    sx, sy = w - 16, 12
    d.polygon([(sx, sy - 6), (sx + 2, sy - 2), (sx + 6, sy), (sx + 2, sy + 2), (sx, sy + 6), (sx - 2, sy + 2), (sx - 6, sy), (sx - 2, sy - 2)], fill=(0xF0, 0x30, 0x6A))
    out = os.path.join(ASSETS, "banner.bmp")
    img.save(out)
    print("banner.bmp ->", out, img.size)


def make_header():
    """页眉横幅（现代 UI 风格，标准 150x57）。"""
    w, h = 150, 57
    top = (0x1A, 0x5A, 0x7A)
    bottom = (0x6B, 0x2D, 0x8F)
    img = _v_gradient(w, h, top, bottom)
    d = ImageDraw.Draw(img)
    d.line([(0, h - 1), (w, h - 1)], fill=(0xF0, 0x30, 0x6A), width=2)
    out = os.path.join(ASSETS, "header.bmp")
    img.save(out)
    print("header.bmp ->", out, img.size)


def make_welcome_large():
    """可选：欢迎页左侧大背景（NSIS MUI2 支持 WELCOME 页 164x314 位图）。
    生成 164x314 的竖版渐变 + 装饰，用于左侧视觉。"""
    w, h = 164, 314
    top = (0x1A, 0x5A, 0x7A)
    bottom = (0x6B, 0x2D, 0x8F)
    img = _v_gradient(w, h, top, bottom)
    d = ImageDraw.Draw(img)
    # 玫红圆环（呼应头像圆环）
    cx, cy, r = w // 2, 100, 42
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(0xF0, 0x30, 0x6A), width=3)
    # 虚线装饰环
    import math
    for ang in range(0, 360, 30):
        a = math.radians(ang)
        x1 = cx + (r + 8) * math.cos(a)
        y1 = cy + (r + 8) * math.sin(a)
        d.rectangle([x1 - 2, y1 - 2, x1 + 2, y1 + 2], fill=(0x33, 0xD6, 0xCC))
    out = os.path.join(ASSETS, "welcome.bmp")
    img.save(out)
    print("welcome.bmp ->", out, img.size)


if __name__ == "__main__":
    make_banner()
    make_header()
    make_welcome_large()
    print("全部素材生成完成")
