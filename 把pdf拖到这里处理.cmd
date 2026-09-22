@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (
  echo Drag a PDF file onto this script to process it.
  echo.
  pause >nul
  exit /b
)
"%LOCALAPPDATA%\Python\bin\python.exe" -X utf8 -m app.cli once --force "%~1"
echo.
pause >nul
