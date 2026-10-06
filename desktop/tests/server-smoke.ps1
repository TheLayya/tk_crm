$ErrorActionPreference = "Stop"
$versionText = Get-Content -LiteralPath "backend/app/version.py" -Raw
if ($versionText -notmatch 'APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"') { throw "Unable to read APP_VERSION" }
$expectedVersion = $Matches[1]
$data = Join-Path $env:TEMP ("TkCRM-server-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $data -Force | Out-Null
$content = "JWT_SECRET=0123456789abcdef0123456789abcdef" + [Environment]::NewLine + "FIELD_ENCRYPTION_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" + [Environment]::NewLine + "SUPER_ADMIN_PASSWORD=Admin123!" + [Environment]::NewLine
[IO.File]::WriteAllText((Join-Path $data ".env"), $content, [Text.UTF8Encoding]::new($false))
$out = Join-Path $data "stdout.log"
$err = Join-Path $data "stderr.log"
$exe = (Resolve-Path "desktop/runtime/windows-x64/server/TkCrm.Server.exe").Path
$env:TKCRM_DATA_DIR = $data
$env:PORT = "8097"
$env:HOST = "127.0.0.1"
$env:PYTHONUTF8 = "1"
$p = Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe) -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 8
$health = ""
try { $health = (Invoke-RestMethod "http://127.0.0.1:8097/health" -TimeoutSec 3 | ConvertTo-Json -Compress) } catch { $health = "ERROR: " + $_.Exception.Message }
$alive = [bool](Get-Process -Id $p.Id -ErrorAction SilentlyContinue)
$ownsPort = [bool](Get-NetTCPConnection -LocalPort 8097 -State Listen -ErrorAction SilentlyContinue | Where-Object OwningProcess -eq $p.Id)
Write-Output ("pid={0} alive={1} health={2} database={3}" -f $p.Id,$alive,$health,[bool](Test-Path (Join-Path $data "monitor.db")))
if (Test-Path $err) { Get-Content $err -Tail 40 }
if (-not $alive -or -not $ownsPort -or $health -notmatch '"status":"ok"' -or $health -notlike ('*"version":"' + $expectedVersion + '"*') -or -not (Test-Path (Join-Path $data "monitor.db"))) { if ($alive) { Stop-Process -Id $p.Id -Force }; throw "服务冒烟失败" }
Stop-Process -Id $p.Id -Force
Write-Output "PASS server smoke: owned listener, current version and isolated database"
