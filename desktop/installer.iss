#define AppName "TkCRM"
#ifndef AppVersion
  #error "Pass AppVersion from build-installer.ps1"
#endif
#define AppPublisher "TkCRM"
#define AppExeName "TkCrm.Desktop.exe"
#define SourceDir "runtime\windows-x64"
#define OutputDir "build\installer"
#define WebView2Bootstrapper "build\MicrosoftEdgeWebview2Setup.exe"

[Setup]
AppId={{9D5C6B35-5C74-4C21-A2E1-3CB4FBE9DA10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\TkCRM
DefaultGroupName=TkCRM
OutputDir={#OutputDir}
OutputBaseFilename=TkCRM-{#AppVersion}-win-x64-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
MinVersion=10.0.17763
PrivilegesRequired=lowest
WizardStyle=modern
SetupIconFile=assets\tkcrm.ico
UninstallDisplayIcon={app}\{#AppExeName}

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#WebView2Bootstrapper}"; Flags: dontcopy

[Icons]
Name: "{autoprograms}\TkCRM"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\TkCRM"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch TkCRM"; Flags: nowait postinstall skipifsilent

[Code]
function HasRuntime(Root: Integer): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(Root, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version)
    and (Version <> '') and (Version <> '0.0.0.0');
end;

function IsWebView2Installed(): Boolean;
begin
  Result := HasRuntime(HKLM32) or HasRuntime(HKCU32);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitCode: Integer;
begin
  Result := '';
  if IsWebView2Installed() then Exit;
  ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
  if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
    Result := '无法启动 WebView2 Runtime 安装程序，请重试。'
  else if (ExitCode <> 0) or not IsWebView2Installed() then
    Result := 'WebView2 Runtime 安装未完成，请检查网络连接后重试。错误码：' + IntToStr(ExitCode);
end;
