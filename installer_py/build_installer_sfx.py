# -*- coding: utf-8 -*-
"""把「品牌化启动器 + payload ZIP」拼成单个自解压安装包。

产物结构（字节序）：
    [CHEN-V_Setup.exe 启动器][ZIP 数据][8 字节小端 = ZIP 起始偏移]

运行原理：启动器读自己末尾 8 字节拿到 ZIP 起点，用 ZipArchive 流式解压
到 %TEMP%\\CHEN-V_Setup，然后启动里面的 installer_py 安装向导。

用法：
    python installer_py/build_installer_sfx.py
"""

import os
import struct
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VER = "1.01"

SRC = os.path.join(ROOT, "dist", "CHEN-V_Setup_v%s" % VER)
BOOT = os.path.join(HERE, "bootstrapper", "bin", "Release", "net48", "CHEN-V_Setup.exe")
OUT = os.path.join(ROOT, "dist", "CHEN-V_Setup_v%s.exe" % VER)
TMP_ZIP = os.path.join(ROOT, "dist", "_payload_%s.zip" % VER)

COMPRESS_LEVEL = 1          # 1=最快（磁盘是瓶颈，压缩率收益有限）


def build_zip():
    """把分发目录打成 ZIP，条目路径以 CHEN-V_Setup_v1.01/ 开头。"""
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
        for root, _dirs, files in os.walk(SRC):
            for f in files:
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


def main():
    for p, name in ((SRC, "分发目录"), (BOOT, "启动器")):
        if not os.path.exists(p):
            print("[错误] 找不到%s：%s" % (name, p))
            print("       请先运行 installer_py/build_installer.py，并编译 bootstrapper。")
            return 1

    print("[1/3] 打包 payload 为 ZIP…")
    if os.path.exists(TMP_ZIP):
        os.remove(TMP_ZIP)
    build_zip()

    print("[2/3] 拼接单文件…")
    concat()

    print("[3/3] 完成")
    print("=" * 52)
    print("双击即可安装：%s" % OUT)
    print("=" * 52)
    return 0


if __name__ == "__main__":
    sys.exit(main())
