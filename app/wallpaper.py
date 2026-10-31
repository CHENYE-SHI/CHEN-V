# -*- coding: utf-8 -*-
"""壁纸文件夹扫描。

从一个用户指定的目录递归扫描可直接用作背景的壁纸文件：
  - 视频壁纸：.mp4 / .webm / .mkv / .mov（可动态播放）
  - 静态壁纸：.png / .jpg / .jpeg / .webp / .bmp / .gif

不再依赖 Wallpaper Engine 的 Steam 订阅目录，改成让用户自己指定目录。
"""

import os

VIDEO_EXTS = (".mp4", ".webm", ".mkv", ".mov", ".avi")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")


def _is_video(path):
    return path.lower().endswith(VIDEO_EXTS)


def _is_image(path):
    return path.lower().endswith(IMAGE_EXTS)


def list_wallpapers(directory):
    """扫描 directory（递归）里的壁纸文件，返回 [{...}] 列表。

    每个元素：
        {
            "title":  str,   # 文件名（不含扩展名）
            "type":   "video" | "image",
            "file":   str,   # 文件绝对路径
            "preview": str,  # 同 file（视频用第一帧做预览，由 GUI 自行处理）
            "dir":    str,   # 所在目录
        }
    """
    out = []
    if not directory or not os.path.isdir(directory):
        return out
    try:
        for root, _dirs, files in os.walk(directory):
            for fn in files:
                if not _is_video(fn) and not _is_image(fn):
                    continue
                full = os.path.join(root, fn)
                title = os.path.splitext(fn)[0]
                out.append({
                    "title": title,
                    "type": "video" if _is_video(fn) else "image",
                    "file": full,
                    "preview": full,
                    "dir": root,
                })
    except Exception:
        pass
    # 视频优先，再按标题排序
    out.sort(key=lambda x: (x["type"] != "video", x["title"].lower()))
    return out
