@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 打开操作页面：若后台服务未运行则自动启动，然后在浏览器中打开操作页面
"%LOCALAPPDATA%\Python\bin\python.exe" -X utf8 -m app.console open
