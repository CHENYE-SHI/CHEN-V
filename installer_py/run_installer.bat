@echo off
rem CHEN-V 自研安装器引导（开发/调试用）
rem 用项目自带的 runtime 跑 installer.py，无需系统 Python
chcp 65001 >nul
setlocal
set "RUNTIME=%~dp0..\runtime\py311\pythonw.exe"
set "SCRIPT=%~dp0installer.py"
if not exist "%RUNTIME%" (
    echo 找不到运行时：%RUNTIME%
    pause
    exit /b 1
)
"%RUNTIME%" "%SCRIPT%"
endlocal
