# -*- coding: utf-8 -*-
"""把「品牌化启动器 + payload ZIP」拼成单个自解压安装包。

产物结构（字节序）：
    [CHEN-V_Setup.exe 启动器][ZIP 数据][8 字节小端 = ZIP 起始偏移]

运行原理：启动器读自己末尾 8 字节拿到 ZIP 起点，用 ZipArchive 流式解压
到 %TEMP%\\CHEN-V_Setup，然后启动里面的 installer_py 安装向导。

用法：
    python installer_py/build_installer_sfx.py
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
VER = "1.02"

SRC = os.path.join(ROOT, "dist", "CHEN-V_Setup_v%s" % VER)
BOOT = os.path.join(HERE, "bootstrapper", "bin", "Release", "net48", "CHEN-V_Setup.exe")
OUT = os.path.join(ROOT, "dist", "CHEN-V_Setup_v%s.exe" % VER)
TMP_ZIP = os.path.join(ROOT, "dist", "_payload_%s.zip" % VER)

COMPRESS_LEVEL = 1          # 1=最快（磁盘是瓶颈，压缩率收益有限）


def build_zip():
    """把分发目录打成 ZIP，条目路径以 CHEN-V_Setup_v1.02/ 开头。"""
    total = 0
    for root, _dirs, files in os.walk(SRC):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except Exception:
                pass
    print("  待打包 %.2f GB" % (total / 1024.0 ** 3))

    n = 0
    written = 0
    t0 = time.time()
    with zipfile.ZipFile(TMP_ZIP, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=COMPRESS_LEVEL, allowZip64=True) as z:
        for root, dirs, files in os.walk(SRC):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                if f.endswith((".pyc", ".pyo")):
                    continue
                src = os.path.join(root, f)
                rel = os.path.relpath(src, SRC).replace(os.sep, "/")
                arc = "CHEN-V_Setup_v%s/%s" % (VER, rel)
                z.write(src, arc)
                n += 1
                try:
                    written += os.path.getsize(src)
                except Exception:
                    pass
                if n % 3000 == 0:
                    print("    已打包 %d 个文件… (%.0f%%)"
                          % (n, written * 100.0 / max(total, 1)), flush=True)
    print("  ZIP 完成：%d 个文件，%.2f GB，用时 %.0fs"
          % (n, os.path.getsize(TMP_ZIP) / 1024.0 ** 3, time.time() - t0))
    return n


def concat():
    boot_size = os.path.getsize(BOOT)
    print("  拼接启动器 %d 字节 + ZIP 数据…" % boot_size)
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
    print("  产物：%s（%.2f GB）" % (OUT, os.path.getsize(OUT) / 1024.0 ** 3))


def open_payload_zip(exe_path):
    """打开 exe 末尾拼接的 ZIP（用于校验包内容）。"""
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


def verify_package():
    """校验 exe 内的 payload 与 dist 源码一致（防止打进旧文件）。

    只校验「会真正安装到用户机器」的文件：安装器会跳过 installer_py/
    与 CHEN-V_Setup.exe* 这些安装器自身文件，它们不影响用户实际运行的程序。
    """
    problems = []
    z = open_payload_zip(OUT)
    entries = {i.filename: i for i in z.infolist()}

    def ignored(rel):
        return (rel.startswith("installer_py/")
                or rel.startswith("CHEN-V_Setup.exe")
                or rel.startswith("卸载CHEN-V.bat")
                or "__pycache__/" in rel
                or rel.endswith((".pyc", ".pyo")))

    expected = []
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if name.endswith((".pyc", ".pyo")):
                continue
            src = os.path.join(root, name)
            rel = os.path.relpath(src, SRC).replace(os.sep, "/")
            if ignored(rel):
                continue
            expected.append(("CHEN-V_Setup_v%s/%s" % (VER, rel), src))

    counted = [v for k, v in entries.items()
               if not ignored(k.split("/", 1)[-1])]
    if len(counted) != len(expected):
        problems.append("文件数不符：包内 %d / 源码 %d" % (len(counted), len(expected)))

    # 所有文件比对大小；代码/配置类再比对 CRC32
    for arc, src in expected:
        e = entries.get(arc)
        if e is None:
            problems.append("包内缺失: %s" % arc)
            continue
        size = os.path.getsize(src)
        if e.file_size != size:
            problems.append("大小不符: %s（包 %d / 源 %d）" % (arc, e.file_size, size))
            continue
        if src.lower().endswith((".py", ".json", ".bat", ".md", ".txt", ".nsi")):
            crc = 0
            with open(src, "rb") as f:
                while True:
                    b = f.read(1 << 20)
                    if not b:
                        break
                    crc = zlib.crc32(b, crc)
            if (crc & 0xFFFFFFFF) != e.CRC:
                problems.append("内容不符（CRC）: %s" % arc)
    return problems, len(expected)


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
    for p, name in ((SRC, "分发目录"), (BOOT, "启动器")):
        if not os.path.exists(p):
            print("[错误] 找不到%s：%s" % (name, p))
            print("       请先运行 installer_py/build_installer.py，并编译 bootstrapper。")
            return 1

    print("[1/4] 打包 payload 为 ZIP…")
    if os.path.exists(TMP_ZIP):
        os.remove(TMP_ZIP)
    build_zip()

    print("[2/4] 拼接单文件…")
    concat()

    print("[3/4] 校验包内容与源码一致…")
    problems, count = verify_package()
    if problems:
        print("  [错误] 发现 %d 处问题：" % len(problems))
        for p in problems[:20]:
            print("      " + p)
        print("")
        print("打包失败：exe 内的文件与源码不一致，请勿发布。")
        return 1
    print("  %d 个文件全部一致 ✅" % count)

    print("[4/4] 完成")
    print("=" * 56)
    print("双击即可安装：%s" % OUT)
    print("大小：%d 字节" % os.path.getsize(OUT))
    print("SHA256：%s" % sha256_of(OUT))
    print("=" * 56)
    return 0


if __name__ == "__main__":
    sys.exit(main())
