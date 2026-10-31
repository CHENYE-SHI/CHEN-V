; ============================================================
; CHEN-V 安装脚本（NSIS 3.x，Unicode）
; 视频补帧 + 超分增强工具
; ============================================================

; --- 基础设置 ---
Unicode True
RequestExecutionLevel admin          ; 完整包约 3.3GB，建议管理员权限（写 Program Files）
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"

; --- 程序元信息 ---
!define APP_NAME "CHEN-V"
!define APP_VERSION "1.01"
!define APP_PUBLISHER "辰师"
!define APP_EXE "CHEN-V.exe"
!define APP_URL "https://github.com/CHENYE-SHI/CHEN-V"

; --- 安装包元信息 ---
Name "${APP_NAME}"
OutFile "CHEN-V_Setup_v${APP_VERSION}.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "Software\${APP_NAME}" "InstallDir"

; --- 压缩（非 SOLID + LZMA；SOLID 模式会触发 NSIS 32 位编译器 2GB mmap 越界，不能用）---
SetCompressor lzma
SetCompressorDictSize 32

; --- 界面美化素材 ---
!define MUI_ICON "..\app\icon.ico"
!define MUI_UNICON "..\app\icon.ico"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "assets\header.bmp"
!define MUI_HEADERIMAGE_RIGHT
!define MUI_WELCOMEFINISHPAGE_BITMAP "assets\welcome.bmp"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_NOAUTOCLOSE
!define MUI_UNFINISHPAGE_NOAUTOCLOSE

; --- 页面 ---
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; --- 语言 ---
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "TradChinese"

; ============================================================
; 安装段
; ============================================================
Section "主程序" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"

  ; 写入安装目录到注册表（供卸载和后续升级定位）
  WriteRegStr HKLM "Software\${APP_NAME}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "Software\${APP_NAME}" "Version" "${APP_VERSION}"

  ; --- 核心文件 ---
  File "..\CHEN-V.exe"
  File "..\命令行.bat"
  File "..\README.md"
  File "..\LICENSE"
  File "..\announce.json"

  ; --- app 源码目录 ---
  SetOutPath "$INSTDIR\app"
  File /r "..\app\*.py"
  File "..\app\icon.ico"
  File "..\app\icon.png"
  ; presets 目录（若存在）
  SetOutPath "$INSTDIR\app\presets"
  File /nonfatal "..\app\presets\*.json"

  ; --- 静态素材 ---
  SetOutPath "$INSTDIR\assets"
  File /nonfatal "..\assets\join_group.jpg"
  File /nonfatal "..\assets\support_wechat.png"
  File /nonfatal "..\assets\support_alipay.jpg"

  ; --- 运行时（Python 3.11）---
  SetOutPath "$INSTDIR\runtime"
  File /r "..\runtime\*"

  ; --- 模型 ---
  SetOutPath "$INSTDIR\models"
  File /r "..\models\*"

  ; --- VapourSynth 运行时 ---
  SetOutPath "$INSTDIR\vrt"
  File /r "..\vrt\*"

  ; --- ffmpeg ---
  SetOutPath "$INSTDIR\ffmpeg"
  File /r "..\ffmpeg\*"

  ; --- 工具 ---
  SetOutPath "$INSTDIR\tools"
  File /r "..\tools\*"

  ; --- 运行期目录（空目录占位）---
  CreateDirectory "$INSTDIR\work"
  CreateDirectory "$INSTDIR\logs"

  ; --- 桌面快捷方式（仅桌面）---
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\app\icon.ico"

  ; --- 卸载信息 ---
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                   "DisplayName" "${APP_NAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                   "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                   "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                   "DisplayIcon" "$INSTDIR\app\icon.ico"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                   "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                   "URLInfoAbout" "${APP_URL}"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                   "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                   "NoRepair" 1

  ; --- 估算占用（供控制面板显示，3.3GB 约 3543348019 字节）---
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
                   "EstimatedSize" 3460304
SectionEnd

; ============================================================
; 卸载段
; ============================================================
Section "Uninstall"
  ; 删除桌面快捷方式
  Delete "$DESKTOP\${APP_NAME}.lnk"

  ; 删除注册表
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
  DeleteRegKey HKLM "Software\${APP_NAME}"

  ; 删除安装目录（含所有文件）
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\runtime"
  RMDir /r "$INSTDIR\models"
  RMDir /r "$INSTDIR\vrt"
  RMDir /r "$INSTDIR\ffmpeg"
  RMDir /r "$INSTDIR\tools"
  RMDir /r "$INSTDIR\assets"
  RMDir /r "$INSTDIR\work"
  RMDir /r "$INSTDIR\logs"

  Delete "$INSTDIR\${APP_EXE}"
  Delete "$INSTDIR\命令行.bat"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\LICENSE"
  Delete "$INSTDIR\announce.json"
  Delete "$INSTDIR\uninstall.exe"

  RMDir "$INSTDIR"
SectionEnd
