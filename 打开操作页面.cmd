@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 打开操作页面：若后台服务未运行则自动启动，然后在浏览器中打开操作页面
rem 优先使用随附的独立运行时（安装版），否则用本机 Python
set "PY=%~dp0runtime\python.exe"
if not exist "%PY%" set "PY=%LOCALAPPDATA%\Python\bin\python.exe"
"%PY%" -X utf8 -m app.console open
