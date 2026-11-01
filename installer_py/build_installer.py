# -*- coding: utf-8 -*-
"""CHEN-V 打包步骤 1：把程序文件同步到 dist/CHEN-V_Setup_v1.01/。

设计要点（踩过的坑）：
  * 不再「先删整个目录再复制」——批量删除会被安全策略拦下，脚本继续往下跑，
    结果 dist 里留着上一次的旧文件，打出来的包就是旧代码。
  * 改成增量同步：按 大小 + 修改时间 判断是否需要复制，只覆盖变化文件。
  * 结束前做一次校验：源码与 dist 的代码/配置文件逐个比对 SHA1，
    不一致直接报错退出（退出码 1），不让旧文件流到下一步。

用法：
    python installer_py/build_installer.py
"""

import hashlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VER = "1.01"
OUT = os.path.join(ROOT, "dist", "CHEN-V_Setup_v%s" % VER)

ROOT_FILES = ["CHEN-V.exe", "命令行.bat", "README.md", "LICENSE", "announce.json"]
DIRS = ["app", "runtime", "models", "vrt", "ffmpeg", "assets", "tools"]
LAUNCHER_FILES = ["CHEN-V_Setup.exe", "CHEN-V_Setup.exe.config"]

# 这些后缀参与逐字节校验（体积小、最容易被改坏或忘记同步）
VERIFY_EXTS = (".py", ".json", ".bat", ".md", ".nsi", ".csproj", ".manifest", ".cs", ".txt")

STALE_LIMIT = 30      # 多余文件逐个删除的上限，超过只告警不删


def log(msg=""):
    print(msg, flush=True)


def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def need_copy(src, dst):
    if not os.path.isfile(dst):
        return True
    try:
        if os.path.getsize(src) != os.path.getsize(dst):
            return True
        return os.path.getmtime(src) > os.path.getmtime(dst) + 1
    except OSError:
        return True


def sync_file(src, dst, stats):
    if not os.path.isfile(src):
        log("  [警告] 源文件缺失: %s" % os.path.relpath(src, ROOT))
        return
    if need_copy(src, dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        stats["copied"] += 1
    else:
        stats["same"] += 1


def sync_tree(src_dir, dst_dir, stats):
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]     # 不打包编译缓存
        rel = os.path.relpath(root, src_dir)
        target_root = dst_dir if rel == "." else os.path.join(dst_dir, rel)
        os.makedirs(target_root, exist_ok=True)
        for name in files:
            if name.endswith((".pyc", ".pyo")):
                continue
            sync_file(os.path.join(root, name), os.path.join(target_root, name), stats)


def find_stale():
    """dist 里有、源码里没有的文件（历史残留）。"""
    stale = []
    for root, _dirs, files in os.walk(OUT):
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, OUT)
            top = rel.split(os.sep)[0]
            if top in DIRS:
                src = os.path.join(ROOT, rel)
            elif rel in ROOT_FILES or rel in LAUNCHER_FILES or rel.startswith("installer_py"):
                src = os.path.join(ROOT, rel)
            else:
                continue
            if not os.path.isfile(src):
                stale.append(rel)
    return stale


def verify():
    """确认 dist 内代码/配置与源码逐字节一致，返回问题列表。"""
    problems = []
    pairs = []
    for rel in ROOT_FILES + LAUNCHER_FILES:
        pairs.append((os.path.join(ROOT, rel), os.path.join(OUT, rel)))
    pairs.append((os.path.join(HERE, "installer.py"),
                  os.path.join(OUT, "installer_py", "installer.py")))

    for d in DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for name in files:
                if not name.lower().endswith(VERIFY_EXTS):
                    continue
                src = os.path.join(root, name)
                if "__pycache__" in src or name.endswith((".pyc", ".pyo")):
                    continue
                pairs.append((src, os.path.join(OUT, os.path.relpath(src, ROOT))))

    for src, dst in pairs:
        if not os.path.isfile(src):
            continue
        if not os.path.isfile(dst):
            problems.append("缺失: %s" % os.path.relpath(dst, OUT))
        elif sha1(src) != sha1(dst):
            problems.append("内容不一致: %s" % os.path.relpath(dst, OUT))
    return problems


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)

    stats = {"copied": 0, "same": 0}
    log("[1/4] 同步根文件…")
    for f in ROOT_FILES + LAUNCHER_FILES:
        sync_file(os.path.join(ROOT, f), os.path.join(OUT, f), stats)
    sync_file(os.path.join(HERE, "installer.py"),
              os.path.join(OUT, "installer_py", "installer.py"), stats)

    log("[2/4] 同步程序目录（增量，未变化的跳过）…")
    for d in DIRS:
        src = os.path.join(ROOT, d)
        if not os.path.isdir(src):
            log("  [警告] 源目录缺失: %s" % d)
            continue
        log("  %s …" % d)
        sync_tree(src, os.path.join(OUT, d), stats)
    log("  复制/更新 %d 个，未变化 %d 个" % (stats["copied"], stats["same"]))

    log("[3/4] 清理历史残留…")
    stale = find_stale()
    if not stale:
        log("  无残留")
    elif len(stale) <= STALE_LIMIT:
        for rel in stale:
            try:
                os.remove(os.path.join(OUT, rel))
                log("  已删除 %s" % rel)
            except OSError as e:
                log("  [警告] 删除失败 %s (%s)" % (rel, e))
    else:
        log("  [警告] 发现 %d 个多余文件，数量过多未自动删除（前 10 个）：" % len(stale))
        for rel in stale[:10]:
            log("      %s" % rel)

    log("[4/4] 校验 dist 与源码一致性…")
    problems = verify()
    if problems:
        log("  [错误] 发现 %d 处不一致：" % len(problems))
        for p in problems[:20]:
            log("      " + p)
        log("")
        log("打包中止：请修正后重试。")
        return 1
    log("  全部一致 ✅")

    log("")
    log("=" * 46)
    log("目录就绪：%s" % OUT)
    log("下一步：python installer_py/build_installer_sfx.py")
    log("=" * 46)
    return 0


if __name__ == "__main__":
    sys.exit(main())
