# 水洗唛打印助手 — 安装包构建脚本
# 功能：组装 payload（程序文件 + 内嵌 Python 运行时）→ 调用 Inno Setup 编译安装包。
# 用法（在任意目录运行）：
#   powershell -ExecutionPolicy Bypass -File "构建工具\安装包\build_installer.ps1"
# 可选参数：
#   -RuntimeFrom <目录>   复用已构建好的运行时（跳过下载）
#   -SkipRuntime          跳过运行时准备（要求 .build\payload\runtime 已存在）
#   -Iscc <路径>          指定 ISCC.exe（默认 C:\Program Files (x86)\Inno Setup 6\ISCC.exe）
# 输出：dist\水洗唛打印助手-安装包-v2.1.exe
param(
  [string]$RuntimeFrom = '',
  [switch]$SkipRuntime,
  [string]$Iscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
  [string]$PyEmbedUrl = 'https://www.python.org/ftp/python/3.14.7/python-3.14.7-embed-amd64.zip'
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = [System.IO.Path]::GetFullPath((Join-Path $here '..\..'))
$build = Join-Path $root '.build'
$payload = Join-Path $build 'payload'

Write-Host '[1/4] 组装程序文件 ->' $payload
if (Test-Path $payload) { Remove-Item $payload -Recurse -Force }
New-Item -ItemType Directory -Force -Path $payload | Out-Null
robocopy $root $payload /E /XD '.git' '.build' 'dist' 'backup' 'out' 'spool' 'docs_build' '开发工具' '文档素材' 'inbox' '构建工具' /XF '.gitignore' /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -gt 7) { throw ('robocopy 失败: ' + $LASTEXITCODE) }

$runtime = Join-Path $payload 'runtime'
Write-Host '[2/4] 准备独立运行时'
if ($RuntimeFrom) {
  robocopy $RuntimeFrom $runtime /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
  if ($LASTEXITCODE -gt 7) { throw ('robocopy runtime 失败: ' + $LASTEXITCODE) }
} elseif (-not $SkipRuntime) {
  $dl = Join-Path $build 'dl'
  New-Item -ItemType Directory -Force -Path $dl, $runtime | Out-Null
  $zip = Join-Path $dl 'py-embed.zip'
  if (-not (Test-Path $zip)) { curl.exe -sS -L --fail -o $zip $PyEmbedUrl }
  Expand-Archive -Path $zip -DestinationPath $runtime -Force
  $pth = Get-ChildItem $runtime -Filter '*._pth' | Select-Object -First 1
  $zipn = (Get-ChildItem $runtime -Filter 'python3*.zip' | Select-Object -First 1).Name
  @"
$zipn
.
..
Lib\site-packages
import site
"@ | Set-Content -Path $pth.FullName -Encoding ascii
  curl.exe -sS -L --fail -o (Join-Path $dl 'get-pip.py') 'https://bootstrap.pypa.io/get-pip.py'
  & (Join-Path $runtime 'python.exe') (Join-Path $dl 'get-pip.py') --no-warn-script-location
  & (Join-Path $runtime 'python.exe') -m pip install --no-warn-script-location --disable-pip-version-check --no-cache-dir --only-binary :all: pymupdf pillow pywin32
} else {
  if (-not (Test-Path (Join-Path $runtime 'python.exe'))) { throw '未找到 .build\payload\runtime，且指定了 -SkipRuntime' }
}

# 归一化 _pth（复用运行时也重写一遍，确保包含 .. 以便导入 app 包）
$pth = Get-ChildItem $runtime -Filter '*._pth' | Select-Object -First 1
$zipn = (Get-ChildItem $runtime -Filter 'python3*.zip' | Select-Object -First 1).Name
@"
$zipn
.
..
Lib\site-packages
import site
"@ | Set-Content -Path $pth.FullName -Encoding ascii

& (Join-Path $runtime 'python.exe') -X utf8 -c "import pymupdf, PIL, win32ui, win32print; print('runtime deps OK')"

Write-Host '[3/4] 规范化 config.json'
& (Join-Path $runtime 'python.exe') -X utf8 -c "import json,sys; p=sys.argv[1]; d=json.load(open(p,encoding='utf-8')); d.setdefault('capture',{})['slot_file']='spool\\capture.pdf'; json.dump(d,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2); print('config normalized')" (Join-Path $payload 'config.json')

Write-Host '[4/4] 编译安装包 (Inno Setup)'
if (-not (Test-Path $Iscc)) { throw ('未找到 Inno Setup: ' + $Iscc) }
& $Iscc (Join-Path $here '水洗唛打印助手.iss')
if ($LASTEXITCODE -ne 0) { throw ('ISCC 失败: ' + $LASTEXITCODE) }

Write-Host ('完成：' + (Join-Path $root 'dist'))
