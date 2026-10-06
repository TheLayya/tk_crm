$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$versionText = Get-Content -LiteralPath (Join-Path $root "backend\app\version.py") -Raw
if ($versionText -notmatch 'APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"') { throw "Unable to read APP_VERSION" }
$version = $Matches[1]
$appKey = "9D5C6B35-5C74-4C21-A2E1-3CB4FBE9DA10"
foreach ($registryRoot in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')) {
  if (Get-ChildItem -LiteralPath $registryRoot -ErrorAction SilentlyContinue | Where-Object PSChildName -like "*$appKey*") { throw "Existing TkCRM installation found; refusing isolated install test" }
}
if (Get-Process TkCrm.Desktop,TkCrm.Server,TkCrm.Updater -ErrorAction SilentlyContinue) { throw "Close TkCRM before running installer smoke" }
$fixture = Join-Path $env:TEMP ("TkCRM-installer-smoke-" + [guid]::NewGuid().ToString("N"))
$installation = Join-Path $fixture ((0x4E2D,0x6587,0x5B89,0x88C5,0x76EE,0x5F55 | ForEach-Object { [char]$_ }) -join "")
$data = Join-Path $fixture ((0x9694,0x79BB,0x6570,0x636E | ForEach-Object { [char]$_ }) -join "")
$runtime = Join-Path $root "desktop\runtime\windows-x64"
$setup = Join-Path $root ("desktop\build\installer\TkCRM-{0}-win-x64-setup.exe" -f $version)
New-Item -ItemType Directory -Path $data -Force | Out-Null
$markers = @{ ".env" = "JWT_SECRET=0123456789abcdef0123456789abcdef`nFIELD_ENCRYPTION_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef`nSUPER_ADMIN_PASSWORD=Admin123!`n"; "fixture-only.txt" = "isolated data marker" }
foreach ($name in $markers.Keys) { [IO.File]::WriteAllText((Join-Path $data $name), $markers[$name]) }
$uninstaller = Join-Path $installation "unins000.exe"
$desktopProcess = $null
$serverProcess = $null
$savedDataDir = $env:TKCRM_DATA_DIR
$savedReadyFile = $env:TKCRM_UPDATE_READY_FILE
$savedOverrides = @{}
foreach ($name in @('WEBVIEW2_USER_DATA_FOLDER', 'TKCRM_URL', 'TKCRM_SERVER_EXE', 'TKCRM_SERVER_DIR', 'TKCRM_STATIC_DIR')) {
  $savedOverrides[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$databaseHash = $null
try {
  $arguments = @("/CURRENTUSER", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOICONS", "/TASKS=", ('/DIR="' + $installation + '"'), ('/LOG="' + (Join-Path $fixture "install.log") + '"'))
  $process = Start-Process -FilePath $setup -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
  if ($process.ExitCode -ne 0) { throw "Installer failed: $($process.ExitCode); logs: $fixture" }
  $files = @(Get-ChildItem -LiteralPath $runtime -Recurse -File)
  foreach ($file in $files) {
    $relative = $file.FullName.Substring($runtime.Length).TrimStart('\')
    $installedFile = Join-Path $installation $relative
    if (-not (Test-Path -LiteralPath $installedFile -PathType Leaf)) { throw "Installed file missing: $relative" }
    if ((Get-FileHash -LiteralPath $file.FullName).Hash -ne (Get-FileHash -LiteralPath $installedFile).Hash) { throw "Installed file differs: $relative" }
  }
  Write-Output "PASS installed payload parity: $($files.Count) files; fixture=$fixture"
  $env:TKCRM_DATA_DIR = $data
  $env:WEBVIEW2_USER_DATA_FOLDER = Join-Path $fixture 'webview2'
  Remove-Item Env:TKCRM_URL,Env:TKCRM_SERVER_EXE,Env:TKCRM_SERVER_DIR,Env:TKCRM_STATIC_DIR -ErrorAction SilentlyContinue
  $readyFile = Join-Path $fixture "desktop-ready.json"
  $env:TKCRM_UPDATE_READY_FILE = $readyFile
  $expectedVersion = $version
  $desktopProcess = Start-Process -FilePath (Join-Path $installation "TkCrm.Desktop.exe") -WindowStyle Hidden -PassThru
  Start-Sleep -Seconds 12
  $serverProcess = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "TkCrm.Server.exe" -and $_.ParentProcessId -eq $desktopProcess.Id }
  $port = $null
  $health = ""
  if ($serverProcess) {
    $connection = Get-NetTCPConnection -OwningProcess $serverProcess.ProcessId -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($connection) {
      $port = $connection.LocalPort
      try { $health = Invoke-RestMethod ("http://127.0.0.1:{0}/health" -f $port) -TimeoutSec 2 | ConvertTo-Json -Compress } catch { }
    }
  }
  if (-not $serverProcess -or $health -notlike ('*"status":"ok"*') -or $health -notlike ('*"version":"' + $expectedVersion + '"*')) { throw "Installed desktop startup failed: port=$port health=$health; fixture=$fixture" }
  Write-Output "PASS installed desktop startup: port=$port health=$health"
  $readyDeadline = (Get-Date).AddSeconds(15)
  $ready = $null
  while ($null -eq $ready -and (Get-Date) -lt $readyDeadline) {
    if (Test-Path -LiteralPath $readyFile) {
      try { $ready = Get-Content -LiteralPath $readyFile -Raw | ConvertFrom-Json } catch { }
    }
    if ($null -eq $ready) { Start-Sleep -Milliseconds 250 }
  }
  if ($null -eq $ready) { throw "Installed WebView2 page did not report a valid ready receipt; fixture=$fixture" }
  if ([int]$ready.port -ne [int]$port -or [string]$ready.version -ne $expectedVersion -or [int]$ready.pid -ne $desktopProcess.Id) { throw "Installed WebView2 ready receipt mismatch: $($ready | ConvertTo-Json -Compress)" }
  if (-not (Test-Path -LiteralPath (Join-Path $env:WEBVIEW2_USER_DATA_FOLDER 'EBWebView') -PathType Container)) { throw 'Installed WebView2 profile was not isolated' }
  Write-Output "PASS isolated WebView2 profile: $env:WEBVIEW2_USER_DATA_FOLDER"
  Write-Output "PASS installed WebView2 navigation: ready port=$($ready.port) version=$($ready.version)"
  & (Join-Path $PSScriptRoot 'close-fixture-desktop.ps1') -DesktopProcess $desktopProcess
  Start-Sleep -Seconds 2
  if (Get-Process -Id $serverProcess.ProcessId -ErrorAction SilentlyContinue) { throw "Installed server remains after desktop exit" }
  $databaseHash = (Get-FileHash -LiteralPath (Join-Path $data "monitor.db")).Hash
  Write-Output "PASS installed desktop shutdown: desktop and owned server exited normally"
  $desktopProcess = $null
  $serverProcess = $null
} finally {
  if ($desktopProcess -and -not $serverProcess) {
    $serverProcess = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'TkCrm.Server.exe' -and $_.ParentProcessId -eq $desktopProcess.Id }
  }
  if ($desktopProcess -and -not $desktopProcess.HasExited) { Stop-Process -Id $desktopProcess.Id -Force -ErrorAction SilentlyContinue }
  if ($serverProcess) { Stop-Process -Id $serverProcess.ProcessId -Force -ErrorAction SilentlyContinue }
  if ($null -eq $savedDataDir) { Remove-Item Env:TKCRM_DATA_DIR -ErrorAction SilentlyContinue } else { $env:TKCRM_DATA_DIR = $savedDataDir }
  if ($null -eq $savedReadyFile) { Remove-Item Env:TKCRM_UPDATE_READY_FILE -ErrorAction SilentlyContinue } else { $env:TKCRM_UPDATE_READY_FILE = $savedReadyFile }
  foreach ($name in $savedOverrides.Keys) { [Environment]::SetEnvironmentVariable($name, $savedOverrides[$name], 'Process') }
  if (Test-Path -LiteralPath $uninstaller) {
    $process = Start-Process -FilePath $uninstaller -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART" -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Uninstaller failed: $($process.ExitCode); fixture=$fixture" }
  }
}
if (Test-Path -LiteralPath (Join-Path $installation "TkCrm.Desktop.exe")) { throw "Desktop executable remains after uninstall" }
if (-not (Test-Path -LiteralPath (Join-Path $data "monitor.db") -PathType Leaf)) { throw "Database was not created in isolated data directory" }
if ((Get-FileHash -LiteralPath (Join-Path $data "monitor.db")).Hash -ne $databaseHash) { throw "Database changed during uninstall" }
foreach ($name in $markers.Keys) { if ([IO.File]::ReadAllText((Join-Path $data $name)) -ne $markers[$name]) { throw "Data marker changed: $name" } }
Write-Output "PASS isolated installer/uninstaller: payload removed, sibling data markers preserved"
