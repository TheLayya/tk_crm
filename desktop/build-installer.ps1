param(
    [string]$Iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    [string]$BaseManifestPath = ''
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot "installer.iss"
if (-not (Test-Path $Iscc)) { throw "Inno Setup compiler not found: $Iscc" }
if (-not (Test-Path (Join-Path $PSScriptRoot "runtime\windows-x64\TkCrm.Desktop.exe"))) { throw "Run publish.ps1 first" }
$bootstrapper = Join-Path $PSScriptRoot "build\MicrosoftEdgeWebview2Setup.exe"
if (-not (Test-Path $bootstrapper)) {
    New-Item -ItemType Directory -Path (Split-Path $bootstrapper) -Force | Out-Null
    Invoke-WebRequest -UseBasicParsing -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $bootstrapper
}
$signature = Get-AuthenticodeSignature -LiteralPath $bootstrapper
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { throw 'WebView2 bootstrapper signature rejected' }
$versionText = Get-Content (Join-Path $root 'backend\app\version.py') -Raw
if ($versionText -notmatch 'APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"') { throw 'Invalid app version' }
$version = $Matches[1]
$forbidden = Get-ChildItem (Join-Path $PSScriptRoot 'runtime\windows-x64') -Recurse -File | Where-Object { $_.Name -eq '.env' -or $_.Extension -in '.db', '.sqlite', '.sqlite3' }
if ($forbidden) { throw 'Installer source contains runtime data' }
Push-Location $root
try {
    & $Iscc "/DAppVersion=$version" $script
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed" }
    $package = Join-Path $PSScriptRoot ("build\installer\TkCRM-{0}-win-x64-setup.exe" -f $version)
    $packageUrl = "https://github.com/TheLayya/tk_crm/releases/download/v$version/TkCRM-$version-win-x64-setup.exe"
    & (Join-Path $PSScriptRoot "generate-windows-manifest.ps1") -PackagePath $package -PackageUrl $packageUrl -BaseManifestPath $BaseManifestPath
    & (Join-Path $PSScriptRoot 'tests\release-audit.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Release audit failed' }
    Write-Host "Installer output: $PSScriptRoot\build\installer"
} finally { Pop-Location }
