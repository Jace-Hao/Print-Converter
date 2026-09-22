@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Label Watcher - keep this window open, close it to stop
echo Starting water-label watcher...
echo (Close this window to stop the watcher)
echo.
"%LOCALAPPDATA%\Python\bin\python.exe" -X utf8 -m app.cli watch
echo.
echo Watcher exited. Press any key to close.
pause >nul
