@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 卸载虚拟打印机 - 水洗唛打印助手
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo 需要管理员权限，正在请求提升（请在弹出的窗口点击"是"）...
  powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
  exit /b
)
echo 正在卸载虚拟打印机「水洗唛打印助手」...
echo.
set "PY=%~dp0runtime\python.exe"
if not exist "%PY%" set "PY=%LOCALAPPDATA%\Python\bin\python.exe"
"%PY%" -X utf8 -m app.vpinstall uninstall
echo.
pause >nul
