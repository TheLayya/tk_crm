param(
  [Parameter(Mandatory = $true)][string]$ManifestPath,
  [string]$OldInstaller = '',
  [string]$NewUpdater = ''
)

# Production updater entry + real GitHub HTTPS asset. This does not click the old UI.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$release = Get-Content -LiteralPath (Resolve-Path -LiteralPath $ManifestPath).Path -Raw -Encoding utf8 | ConvertFrom-Json
$version = [string]$release.version
if ($version -notmatch '^\d+\.\d+\.\d+$' -or [version]$version -le [version]'1.1.15') { throw 'Expected a newer release than 1.1.15' }
$packageUrl = "https://github.com/TheLayya/tk_crm/releases/download/v$version/TkCRM-$version-win-x64-setup.exe"
if ([string]$release.windows_package_url -cne $packageUrl -or [string]$release.windows_sha256 -cnotmatch '^[a-f0-9]{64}$') { throw 'Manifest must point to the exact trusted GitHub Windows asset with SHA-256' }
if (-not $OldInstaller) { $OldInstaller = Join-Path $root 'desktop\build\installer\TkCRM-1.1.15-win-x64-setup.exe' }
if (-not $NewUpdater) { $NewUpdater = Join-Path $root 'desktop\runtime\windows-x64\TkCrm.Updater.exe' }
$python = Join-Path $root 'backend\.venv312\Scripts\python.exe'
foreach ($path in @($OldInstaller, $NewUpdater, $python)) {
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing online update input: $path" }
}
if ((Get-FileHash -LiteralPath $OldInstaller -Algorithm SHA256).Hash.ToLowerInvariant() -ne '24c791f67103ca59c42be73b02a3892366f9a618d4424cd93ce009ac2b6e631a') { throw 'Historical 1.1.15 installer fingerprint differs' }
$appKey = '9D5C6B35-5C74-4C21-A2E1-3CB4FBE9DA10'
foreach ($registryRoot in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall','HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')) {
  if (Get-ChildItem -LiteralPath $registryRoot -ErrorAction SilentlyContinue | Where-Object PSChildName -like "*$appKey*") { throw 'Existing TkCRM installation found; refusing isolated online update' }
}
if (Get-Process TkCrm.Desktop,TkCrm.Server,TkCrm.Updater -ErrorAction SilentlyContinue) { throw 'Close TkCRM before online update smoke' }

$fixture = Join-Path $env:TEMP ('TkCRM-online-update-' + [guid]::NewGuid().ToString('N'))
$installation = Join-Path $fixture 'old-install'
$data = Join-Path $fixture 'user-data'
$updates = Join-Path $fixture 'updater'
New-Item -ItemType Directory -Path $data,$updates -Force | Out-Null
$uninstaller = Join-Path $installation 'unins000.exe'
$saved = @{}
$overrideNames = @('WEBVIEW2_USER_DATA_FOLDER','DATABASE_URL','JWT_SECRET','FIELD_ENCRYPTION_KEY','SUPER_ADMIN_PASSWORD','STATIC_DIR','UPDATE_CLIENT_TYPE','UPDATE_AGENT_URL','UPDATE_AGENT_TOKEN','UPDATE_HISTORY_PATH','UPDATE_MANIFEST_URL') + @(Get-ChildItem Env: | Where-Object Name -like 'TKCRM_*' | ForEach-Object Name) + @('TKCRM_DATA_DIR','TKCRM_UPDATE_READY_FILE')
foreach ($name in ($overrideNames | Select-Object -Unique)) {
  $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
  [Environment]::SetEnvironmentVariable($name, $null, 'Process')
}
$owned = [Collections.Generic.List[System.Diagnostics.Process]]::new()
$ownedServers = [Collections.Generic.List[System.Diagnostics.Process]]::new()
$oldDesktop = $null
$newDesktop = $null
$updater = $null
$finished = $false

function Read-Json([string]$Path) {
  if (Test-Path -LiteralPath $Path -PathType Leaf) { try { return Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json } catch { } }
  return $null
}
function Verify-Data {
  & $python -X utf8 (Join-Path $PSScriptRoot 'online-update-smoke.py') verify $data
  if ($LASTEXITCODE -ne 0) { throw 'Isolated database/data verification failed' }
}
function Register-Server([System.Diagnostics.Process]$Desktop) {
  foreach ($child in @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'TkCrm.Server.exe' -and $_.ParentProcessId -eq $Desktop.Id })) {
    $server = Get-Process -Id $child.ProcessId
    $owned.Add($server)
    $ownedServers.Add($server)
  }
}
function Start-Updater([string]$Name, [object]$Manifest) {
  $manifestFile = Join-Path $updates ($Name + '.json')
  $statusFile = Join-Path $updates ($Name + '-status.json')
  [IO.File]::WriteAllText($manifestFile, ($Manifest | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
  $arguments = @('--parent-pid',[string]$oldDesktop.Id,'--install-dir',('"' + $installation + '"'),'--data-dir',('"' + $data + '"'),'--expected-version',$version,'--manifest-file',('"' + $manifestFile + '"'),'--installer-url',$packageUrl,'--sha256',[string]$Manifest.windows_sha256,'--status-file',('"' + $statusFile + '"'))
  $process = Start-Process -FilePath (Join-Path $updates 'TkCrm.Updater.exe') -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $updates ($Name + '.stdout.log')) -RedirectStandardError (Join-Path $updates ($Name + '.stderr.log'))
  $null = $process.Handle
  $owned.Add($process)
  return @{ Process=$process; Status=$statusFile }
}
function Wait-UpdaterExit([System.Diagnostics.Process]$Process, [datetime]$Deadline) {
  while (-not $Process.HasExited -and (Get-Date) -lt $Deadline) { Start-Sleep -Milliseconds 500 }
  if (-not $Process.HasExited) { throw 'Online updater timeout; fixture preserved for inspection' }
  $Process.WaitForExit()
  if ($Process.ExitCode -isnot [int]) { throw "Updater exit code unavailable: pid=$($Process.Id)" }
}
function Wait-OwnedServersExit {
  $deadline = (Get-Date).AddSeconds(10)
  foreach ($server in $ownedServers) {
    while (-not $server.HasExited -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 100 }
    if (-not $server.HasExited) { throw 'Owned server remained after normal desktop close' }
  }
}

try {
  Write-Output "Online update fixture: $fixture"
  $install = Start-Process -FilePath $OldInstaller -ArgumentList @('/CURRENTUSER','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS','/TASKS=',('/DIR="' + $installation + '"'),('/LOG="' + (Join-Path $fixture 'install.log') + '"')) -WindowStyle Hidden -Wait -PassThru
  if ($install.ExitCode -ne 0) { throw "Old installer failed: $($install.ExitCode)" }
  & $python -X utf8 (Join-Path $PSScriptRoot 'online-update-smoke.py') seed $data
  if ($LASTEXITCODE -ne 0) { throw 'Synthetic old database seed failed' }
  $env:TKCRM_DATA_DIR = $data
  $env:TKCRM_UPDATE_READY_FILE = Join-Path $fixture 'old-ready.json'
  $env:WEBVIEW2_USER_DATA_FOLDER = Join-Path $fixture 'webview2'
  $oldDesktop = Start-Process -FilePath (Join-Path $installation 'TkCrm.Desktop.exe') -WindowStyle Hidden -PassThru
  $owned.Add($oldDesktop)
  $deadline = (Get-Date).AddSeconds(60)
  $oldReceipt = $null
  while ($null -eq $oldReceipt -and -not $oldDesktop.HasExited -and (Get-Date) -lt $deadline) { $oldReceipt = Read-Json $env:TKCRM_UPDATE_READY_FILE; if ($null -eq $oldReceipt) { Start-Sleep -Milliseconds 250 } }
  if ($null -eq $oldReceipt -or [string]$oldReceipt.version -ne '1.1.15' -or [int]$oldReceipt.pid -ne $oldDesktop.Id) { throw 'Old desktop ready receipt failed' }
  Register-Server $oldDesktop
  $oldHealth = Invoke-RestMethod ("http://127.0.0.1:{0}/health" -f $oldReceipt.port) -TimeoutSec 5
  if ($oldHealth.status -ne 'ok' -or $oldHealth.version -ne '1.1.15') { throw 'Old desktop health mismatch' }
  if (-not (Test-Path -LiteralPath (Join-Path $env:WEBVIEW2_USER_DATA_FOLDER 'EBWebView') -PathType Container)) { throw 'WebView2 fixture is not isolated' }
  Verify-Data
  Write-Output 'PASS old 1.1.15 started and migrated 0004 fixture to the existing head'

  $payloadBefore = @{}
  foreach ($file in @(Get-ChildItem -LiteralPath $installation -Recurse -File)) { $payloadBefore[$file.FullName] = (Get-FileHash -LiteralPath $file.FullName).Hash }
  Copy-Item -LiteralPath $NewUpdater -Destination (Join-Path $updates 'TkCrm.Updater.exe')
  $badRelease = $release | ConvertTo-Json -Depth 8 | ConvertFrom-Json
  $badRelease.windows_sha256 = if ([string]$release.windows_sha256 -eq ('0' * 64)) { '1' * 64 } else { '0' * 64 }
  $negative = Start-Updater 'bad-checksum' $badRelease
  $updater = $negative.Process
  Wait-UpdaterExit $updater ((Get-Date).AddMinutes(12))
  $state = Read-Json $negative.Status
  if ($updater.ExitCode -ne 1 -or $null -eq $state -or $state.status -ne 'failed' -or $state.message -notmatch 'SHA-256') { throw 'Checksum mismatch was not rejected by production downloader' }
  if ($oldDesktop.HasExited) { throw 'Checksum failure closed the old desktop' }
  foreach ($path in $payloadBefore.Keys) { if ((Get-FileHash -LiteralPath $path).Hash -ne $payloadBefore[$path]) { throw 'Checksum failure modified installation files' } }
  $oldHealth = Invoke-RestMethod ("http://127.0.0.1:{0}/health" -f $oldReceipt.port) -TimeoutSec 5
  if ($oldHealth.status -ne 'ok' -or $oldHealth.version -ne '1.1.15') { throw 'Checksum failure damaged the old server' }
  Verify-Data
  Write-Output 'PASS real GitHub download with bad SHA: old app/files/data preserved before shutdown'

  $positive = Start-Updater 'valid-update' $release
  $updater = $positive.Process
  $deadline = (Get-Date).AddMinutes(12)
  $state = $null
  while (-not $updater.HasExited -and (Get-Date) -lt $deadline) {
    $state = Read-Json $positive.Status
    if ($state -and $state.status -eq 'waiting_exit') { break }
    if ($state -and $state.status -eq 'failed') { throw "Online updater failed before exit: $($state.message)" }
    Start-Sleep -Milliseconds 500
  }
  if (-not $state -or $state.status -ne 'waiting_exit') { throw 'Production updater did not reach waiting_exit after download/hash verification' }
  & (Join-Path $PSScriptRoot 'close-fixture-desktop.ps1') -DesktopProcess $oldDesktop
  Wait-OwnedServersExit
  Wait-UpdaterExit $updater ((Get-Date).AddMinutes(5))
  $state = Read-Json $positive.Status
  if ($updater.ExitCode -ne 0 -or $null -eq $state -or $state.status -ne 'completed') { throw "Production online update failed: $($state.message)" }
  $readyFiles = @(Get-ChildItem -LiteralPath (Join-Path $updates 'updates') -Filter ready.json -Recurse -File)
  $newReceipt = $null
  foreach ($file in $readyFiles) { $receipt = Read-Json $file.FullName; if ($receipt -and [string]$receipt.version -eq $version) { $newReceipt = $receipt; break } }
  if ($null -eq $newReceipt) { throw 'Production updater new-version receipt missing' }
  $newDesktop = Get-Process -Id ([int]$newReceipt.pid)
  $newProcess = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $newDesktop.Id)
  if ([string]$newProcess.ExecutablePath -ine (Join-Path $installation 'TkCrm.Desktop.exe')) { throw 'New receipt belongs to another installation' }
  $owned.Add($newDesktop)
  Register-Server $newDesktop
  $newHealth = Invoke-RestMethod ("http://127.0.0.1:{0}/health" -f $newReceipt.port) -TimeoutSec 5
  if ($newHealth.status -ne 'ok' -or $newHealth.version -ne $version) { throw 'Updated desktop health/version mismatch' }
  $history = @(Get-Content -LiteralPath (Join-Path $data 'update-history.json') -Raw -Encoding utf8 | ConvertFrom-Json)
  if ([string]$history[0].version -ne $version -or ($history[0].changes | ConvertTo-Json -Compress) -cne ($release.changes | ConvertTo-Json -Compress)) { throw 'Version/changelog update history differs from manifest' }
  Verify-Data
  Write-Output "PASS production online entry: GitHub HTTPS/SHA, real install, new desktop receipt/health $version, original data and history"
  & (Join-Path $PSScriptRoot 'close-fixture-desktop.ps1') -DesktopProcess $newDesktop
  Wait-OwnedServersExit
  $databaseHash = (Get-FileHash -LiteralPath (Join-Path $data 'monitor.db')).Hash
  $historyHash = (Get-FileHash -LiteralPath (Join-Path $data 'update-history.json')).Hash
  $finished = $true
} finally {
  # On failures stop only processes proven to belong to this temporary installation/updater.
  if ($updater -and -not $updater.HasExited) {
    & taskkill.exe /PID $updater.Id /T /F *> $null
    if (-not $updater.WaitForExit(10000)) { throw "Owned updater tree could not be stopped; fixture=$fixture" }
  }
  foreach ($process in $owned) {
    if (-not $process.HasExited) { & taskkill.exe /PID $process.Id /T /F *> $null; if (-not $process.WaitForExit(10000)) { throw "Owned fixture process could not be stopped; fixture=$fixture" } }
  }
  foreach ($name in @('TkCrm.Desktop.exe','TkCrm.Server.exe','TkCrm.Updater.exe')) {
    foreach ($process in @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq $name -and $_.ExecutablePath -and ([string]$_.ExecutablePath).StartsWith($fixture + '\', [StringComparison]::OrdinalIgnoreCase) })) { & taskkill.exe /PID $process.ProcessId /T /F *> $null }
  }
  foreach ($process in $owned) { if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }; $process.Dispose() }
  foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
  if (Test-Path -LiteralPath $uninstaller -PathType Leaf) {
    $uninstall = Start-Process -FilePath $uninstaller -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART' -WindowStyle Hidden -Wait -PassThru
    if ($uninstall.ExitCode -ne 0) { throw "Fixture uninstaller failed: $($uninstall.ExitCode); fixture=$fixture" }
  }
}
if (-not $finished) { throw 'Online update did not finish' }
if (Test-Path -LiteralPath (Join-Path $installation 'TkCrm.Desktop.exe')) { throw 'Updated application remained after uninstall' }
if ((Get-FileHash -LiteralPath (Join-Path $data 'monitor.db')).Hash -ne $databaseHash -or (Get-FileHash -LiteralPath (Join-Path $data 'update-history.json')).Hash -ne $historyHash) { throw 'Uninstall changed retained database/history' }
Verify-Data
Write-Output "PASS isolated online update/uninstall fixture=$fixture"
