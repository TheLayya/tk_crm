$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$data = Join-Path $env:TEMP ('TkCRM-no-toolchain-' + [guid]::NewGuid().ToString('N'))
$exe = Join-Path $root 'desktop\runtime\windows-x64\TkCrm.Desktop.exe'
$versionText = Get-Content -LiteralPath (Join-Path $root 'backend\app\version.py') -Raw
if ($versionText -notmatch 'APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"') { throw 'Unable to read APP_VERSION' }
$expectedVersion = $Matches[1]
$savedEnvironment = @{}
foreach ($name in @('PATH', 'PYTHONPATH', 'PYTHONHOME', 'NODE_PATH', 'VIRTUAL_ENV', 'TKCRM_DATA_DIR', 'TKCRM_LEGACY_DATA_DIR', 'TKCRM_UPDATE_READY_FILE', 'WEBVIEW2_USER_DATA_FOLDER', 'TKCRM_URL', 'TKCRM_SERVER_EXE', 'TKCRM_SERVER_DIR', 'TKCRM_STATIC_DIR')) {
  $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$desktop = $null
$server = $null
try {
  New-Item -ItemType Directory -Path $data -Force | Out-Null
  $configuration = "JWT_SECRET=0123456789abcdef0123456789abcdef`nFIELD_ENCRYPTION_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef`nSUPER_ADMIN_PASSWORD=Admin123!`n"
  [IO.File]::WriteAllText((Join-Path $data '.env'), $configuration, [Text.UTF8Encoding]::new($false))
  $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\Wbem"
  Remove-Item Env:PYTHONPATH,Env:PYTHONHOME,Env:NODE_PATH,Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
  Remove-Item Env:TKCRM_URL,Env:TKCRM_SERVER_EXE,Env:TKCRM_SERVER_DIR,Env:TKCRM_STATIC_DIR -ErrorAction SilentlyContinue
  $env:WEBVIEW2_USER_DATA_FOLDER = Join-Path $data 'webview2'
  $env:TKCRM_DATA_DIR = $data
  $env:TKCRM_LEGACY_DATA_DIR = ''
  $readyFile = Join-Path $data 'desktop-ready.json'
  $env:TKCRM_UPDATE_READY_FILE = $readyFile
  $desktop = Start-Process -FilePath $exe -WindowStyle Hidden -PassThru
  $deadline = (Get-Date).AddSeconds(45)
  $ready = $null
  while ($null -eq $ready -and (Get-Date) -lt $deadline) {
    if ($desktop.HasExited) { throw 'Fixture desktop exited before becoming ready' }
    if (Test-Path -LiteralPath $readyFile) {
      try { $ready = Get-Content -LiteralPath $readyFile -Raw | ConvertFrom-Json } catch { }
    }
    if ($null -eq $ready) { Start-Sleep -Milliseconds 250 }
  }
  if ($null -eq $ready) {
    Write-Output "Fixture desktop pid=$($desktop.Id) title=$($desktop.MainWindowTitle)"
    Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $desktop.Id } | Select-Object ProcessId, Name | Format-Table | Out-String | Write-Output
    throw 'Fixture WebView2 did not report a valid ready receipt'
  }
  if ([int]$ready.pid -ne $desktop.Id -or [string]$ready.version -ne $expectedVersion) { throw 'Fixture WebView2 receipt mismatch' }
  if (-not (Test-Path -LiteralPath (Join-Path $env:WEBVIEW2_USER_DATA_FOLDER 'EBWebView') -PathType Container)) { throw 'Fixture WebView2 profile was not isolated' }
  Write-Output "PASS isolated WebView2 profile: $env:WEBVIEW2_USER_DATA_FOLDER"
  $server = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'TkCrm.Server.exe' -and $_.ParentProcessId -eq $desktop.Id }
  if (-not $server) { throw 'Fixture desktop has no owned server' }
  $port = [int]$ready.port
  $connection = Get-NetTCPConnection -OwningProcess $server.ProcessId -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  if (-not $connection) { throw 'Fixture server does not own the health listener' }
  $base = "http://127.0.0.1:$port"
  $health = Invoke-RestMethod "$base/health" -TimeoutSec 3
  if ($health.status -ne 'ok' -or $health.version -ne $expectedVersion) { throw 'Fixture health version mismatch' }
  Write-Output "PASS without toolchain: owned server port=$port version=$($health.version), WebView2 ready"
  $login = Invoke-RestMethod -Method Post -Uri "$base/api/auth/login" -ContentType 'application/json' -Body '{"username":"admin","password":"Admin123!"}'
  $status = Invoke-RestMethod -Uri "$base/api/updates/status" -Headers @{ Authorization = "Bearer $($login.access_token)" }
  if ($status.status -ne 'idle') { throw 'Fixture desktop updater was not initialized' }
  Write-Output 'PASS desktop updater initialized: idle'
  & (Join-Path $PSScriptRoot 'close-fixture-desktop.ps1') -DesktopProcess $desktop
  $deadline = (Get-Date).AddSeconds(10)
  while ((Get-Process -Id $server.ProcessId -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 100 }
  if (Get-Process -Id $server.ProcessId -ErrorAction SilentlyContinue) { throw 'Fixture server remained after normal desktop exit' }
  if (-not (Test-Path -LiteralPath (Join-Path $data 'monitor.db'))) { throw 'Fixture database was not created' }
  Write-Output 'PASS no-toolchain desktop smoke: startup, ready page, updater and normal shutdown'
} finally {
  if ($desktop -and -not $server) {
    $server = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'TkCrm.Server.exe' -and $_.ParentProcessId -eq $desktop.Id }
  }
  if ($desktop -and -not $desktop.HasExited) { Stop-Process -Id $desktop.Id -Force -ErrorAction SilentlyContinue }
  if ($server) { Stop-Process -Id $server.ProcessId -Force -ErrorAction SilentlyContinue }
  foreach ($name in $savedEnvironment.Keys) { [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process') }
  Write-Output "Fixture logs: $data"
}
