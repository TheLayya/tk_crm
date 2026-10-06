$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runtime = Join-Path $root 'desktop\runtime\windows-x64'
$installer = Join-Path $root 'desktop\build\MicrosoftEdgeWebview2Setup.exe'
$versionText = Get-Content (Join-Path $root 'backend\app\version.py') -Raw
if ($versionText -notmatch 'APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"') { throw 'Unable to read APP_VERSION' }
$setup = Join-Path $root ('desktop\build\installer\TkCRM-{0}-win-x64-setup.exe' -f $Matches[1])

foreach ($path in @(
  (Join-Path $runtime 'TkCrm.Desktop.exe'),
  (Join-Path $runtime 'coreclr.dll'),
  (Join-Path $runtime 'hostfxr.dll'),
  (Join-Path $runtime 'server\TkCrm.Server.exe'),
  (Join-Path $runtime 'server\_internal\frontend\dist\index.html'),
  $installer,
  $setup
)) {
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing self-contained release file: $path" }
}

$signature = Get-AuthenticodeSignature -LiteralPath $installer
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
  throw 'WebView2 bootstrapper signature is invalid or not Microsoft Corporation'
}

$runtimeData = @(Get-ChildItem -LiteralPath $runtime -Recurse -Force -File | Where-Object {
  $_.Name -eq '.env' -or $_.Extension -in '.db', '.sqlite', '.sqlite3'
})
if ($runtimeData.Count -gt 0) { throw ('Runtime data found in release: ' + (($runtimeData | ForEach-Object FullName) -join '; ')) }

Write-Output 'PASS environment audit: self-contained runtime, signed WebView2 bootstrapper, no runtime data'
Write-Output ('desktop=' + (Get-Item (Join-Path $runtime 'TkCrm.Desktop.exe')).Length)
Write-Output ('server=' + (Get-Item (Join-Path $runtime 'server\TkCrm.Server.exe')).Length)
Write-Output ('installer=' + (Get-Item $setup).Length)
