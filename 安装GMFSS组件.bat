@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
runtime\py311\python.exe app\gmfss_setup.py
echo.
pause
