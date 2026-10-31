# -*- coding: utf-8 -*-
"""CHEN-V 在线更新检查与公告拉取。

数据源（作者在 GitHub 上维护，程序只读不写）：
  - 最新版本号：GitHub Releases 的最新 tag（API: api.github.com/repos/<owner>/CHEN-V/releases/latest）
  - 公告：仓库根目录的 announce.json（raw.githubusercontent.com/<owner>/CHEN-V/main/announce.json）

所有网络请求都走短超时 + 后台线程，绝不阻塞主界面；失败一律静默回退为「本地版」。
"""
import json
import threading
import time
import urllib.request
import urllib.error


# 作者维护的 GitHub 仓库。发布到 GitHub 后这两个值就是最终值；
# 若作者后续改账号名，只需改这里。
GITHUB_OWNER = "CHENYE-SHI"
GITHUB_REPO = "CHEN-V"

_RELEASES_API = "https://api.github.com/repos/%s/%s/releases/latest" % (GITHUB_OWNER, GITHUB_REPO)
_ANNOUNCE_RAW = "https://raw.githubusercontent.com/%s/%s/main/announce.json" % (GITHUB_OWNER, GITHUB_REPO)
# 下载页（点「去下载」跳转到这里）
_RELEASES_PAGE = "https://github.com/%s/%s/releases" % (GITHUB_OWNER, GITHUB_REPO)

_TIMEOUT = 8  # 秒；联网失败不能拖慢启动/响应


def _http_get_json(url):
    """GET 并解析 JSON，失败返回 None。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "CHEN-V-updater/1.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            data = r.read().decode("utf-8", "replace")
        return json.loads(data)
    except Exception:
        return None


def _http_get_text(url):
    """GET 返回文本，失败返回 None。"""
    req = urllib.request.Request(url, headers={"User-Agent": "CHEN-V-updater/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def releases_page_url():
    return _RELEASES_PAGE


def _strip_v(tag):
    """把 'V1.02' / 'v1.02' / '1.02' 统一成 '1.02' 用于比较。"""
    if not tag:
        return ""
    s = tag.strip()
    if s and s[0].lower() == "v":
        s = s[1:]
    return s.strip()


def _ver_tuple(v):
    """'1.02.03' -> (1, 2, 3)；无法解析返回 ()。"""
    try:
        return tuple(int(x) for x in v.split(".") if x != "")
    except Exception:
        return ()


def is_newer(remote_ver, local_ver):
    """remote_ver 是否严格高于 local_ver。"""
    a, b = _ver_tuple(remote_ver), _ver_tuple(local_ver)
    if not a:
        return False
    if not b:
        return True
    # 补齐长度再逐段比较
    n = max(len(a), len(b))
    a = a + (0,) * (n - len(a))
    b = b + (0,) * (n - len(b))
    return a > b


class UpdateState:
    """一次检查结果。字段都可能为 None，调用方需容错。"""

    def __init__(self):
        self.checked_at = 0.0          # 检查时间戳
        self.latest_ver = None         # 最新版本号字符串（不含 V）
        self.latest_tag = None         # 原始 tag
        self.latest_body = None        # 更新日志
        self.has_update = False        # 是否有更新
        self.announce = None           # 公告 dict（或 None）
        self.announce_title = None     # 公告标题
        self.announce_body = None      # 公告正文
        self.error = None              # 出错信息（成功为 None）


def check_updates(local_ver, on_done, want_announce=True, lang="zh-CN"):
    """后台检查更新 + 公告，完成后回主线程调用 on_done(state)。

    local_ver: 当前版本号（不含 V，如 '1.00'）
    on_done:  回调，在后台线程调用；调用方自行调度回主线程
    lang:     公告优先取该语言文案（announce.json 的 lang 字段），缺省回退默认 title/body
    """
    def _work():
        st = UpdateState()
        st.checked_at = time.time()
        # 1) 最新版本
        rel = _http_get_json(_RELEASES_API)
        if rel and isinstance(rel, dict) and rel.get("tag_name"):
            st.latest_tag = rel.get("tag_name")
            st.latest_ver = _strip_v(rel.get("tag_name"))
            st.latest_body = rel.get("body") or ""
            st.has_update = is_newer(st.latest_ver, local_ver)
        else:
            st.error = "no_release"
        # 2) 公告
        if want_announce:
            ann = _http_get_json(_ANNOUNCE_RAW)
            if ann and isinstance(ann, dict):
                st.announce = ann
                # 优先取当前语言文案，缺省回退默认字段
                title = ann.get("title") or ""
                body = ann.get("body") or ""
                lang_map = ann.get("lang") or {}
                if isinstance(lang_map, dict):
                    cur = lang_map.get(lang)
                    if isinstance(cur, dict):
                        title = cur.get("title") or title
                        body = cur.get("body") or body
                st.announce_title = title
                st.announce_body = body
        if not st.error and st.latest_ver is None:
            st.error = "network"
        try:
            on_done(st)
        except Exception:
            pass

    threading.Thread(target=_work, daemon=True).start()
