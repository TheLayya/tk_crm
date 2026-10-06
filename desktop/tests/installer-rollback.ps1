$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$dotnet = Join-Path $env:LOCALAPPDATA 'TkCRM-Dev\dotnet\dotnet.exe'
if (-not (Test-Path -LiteralPath $dotnet)) {
  $dotnet = (Get-Command dotnet -ErrorAction Stop).Source
}
$iscc = Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'
if (-not (Test-Path -LiteralPath $iscc)) { throw 'Inno Setup compiler not found' }
Push-Location $root
try {
  & $dotnet build 'desktop/tests/InstallerRollback/InstallerRollback.csproj' -c Release --nologo
  if ($LASTEXITCODE -ne 0) { throw 'Rollback test build failed' }
  & $iscc 'desktop/tests/InstallerRollback/failure.iss'
  if ($LASTEXITCODE -ne 0) { throw 'Rollback fixture build failed' }
  $savedDotnetRoot = $env:DOTNET_ROOT
  try {
    $env:DOTNET_ROOT = Split-Path -Parent $dotnet
    & $dotnet 'desktop/tests/InstallerRollback/bin/Release/net10.0-windows/InstallerRollback.dll' 'desktop/build/rollback-fixture/failure-setup.exe'
  } finally {
    if ($null -eq $savedDotnetRoot) { Remove-Item Env:DOTNET_ROOT -ErrorAction SilentlyContinue }
    else { $env:DOTNET_ROOT = $savedDotnetRoot }
  }
  if ($LASTEXITCODE -ne 0) { throw 'Installer rollback test failed' }
} finally {
  Pop-Location
}
