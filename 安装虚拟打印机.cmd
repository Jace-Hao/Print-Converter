@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 安装虚拟打印机 - 水洗唛打印助手
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo 需要管理员权限，正在请求提升（请在弹出的窗口点击"是"）...
  powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
  exit /b
)
echo 正在安装虚拟打印机「水洗唛打印助手」...
echo.
set "PY=%~dp0runtime\python.exe"
if not exist "%PY%" set "PY=%LOCALAPPDATA%\Python\bin\python.exe"
"%PY%" -X utf8 -m app.vpinstall install
echo.
echo ------------------------------------------------------------
echo 安装完成后：「洗衣管家」打印水洗唛时会自动经该虚拟打印机
echo 进入本工具，完成旋转后输出到标签机（无需其他操作）。
echo ------------------------------------------------------------
pause >nul
