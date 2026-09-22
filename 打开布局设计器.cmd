@echo off
chcp 65001 >nul
cd /d "%~dp0"
start "" "%LOCALAPPDATA%\Python\bin\pythonw.exe" -X utf8 "%~dp0app\designer.py"
