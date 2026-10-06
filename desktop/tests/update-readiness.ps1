$ErrorActionPreference = 'Stop'
$dotnet = Join-Path $env:LOCALAPPDATA 'TkCRM-Dev/dotnet/dotnet.exe'
if (-not (Test-Path -LiteralPath $dotnet)) { $dotnet = (Get-Command dotnet -ErrorAction Stop).Source }
$project = Join-Path $PSScriptRoot 'UpdateReadiness/UpdateReadiness.csproj'
& $dotnet run --project $project -c Release
if ($LASTEXITCODE -ne 0) { throw 'Update readiness checks failed' }
