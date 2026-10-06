$ErrorActionPreference = "Stop"
$data = Join-Path $env:TEMP ("TkCRM-desktop-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $data -Force | Out-Null
$content = "JWT_SECRET=0123456789abcdef0123456789abcdef" + [Environment]::NewLine + "FIELD_ENCRYPTION_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" + [Environment]::NewLine + "SUPER_ADMIN_PASSWORD=Admin123!" + [Environment]::NewLine
[IO.File]::WriteAllText((Join-Path $data ".env"), $content, [Text.UTF8Encoding]::new($false))
$exe = (Resolve-Path "desktop/runtime/windows-x64/TkCrm.Desktop.exe").Path
$versionText = Get-Content -LiteralPath "backend/app/version.py" -Raw
if ($versionText -notmatch 'APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"') { throw "无法读取 APP_VERSION" }
$expectedVersion = $Matches[1]
$savedDataDir = $env:TKCRM_DATA_DIR
$savedOverrides = @{}
foreach ($name in @('WEBVIEW2_USER_DATA_FOLDER', 'TKCRM_URL', 'TKCRM_SERVER_EXE', 'TKCRM_SERVER_DIR', 'TKCRM_STATIC_DIR')) {
    $savedOverrides[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$p = $null
$server = $null
try {
$env:TKCRM_DATA_DIR = $data
$env:WEBVIEW2_USER_DATA_FOLDER = Join-Path $data 'webview2'
Remove-Item Env:TKCRM_URL,Env:TKCRM_SERVER_EXE,Env:TKCRM_SERVER_DIR,Env:TKCRM_STATIC_DIR -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $exe -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 12
$desktop = Get-Process -Id $p.Id -ErrorAction SilentlyContinue
$server = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "TkCrm.Server.exe" -and $_.ParentProcessId -eq $p.Id
}
$health = ""
 $port = $null
if ($server) {
    $connection = Get-NetTCPConnection -OwningProcess $server.ProcessId -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($connection) {
        $port = $connection.LocalPort
        try { $health = Invoke-RestMethod ("http://127.0.0.1:{0}/health" -f $port) -TimeoutSec 1 | ConvertTo-Json -Compress } catch { }
    }
}
$healthOk = $health -like '*"status":"ok"*' -and $health -like ('*"version":"' + $expectedVersion + '"*')
Write-Output ("before_close desktop={0} server={1} port={2} health={3}" -f [bool]$desktop, [bool]$server, $port, $health)
if (-not $desktop -or -not $server -or -not $healthOk) {
    if ($desktop) { Stop-Process -Id $p.Id -Force }
    throw "桌面冒烟启动或健康检查失败"
}
& (Join-Path $PSScriptRoot 'close-fixture-desktop.ps1') -DesktopProcess $p
Start-Sleep -Seconds 2
$desktopAfter = Get-Process -Id $p.Id -ErrorAction SilentlyContinue
$serverAfter = Get-Process -Id $server.ProcessId -ErrorAction SilentlyContinue
$databaseCreated = Test-Path (Join-Path $data 'monitor.db')
$desktopFlag = [bool]$desktopAfter
$serverFlag = [bool]$serverAfter
Write-Output ("after_close desktop={0} server={1} database={2}" -f $desktopFlag, $serverFlag, $databaseCreated)
if ($serverAfter) { Stop-Process -Id $server.ProcessId -Force }
if ($desktopAfter -or $serverAfter -or -not $databaseCreated) {
    throw "桌面冒烟退出清理失败"
}
} finally {
    if ($p -and -not $server) {
        $server = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'TkCrm.Server.exe' -and $_.ParentProcessId -eq $p.Id }
    }
    if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    if ($server) { Stop-Process -Id $server.ProcessId -Force -ErrorAction SilentlyContinue }
    if ($null -eq $savedDataDir) { Remove-Item Env:TKCRM_DATA_DIR -ErrorAction SilentlyContinue }
    else { $env:TKCRM_DATA_DIR = $savedDataDir }
    foreach ($name in $savedOverrides.Keys) { [Environment]::SetEnvironmentVariable($name, $savedOverrides[$name], 'Process') }
}
