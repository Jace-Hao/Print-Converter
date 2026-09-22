# 水洗唛打印助手 — 卸载开机自启（并停止正在运行的后台软件）
$ErrorActionPreference = 'Continue'
try {
  Unregister-ScheduledTask -TaskName '水洗唛打印助手' -Confirm:$false -ErrorAction Stop
  Write-Host '已删除开机自启任务。'
} catch {
  Write-Host ('未找到任务或权限不足：' + $_.Exception.Message)
}
Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|pythonw)' -and $_.CommandLine -match 'app\.console|app\.cli watch' } | ForEach-Object {
  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  Write-Host ('已停止后台进程 PID ' + $_.ProcessId)
}
Write-Host '完成。'
Read-Host '按回车退出'
