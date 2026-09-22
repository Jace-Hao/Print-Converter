@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Printing 2 calibration labels (v1 clockwise / v2 counter-clockwise)...
"%LOCALAPPDATA%\Python\bin\python.exe" -X utf8 -m app.cli calibrate
echo.
pause >nul
