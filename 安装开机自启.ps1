# 水洗唛打印助手 — 安装开机自启（登录后在后台运行监视）
# 用法：右键本文件 → 使用 PowerShell 运行；如提示权限不足，请以管理员身份运行。
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonw = Join-Path $env:LOCALAPPDATA 'Python\bin\pythonw.exe'
if (-not (Test-Path $pythonw)) { Write-Host "找不到 pythonw.exe：$pythonw"; Read-Host '按回车退出'; exit 1 }

$cli = Join-Path $root 'app\cli.py'
$action  = New-ScheduledTaskAction -Execute $pythonw -Argument ('-X utf8 "' + $cli + '" watch')
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
try {
  Register-ScheduledTask -TaskName '水洗唛打印助手' -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
  Start-ScheduledTask -TaskName '水洗唛打印助手'
  Write-Host '已安装开机自启，并已立即启动监视。'
} catch {
  Write-Host ('安装失败：' + $_.Exception.Message)
  Write-Host '提示：请以管理员身份运行本脚本后重试。'
}
Read-Host '按回车退出'
