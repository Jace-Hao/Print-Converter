@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在打印 2 张校准唛（第1版顺时针 / 第2版逆时针）...
set "PY=%~dp0runtime\python.exe"
if not exist "%PY%" set "PY=%LOCALAPPDATA%\Python\bin\python.exe"
"%PY%" -X utf8 -m app.cli calibrate
echo.
pause >nul
