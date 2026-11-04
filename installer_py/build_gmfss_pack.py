# -*- coding: utf-8 -*-
"""CHEN-V GMFSS 补充包：单独打包 PyTorch 运行时 + GMFSS 模型。

为什么拆出来：torch 2.11+cu128 解开是 4.4 GB，主安装包只有 2.4 GB。
把它塞进主包，等于让每个用户都多下 4.4 GB，而 GMFSS 只是可选的补帧引擎。

所以补充包就是「主包故意排除的那部分」：
    vrt/python/Lib/site-packages/   除 vapoursynth 之外全部（主包已带 vapoursynth）
    vrt/plugins/gmfss/              模型权重 + 推理代码
    app/gmfss_engine.py 等胶水文件

设计要点：
  * 直接从源码目录打包，不经过 dist 中转 —— 省掉 4.4 GB 的复制和一份磁盘占用。
  * ZIP 条目统一以 CHEN-V_GMFSS_v1.03/ 开头，安装器剥掉第一段再落到目标目录。
  * 打完做一次条目数与 CRC 校验，防止半路写坏。

用法：
    python installer_py/build_gmfss_pack.py
"""

import hashlib
import io
import os
import struct
import sys
import time
import zipfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

VER = "1.03"
PACK_NAME = "CHEN-V_GMFSS_v%s" % VER

BOOT = os.path.join(HERE, "bootstrapper_gmfss", "bin", "Release", "net48",
                    "CHEN-V_GMFSS_Setup.exe")
OUT = os.path.join(ROOT, "dist", "CHEN-V_GMFSS_Setup_v%s.exe" % VER)
TMP_ZIP = os.path.join(ROOT, "dist", "_payload_gmfss_%s.zip" % VER)

COMPRESS_LEVEL = 1        # 1 = 最快；DLL 本身压不动多少，CPU 时间才是瓶颈

# (相对路径, 需要排除的顶层子目录)
INCLUDE_DIRS = [
    ("vrt/python/Lib/site-packages", {"vapoursynth"}),   # 主包已带，不重复
    ("vrt/plugins/gmfss", set()),
]

INCLUDE_FILES = [
    "app/gmfss_engine.py",
    "app/gmfss_setup.py",
    "安装GMFSS组件.bat",
]

README_TEXT = """CHEN-V GMFSS 补充包 v{ver}

这个包补的是 GMFSS 补帧需要的 PyTorch 运行时和模型文件。
主安装包为了控制体积没有带它们，所以 RIFE 装完就能用，GMFSS 要额外装这个。

安装方法
--------
1. 先装好 CHEN-V 主程序（如果还没装）。
2. 双击 CHEN-V_GMFSS_Setup_v{ver}.exe。
3. 点「选择目录」，选中你安装 CHEN-V 的那个文件夹
   （默认装在 C:\\Program Files\\CHEN-V，装在别处就选你那个）。
4. 点「开始安装」，等进度走完。
5. 关掉再重开 CHEN-V，补帧模型下拉框里就会出现
   「GMFSS Fortuna Union（光流·画质）」和「GMFSS Fortuna Union（光流·动漫）」。

安装器会先检查所选目录里有没有 CHEN-V.exe 和 app\\gui_main.py，
选错文件夹会直接拦下来，不会往别的地方乱写。

磁盘占用
--------
释放后约 4.4 GB，全部在你选的 CHEN-V 目录里，
用的是直接写入，不经过 C 盘临时目录，不会额外占一份空间。

怎么卸载
--------
删掉 CHEN-V 目录下的这两个文件夹即可：
    vrt\\plugins\\gmfss
    vrt\\python\\Lib\\site-packages\\torch
程序会自动认不出 GMFSS，退回到 RIFE，不影响其他功能。

关于根目录的「安装GMFSS组件.bat」
----------------------------
那是联网重装用的备用手段（给 vrt\\python 装 pip 和 torch）。
补充包装好之后一般用不到；万一 torch 被误删，可以双击它联网修复。
""".format(ver=VER)


def log(msg=""):
    print(msg, flush=True)


def crc32_of(path):
    crc = 0
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            crc = zlib.crc32(b, crc)
    return crc & 0xFFFFFFFF


def collect():
    """返回 [(绝对路径, 包内相对路径), ...]。"""
    items = []
    skipped = 0

    for rel_dir, drop in INCLUDE_DIRS:
        base = os.path.join(ROOT, rel_dir.replace("/", os.sep))
        if not os.path.isdir(base):
            log("  [错误] 源目录不存在: %s" % rel_dir)
            return None
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            # 排除主包已经带上的顶层子目录（vapoursynth）
            rel_from_base = os.path.relpath(root, base).replace(os.sep, "/")
            if rel_from_base == ".":
                dirs[:] = [d for d in dirs if d not in drop]
                files = [f for f in files if not any(f.startswith(d) for d in drop)]
            for name in files:
                if name.endswith((".pyc", ".pyo")):
                    skipped += 1
                    continue
                src = os.path.join(root, name)
                rel = os.path.relpath(src, ROOT).replace(os.sep, "/")
                items.append((src, rel))

    for rel in INCLUDE_FILES:
        src = os.path.join(ROOT, rel.replace("/", os.sep))
        if os.path.isfile(src):
            items.append((src, rel))
        else:
            log("  [警告] 缺少可选文件: %s" % rel)

    log("  跳过 %d 个字节码文件" % skipped)
    return items


def build_zip(items):
    total = 0
    for src, _rel in items:
        try:
            total += os.path.getsize(src)
        except OSError:
            pass
    log("  待打包 %.2f GB / %d 个文件" % (total / 1024.0 ** 3, len(items)))

    t0 = time.time()
    written = 0
    with zipfile.ZipFile(TMP_ZIP, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=COMPRESS_LEVEL, allowZip64=True) as z:
        # 说明文件放最前面，用户解压/排查时一眼能看到
        z.writestr("%s/GMFSS补充包说明.txt" % PACK_NAME, README_TEXT)

        for i, (src, rel) in enumerate(items, 1):
            z.write(src, "%s/%s" % (PACK_NAME, rel))
            try:
                written += os.path.getsize(src)
            except OSError:
                pass
            if i % 2000 == 0:
                log("    已打包 %d/%d（%.0f%%）…"
                    % (i, len(items), written * 100.0 / max(total, 1)))

    log("  ZIP 完成：%.2f GB，用时 %.0fs"
        % (os.path.getsize(TMP_ZIP) / 1024.0 ** 3, time.time() - t0))


def concat():
    boot_size = os.path.getsize(BOOT)
    log("  拼接启动器 %d 字节 + ZIP 数据…" % boot_size)
    with open(OUT, "wb") as out:
        with open(BOOT, "rb") as b:
            while True:
                chunk = b.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
        with open(TMP_ZIP, "rb") as z:
            while True:
                chunk = z.read(4 << 20)
                if not chunk:
                    break
                out.write(chunk)
        out.write(struct.pack("<q", boot_size))
    os.remove(TMP_ZIP)
    log("  产物：%s（%.2f GB）" % (OUT, os.path.getsize(OUT) / 1024.0 ** 3))


def open_payload_zip(exe_path):
    size = os.path.getsize(exe_path)
    f = open(exe_path, "rb")
    f.seek(-8, os.SEEK_END)
    off = struct.unpack("<q", f.read(8))[0]
    if off <= 0 or off >= size - 8:
        raise RuntimeError("ZIP 偏移无效，文件可能损坏")
    f.seek(off)

    class _Sub(io.RawIOBase):
        def __init__(self, fh, start, length):
            self.f, self.st, self.ln, self.pos = fh, start, length, 0

        def readable(self):
            return True

        def seekable(self):
            return True

        def seek(self, o, w=0):
            self.pos = o if w == 0 else (self.pos + o if w == 1 else self.ln + o)
            return self.pos

        def tell(self):
            return self.pos

        def readinto(self, b):
            remain = self.ln - self.pos
            if remain <= 0:
                return 0
            n = min(len(b), remain)
            self.f.seek(self.st + self.pos)
            data = self.f.read(n)
            b[:len(data)] = data
            self.pos += len(data)
            return len(data)

    return zipfile.ZipFile(io.BufferedReader(_Sub(f, off, size - 8 - off)))


def verify(items):
    """逐条比对包内大小，代码/配置类再比 CRC。"""
    problems = []
    z = open_payload_zip(OUT)
    entries = {i.filename: i for i in z.infolist()}
    log("  包内条目 %d 个（含说明文件）" % len(entries))

    for src, rel in items:
        arc = "%s/%s" % (PACK_NAME, rel)
        e = entries.get(arc)
        if e is None:
            problems.append("缺失: %s" % rel)
            continue
        size = os.path.getsize(src)
        if e.file_size != size:
            problems.append("大小不符: %s（包 %d / 源 %d）" % (rel, e.file_size, size))
            continue
        if src.lower().endswith((".py", ".bat", ".txt", ".json")):
            if crc32_of(src) != e.CRC:
                problems.append("内容不符（CRC）: %s" % rel)

    extra = set(entries) - set("%s/%s" % (PACK_NAME, r) for _s, r in items)
    extra.discard("%s/GMFSS补充包说明.txt" % PACK_NAME)
    if extra:
        problems.append("包内有多余条目 %d 个（示例：%s）"
                        % (len(extra), sorted(extra)[0]))
    return problems, len(items)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(8 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    log("=" * 56)
    log("CHEN-V GMFSS 补充包 v%s" % VER)
    log("=" * 56)

    if not os.path.isfile(BOOT):
        log("[错误] 找不到补充包安装器：%s" % BOOT)
        log("       先编译：cd installer_py\\bootstrapper_gmfss && dotnet build -c Release")
        return 1

    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)

    log("[1/4] 收集文件…")
    items = collect()
    if not items:
        return 1

    log("[2/4] 打包 ZIP…")
    if os.path.exists(TMP_ZIP):
        os.remove(TMP_ZIP)
    build_zip(items)

    log("[3/4] 拼接单文件…")
    concat()

    log("[4/4] 校验包内容…")
    problems, count = verify(items)
    if problems:
        log("  [错误] 发现 %d 处问题：" % len(problems))
        for p in problems[:20]:
            log("      " + p)
        log("")
        log("打包失败：包内文件与源不一致，请勿发布。")
        return 1
    log("  %d 个文件全部一致 ✅" % count)

    log("")
    log("=" * 56)
    log("补充包：%s" % OUT)
    log("大小：%.2f GB" % (os.path.getsize(OUT) / 1024.0 ** 3))
    log("SHA256：%s" % sha256_of(OUT))
    log("=" * 56)
    return 0


if __name__ == "__main__":
    sys.exit(main())
