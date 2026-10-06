param(
    [string]$Dotnet = ''
)

$ErrorActionPreference = 'Stop'
$localDotnet = Join-Path $env:LOCALAPPDATA 'TkCRM-Dev\dotnet\dotnet.exe'
$dotnetCommand = Get-Command dotnet -ErrorAction SilentlyContinue
if (-not $Dotnet) {
    if ($dotnetCommand) {
        $sdkList = & $dotnetCommand.Source --list-sdks 2>$null
        if ($LASTEXITCODE -eq 0 -and ($sdkList -match '^10\.')) { $Dotnet = $dotnetCommand.Source }
    }
    if (-not $Dotnet -and (Test-Path -LiteralPath $localDotnet)) { $Dotnet = $localDotnet }
    if (-not $Dotnet) { throw 'dotnet SDK not found; install .NET SDK or pass -Dotnet path' }
}
$sdkList = & $Dotnet --list-sdks
if ($LASTEXITCODE -ne 0 -or -not ($sdkList -match '^10\.')) { throw '.NET 10 SDK is required to publish TkCRM' }
$root = Split-Path -Parent $PSScriptRoot
$output = Join-Path $PSScriptRoot 'runtime\windows-x64'

$resolvedRoot = (Resolve-Path $root).Path.TrimEnd('\')
$resolvedOutput = [IO.Path]::GetFullPath($output).TrimEnd('\')
if (-not $resolvedOutput.StartsWith($resolvedRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to clean publish output outside the repository: $resolvedOutput"
}
if (Test-Path -LiteralPath $resolvedOutput) {
    Remove-Item -LiteralPath $resolvedOutput -Recurse -Force
}

Push-Location $root
try {
    & npm.cmd run build --prefix frontend
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    & (Join-Path $PSScriptRoot 'build-server.ps1')
    $updaterOutput = Join-Path $PSScriptRoot 'build\updater-publish'
    $resolvedUpdaterOutput = [IO.Path]::GetFullPath($updaterOutput)
    if (-not $resolvedUpdaterOutput.StartsWith($resolvedRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Updater output must remain inside the repository'
    }
    if (Test-Path -LiteralPath $updaterOutput) { Remove-Item -LiteralPath $updaterOutput -Recurse -Force }
    & $Dotnet publish (Join-Path $PSScriptRoot 'TkCrm.Updater\TkCrm.Updater.csproj') -c Release -r win-x64 --self-contained true -o $updaterOutput
    if ($LASTEXITCODE -ne 0) { throw 'Updater publish failed' }
    & $Dotnet publish (Join-Path $PSScriptRoot 'TkCrm.Desktop\TkCrm.Desktop.csproj') -c Release -r win-x64 --self-contained true -o $output
    if ($LASTEXITCODE -ne 0) { throw 'Desktop publish failed' }
    $server = Join-Path $output 'server'
    New-Item -ItemType Directory -Path $server -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'runtime\server\TkCrm.Server\TkCrm.Server.exe') -Destination $server -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'runtime\server\TkCrm.Server\_internal') -Destination $server -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $updaterOutput 'TkCrm.Updater.exe') -Destination $output -Force
    Remove-Item -LiteralPath $updaterOutput -Recurse -Force
    $forbidden = Get-ChildItem -LiteralPath $output -Recurse -File | Where-Object { $_.Name -eq '.env' -or $_.Extension -in '.db', '.sqlite', '.sqlite3' }
    if ($forbidden) { throw 'Publish output contains runtime data or secrets' }
    Write-Host "Published: $output"
}
finally {
    Pop-Location
}
