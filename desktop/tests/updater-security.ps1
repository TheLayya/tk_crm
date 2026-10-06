$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$updater = Join-Path $root 'desktop/runtime/windows-x64/TkCrm.Updater.exe'
$python = Join-Path $root 'backend/.venv312/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $updater)) { throw 'Missing packaged TkCrm.Updater.exe' }
if (-not (Test-Path -LiteralPath $python)) { throw 'Missing backend test virtual environment' }
$oldUpdater = $env:TKCRM_TEST_UPDATER_EXE
$oldFieldKey = $env:FIELD_ENCRYPTION_KEY
$oldJwt = $env:JWT_SECRET
$oldPassword = $env:SUPER_ADMIN_PASSWORD
$oldPythonPath = $env:PYTHONPATH
Push-Location $root
try {
  $env:TKCRM_TEST_UPDATER_EXE = (Resolve-Path -LiteralPath $updater).Path
  $env:FIELD_ENCRYPTION_KEY = ('0123456789abcdef' * 4)
  $env:JWT_SECRET = 'isolated-updater-security-test'
  $env:SUPER_ADMIN_PASSWORD = 'fixture-only'
  $env:PYTHONPATH = "$root\backend;$root"
  & $python -X utf8 -m pytest backend/tests/test_windows_updater_executable.py -q
  if ($LASTEXITCODE -ne 0) { throw 'Windows updater security matrix failed' }
} finally {
  Pop-Location
  if ($null -eq $oldUpdater) { Remove-Item Env:TKCRM_TEST_UPDATER_EXE -ErrorAction SilentlyContinue } else { $env:TKCRM_TEST_UPDATER_EXE = $oldUpdater }
  if ($null -eq $oldFieldKey) { Remove-Item Env:FIELD_ENCRYPTION_KEY -ErrorAction SilentlyContinue } else { $env:FIELD_ENCRYPTION_KEY = $oldFieldKey }
  if ($null -eq $oldJwt) { Remove-Item Env:JWT_SECRET -ErrorAction SilentlyContinue } else { $env:JWT_SECRET = $oldJwt }
  if ($null -eq $oldPassword) { Remove-Item Env:SUPER_ADMIN_PASSWORD -ErrorAction SilentlyContinue } else { $env:SUPER_ADMIN_PASSWORD = $oldPassword }
  if ($null -eq $oldPythonPath) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue } else { $env:PYTHONPATH = $oldPythonPath }
}
