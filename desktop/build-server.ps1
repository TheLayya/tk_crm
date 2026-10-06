$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root 'backend\.venv312\Scripts\python.exe'
$entry = Join-Path $PSScriptRoot 'server_main.py'
$dist = Join-Path $PSScriptRoot 'runtime\server'

if (-not (Test-Path $python)) {
    throw "找不到开发虚拟环境：$python"
}

if (-not (Test-Path (Join-Path $root 'frontend\dist\index.html'))) { throw '先运行 npm run build --prefix frontend' }
& $python -m PyInstaller --noconfirm --clean --onedir --name TkCrm.Server --distpath $dist --workpath (Join-Path $PSScriptRoot 'build') --specpath (Join-Path $PSScriptRoot 'build') --paths (Join-Path $root 'backend') --collect-submodules app --collect-submodules passlib.handlers --collect-all apscheduler --collect-all uvicorn --add-data "$(Join-Path $root 'backend\alembic');backend/alembic" --add-data "$(Join-Path $root 'backend\alembic.ini');backend" --add-data "$(Join-Path $root 'frontend\dist');frontend/dist" $entry
if ($LASTEXITCODE -ne 0) { throw "TkCrm.Server 打包失败" }

Write-Host "Server runtime: $(Join-Path $dist 'TkCrm.Server')"
