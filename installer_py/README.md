# CHEN-V 安装程序（单文件直装）

一个 1.4GB 的 exe，双击即装。**不落临时目录、不重复复制**——直接把包内数据解压
到用户选定的安装目录。

## 交付物

```
dist/CHEN-V_Setup_v1.01.exe      ← 唯一需要分发的文件（1.40 GB）
```

## 结构

```
installer_py/
  ├── bootstrapper/            # 安装程序本体（C# / .NET 4.8 / WinForms）
  │     Program.cs             # 界面 + 解压引擎 + 注册表/快捷方式/卸载器
  │     app.manifest           # requireAdministrator（双击请求 UAC）
  │     icon.png / app.ico     # 内嵌图标
  ├── build_installer.py       # 步骤1：把程序文件组装到 dist/CHEN-V_Setup_v1.01/
  ├── build_installer_sfx.py   # 步骤2：打成单文件 exe（ZIP + 拼接）
  └── installer.py             # （旧）PySide6 向导，现已不使用，保留备查
```

## 单文件原理

```
[安装程序 exe][ZIP 数据][8 字节小端 = ZIP 起始偏移]
```

运行时读末尾 8 字节拿到 ZIP 起点，用 `ZipArchive` + 自定义 `SubStream`
**流式解压到安装目录**，全程只写一遍 2.3GB。

> 关键：不经过 `%TEMP%` 中转。早期版本先解压到临时目录再复制到目标，等于
> 写两遍 2.3GB（还额外占 C 盘），已废弃。

## 安装流程（2 步）

1. 双击 → 立即出窗口，显示默认安装位置 `C:\Program Files\CHEN-V`，可点「更改」
2. 点「开始安装」→ 进度条 → 完成页（可勾选「立即运行」）

装完会：
- 写 `HKLM\...\Uninstall\CHEN-V` 卸载项（控制面板可见）
- 写 `HKLM\Software\CHEN-V` 安装位置（供升级定位）
- 建桌面快捷方式
- 生成卸载脚本 `%LOCALAPPDATA%\CHEN-V\uninstall.bat`（放在安装目录外，
  避免卸载时删到自己锁住）
- 创建 `work`、`logs` 目录
- 跳过 `installer_py/`、`CHEN-V_Setup.exe` 等安装器自身文件

## 打包

```bat
python installer_py\build_installer.py        :: 组装目录（约 42 秒）
python installer_py\build_installer_sfx.py    :: 打单文件（约 55 秒 → 1.40 GB）
```

改过 `bootstrapper/Program.cs` 要先编译：

```bat
cd installer_py\bootstrapper
dotnet build -c Release
```

## 静默安装（脚本/自测用）

```bat
CHEN-V_Setup_v1.01.exe /S:"D:\CHEN-V"
```

退出码 0 成功，日志写 `%TEMP%\chenv_install_error.log`。

## 实测

| 指标 | 数值 |
|---|---|
| 双击到界面 | < 1 秒 |
| 安装 2.3GB（SSD） | 约 21 秒 |
| 包体积 | 1.40 GB |
| C 盘额外占用 | **0**（无临时解压） |

## 踩过的坑

- **MAX_PATH 260**：payload 里 PySide6 的 `.obj` 路径达 257 字符。解压时对超长
  路径加 `\\?\` 前缀（`LP()`），manifest 同时开 `longPathAware`。
- **先解压再复制**：写两遍 2.3GB，慢一倍还白占 C 盘。改为直接解压到目标目录。
- **PySide6 跨线程刷新**：非主线程调 `QTimer.singleShot` 静默失效，进度永远 0%
  （旧 PySide6 向导的致命 bug，也是弃用它的原因之一）。
- **卸载器位置**：放安装目录里会删到自己锁住，必须放 `%LOCALAPPDATA%`。
