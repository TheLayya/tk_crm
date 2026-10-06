param(
  [Parameter(Mandatory = $true)][string]$PackagePath,
  [Parameter(Mandatory = $true)][string]$PackageUrl,
  [string]$OutputPath = ''
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$versionText = Get-Content (Join-Path $root 'backend\app\version.py') -Raw
if ($versionText -notmatch 'APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"') { throw 'Unable to read APP_VERSION' }
$version = $Matches[1]
$package = (Resolve-Path $PackagePath).Path
$packageName = [IO.Path]::GetFileName($package)
if ($packageName -ne "TkCRM-$version-win-x64-setup.exe") { throw "Package filename does not match APP_VERSION: $packageName" }
$uri = [Uri]$PackageUrl
if ($uri.Scheme -ne 'https' -or $uri.Host -ne 'github.com' -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or -not $uri.AbsolutePath.StartsWith("/TheLayya/tk_crm/releases/download/v$version/", [StringComparison]::Ordinal) -or -not $uri.AbsolutePath.EndsWith('.exe', [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid GitHub Windows package URL' }
$basePath = Join-Path $root 'version.json'
$base = if (Test-Path -LiteralPath $basePath) { Get-Content -LiteralPath $basePath -Raw -Encoding utf8 | ConvertFrom-Json } else { [pscustomobject]@{} }
if (($base.package_url -or $base.sha256 -or $base.changes) -and [string]$base.version -ne $version) { throw 'Base manifest version does not match APP_VERSION' }
$output = if ($OutputPath) { [IO.Path]::GetFullPath($OutputPath) } else { Join-Path $PSScriptRoot 'build\version.windows.json' }
$resolvedRoot = (Resolve-Path $root).Path.TrimEnd('\')
if (-not $output.StartsWith($resolvedRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Output must remain inside repository: $output" }
$manifest = [ordered]@{
  version = $version
  date = if ($base.date) { [string]$base.date } else { (Get-Date).ToString('yyyy-MM-dd') }
  package_url = if ($base.package_url) { [string]$base.package_url } else { $null }
  sha256 = if ($base.sha256) { [string]$base.sha256 } else { $null }
  windows_package_url = $PackageUrl
  windows_sha256 = (Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLowerInvariant()
  changes = @($base.changes)
}
if ($null -eq $manifest.package_url) { $manifest.Remove('package_url') }
if ($null -eq $manifest.sha256) { $manifest.Remove('sha256') }
New-Item -ItemType Directory -Path (Split-Path $output) -Force | Out-Null
$json = $manifest | ConvertTo-Json -Depth 4
[IO.File]::WriteAllText($output, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Output "Generated Windows manifest: $output"
Write-Output "version=$version windows_sha256=$($manifest.windows_sha256)"
