$ErrorActionPreference = 'Stop'
$dotnet = Join-Path $env:LOCALAPPDATA 'TkCRM-Dev/dotnet/dotnet.exe'
if (-not (Test-Path -LiteralPath $dotnet)) { $dotnet = (Get-Command dotnet -ErrorAction Stop).Source }
$savedUpdater = $env:TKCRM_TEST_UPDATER_EXE
try {
  $buildRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\build')).TrimEnd('\')
  $output = [IO.Path]::GetFullPath((Join-Path $buildRoot 'update-lock-updater'))
  if (-not $output.StartsWith($buildRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Fixture output is outside desktop/build' }
  if (Test-Path -LiteralPath $output) { Remove-Item -LiteralPath $output -Recurse -Force }
  & $dotnet publish (Join-Path $PSScriptRoot '..\TkCrm.Updater\TkCrm.Updater.csproj') -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o $output
  if ($LASTEXITCODE -ne 0) { throw 'Update lock fixture updater build failed' }
  $env:TKCRM_TEST_UPDATER_EXE = Join-Path $output 'TkCrm.Updater.exe'
  & $dotnet run --project (Join-Path $PSScriptRoot 'UpdateLock/UpdateLock.csproj') -c Release
  if ($LASTEXITCODE -ne 0) { throw 'Update lock process test failed' }
} finally {
  if ($null -eq $savedUpdater) { Remove-Item Env:TKCRM_TEST_UPDATER_EXE -ErrorAction SilentlyContinue }
  else { $env:TKCRM_TEST_UPDATER_EXE = $savedUpdater }
}
