# 水洗唛打印助手 — 卸载清理（供安装包卸载调用，也可手动运行）
# 只清理「指向本目录」的组件：后台服务进程 / 开机自启任务 / 虚拟打印机。
# 若这些组件指向其它安装目录，则保持不变（避免误伤其它安装）。
param([string]$Dir = $PSScriptRoot, [switch]$Silent)
$ErrorActionPreference = 'Continue'
$dir = [System.IO.Path]::GetFullPath($Dir).TrimEnd('\')

function Say($m) { Write-Host $m }

# 1) 停止后台服务（仅当进程属于本目录：命令行或可执行文件路径包含本目录）
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
  $_.Name -match '^(python|pythonw)' -and
  $_.CommandLine -and ($_.CommandLine -match 'app\.console|app\.cli watch') -and (
    ($_.CommandLine -like ('*' + $dir + '*')) -or
    ($_.ExecutablePath -and ($_.ExecutablePath -like ($dir + '\*')))
  )
} | ForEach-Object {
  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  Say ('已停止后台进程 PID ' + $_.ProcessId)
}

# 2) 删除开机自启任务（仅当任务指向本目录）
try {
  $t = Get-ScheduledTask -TaskName '水洗唛打印助手' -ErrorAction Stop
  $wd = ''
  foreach ($a in $t.Actions) { if ($a.WorkingDirectory) { $wd = $a.WorkingDirectory } }
  if ($wd -and ([System.IO.Path]::GetFullPath($wd).TrimEnd('\') -ieq $dir)) {
    Unregister-ScheduledTask -TaskName '水洗唛打印助手' -Confirm:$false
    Say '已删除开机自启任务（指向本目录）。'
  } else {
    Say ('跳过开机自启任务（指向：' + $wd + '）')
  }
} catch { Say '未找到开机自启任务（跳过）。' }

# 3) 移除虚拟打印机与端口（仅当打印机端口指向本目录）
try {
  Import-Module PrintManagement -ErrorAction SilentlyContinue
  $p = Get-Printer -Name '水洗唛打印助手' -ErrorAction Stop
  if ($p.PortName -and ($p.PortName -like ('*' + $dir + '*'))) {
    Remove-Printer -Name '水洗唛打印助手' -ErrorAction SilentlyContinue
    Say '已删除虚拟打印机（端口指向本目录）。'
    if (Get-PrinterPort -Name $p.PortName -ErrorAction SilentlyContinue) {
      Remove-PrinterPort -Name $p.PortName -ErrorAction SilentlyContinue
      Say ('已删除端口：' + $p.PortName)
    }
  } else {
    Say ('跳过虚拟打印机（端口指向：' + $p.PortName + '）')
  }
} catch { Say '未找到虚拟打印机（跳过）。' }

if (-not $Silent) { Read-Host '按回车退出' }
