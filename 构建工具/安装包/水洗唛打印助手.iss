; 水洗唛打印助手 — Inno Setup 安装包脚本
; 编译：iscc 水洗唛打印助手.iss    （或运行同目录 build_installer.ps1）
; 产物：..\..\dist\水洗唛打印助手-安装包-v2.1.exe

#define MyAppName "水洗唛打印助手"
#define MyAppVersion "2.1"
#define MyAppPublisher "星期衣精致洗衣"

[Setup]
AppId={{A7C4E3B1-2D6F-47A8-B9C1-5E8D2F4A6B3C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={sd}\水洗唛打印助手
DisableProgramGroupPage=yes
DisableDirPage=no
AllowNoIcons=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputDir=..\..\dist
OutputBaseFilename=水洗唛打印助手-安装包-v2.1
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName}
SetupLogging=yes
VersionInfoVersion=2.1.0.0
VersionInfoDescription={#MyAppName} 安装程序
VersionInfoProductName={#MyAppName}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "vprinter"; Description: "安装虚拟打印机「水洗唛打印助手」（打印链路必需）"; GroupDescription: "推荐选项："; Flags: checkedonce
Name: "autostart"; Description: "设置开机自启（登录后自动在后台运行）"; GroupDescription: "推荐选项："; Flags: checkedonce
Name: "launchapp"; Description: "安装完成后立即启动软件（后台运行）"; GroupDescription: "推荐选项："; Flags: checkedonce
Name: "desktopicon"; Description: "创建桌面快捷方式（打开操作页面）"; GroupDescription: "附加快捷方式："; Flags: checkedonce

[Files]
Source: "..\..\.build\payload\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\水洗唛打印助手\打开操作页面"; Filename: "{app}\打开操作页面.cmd"; WorkingDir: "{app}"
Name: "{autoprograms}\水洗唛打印助手\停止软件"; Filename: "{app}\停止软件.cmd"; WorkingDir: "{app}"
Name: "{autoprograms}\水洗唛打印助手\使用说明（网页版）"; Filename: "{app}\使用说明.html"
Name: "{autoprograms}\水洗唛打印助手\卸载水洗唛打印助手"; Filename: "{uninstallexe}"
Name: "{autodesktop}\打开操作页面"; Filename: "{app}\打开操作页面.cmd"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\runtime\python.exe"; Parameters: "-X utf8 -m app.cli init"; WorkingDir: "{app}"; StatusMsg: "初始化配置…"; Flags: runhidden waituntilterminated
Filename: "{app}\runtime\python.exe"; Parameters: "-X utf8 -m app.vpinstall install"; WorkingDir: "{app}"; StatusMsg: "安装虚拟打印机…"; Flags: runhidden waituntilterminated; Tasks: vprinter
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\安装开机自启.ps1"" -Silent"; WorkingDir: "{app}"; StatusMsg: "设置开机自启…"; Flags: runhidden waituntilterminated; Tasks: autostart
Filename: "{app}\使用说明.html"; Description: "查看使用说明"; Flags: postinstall shellexec nowait skipifsilent unchecked
Filename: "{app}\runtime\pythonw.exe"; Parameters: "-X utf8 -m app.console run"; WorkingDir: "{app}"; Flags: postinstall nowait skipifsilent unchecked; Tasks: launchapp; Description: "立即启动软件（后台运行）"

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\卸载清理.ps1"" -Silent"; Flags: runhidden waituntilterminated
