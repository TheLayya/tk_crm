$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
& (Join-Path $root 'backend/.venv312/Scripts/python.exe') -X utf8 (Join-Path $PSScriptRoot 'packaged-migration.py')
if ($LASTEXITCODE -ne 0) { throw 'Frozen server migration fixture failed' }
