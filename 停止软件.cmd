@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在停止「水洗唛打印助手」后台服务...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'app\.console|app\.cli watch' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo.
echo 已停止。需要再次使用请双击「打开操作页面.cmd」。
pause >nul
