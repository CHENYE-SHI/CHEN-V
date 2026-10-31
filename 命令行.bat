@echo off
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0runtime\py311\python.exe" "%~dp0app\cli.py" %*
echo.
pause
