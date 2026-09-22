@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (
  echo 把 PDF 文件拖到本文件上即可自动处理。
  echo.
  pause >nul
  exit /b
)
set "PY=%~dp0runtime\python.exe"
if not exist "%PY%" set "PY=%LOCALAPPDATA%\Python\bin\python.exe"
"%PY%" -X utf8 -m app.cli once --force "%~1"
echo.
pause >nul
