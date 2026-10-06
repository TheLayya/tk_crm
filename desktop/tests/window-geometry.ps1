$ErrorActionPreference = 'Stop'
$dotnet = Join-Path $env:LOCALAPPDATA 'TkCRM-Dev/dotnet/dotnet.exe'
if (-not (Test-Path -LiteralPath $dotnet)) { $dotnet = (Get-Command dotnet -ErrorAction Stop).Source }
& $dotnet run --project (Join-Path $PSScriptRoot 'WindowGeometry/WindowGeometry.csproj') -c Release
if ($LASTEXITCODE -ne 0) { throw 'Native window geometry checks failed' }
