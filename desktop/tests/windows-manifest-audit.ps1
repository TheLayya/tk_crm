param(
  [Parameter(Mandatory = $true)][string]$ManifestPath,
  [Parameter(Mandatory = $true)][string]$PackagePath
)

$ErrorActionPreference = 'Stop'
$manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding utf8 | ConvertFrom-Json
$package = (Resolve-Path $PackagePath).Path
$versionText = Get-Content (Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path 'backend\app\version.py') -Raw -Encoding utf8
if ($versionText -notmatch 'APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"') { throw 'Unable to read APP_VERSION' }
$version = $Matches[1]
if ([string]$manifest.version -ne $version) { throw "Manifest version mismatch: $($manifest.version) != $version" }
$url = [Uri]$manifest.windows_package_url
if ($url.Scheme -ne 'https' -or $url.Host -ne 'github.com' -or $url.UserInfo -or $url.Query -or $url.Fragment -or -not $url.AbsolutePath.StartsWith("/TheLayya/tk_crm/releases/download/v$version/", [StringComparison]::Ordinal) -or -not $url.AbsolutePath.EndsWith('.exe', [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid Windows package URL' }
$actual = (Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne ([string]$manifest.windows_sha256).ToLowerInvariant()) { throw "Windows package SHA-256 mismatch: $actual != $($manifest.windows_sha256)" }
$changes = @($manifest.changes)
if ($changes.Count -eq 0 -or ($changes | Where-Object { $_ -isnot [string] -or [string]::IsNullOrWhiteSpace($_) }).Count -gt 0) { throw 'Manifest changes must be a non-empty string array' }
Write-Output "PASS Windows manifest audit: version=$version sha256=$actual"
