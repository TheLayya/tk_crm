$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$versionText = Get-Content (Join-Path $root "backend\app\version.py") -Raw
if ($versionText -notmatch 'APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"') { throw "无法读取 APP_VERSION" }
$version = $Matches[1]
$runtime = Join-Path $root "desktop\runtime\windows-x64"
$installer = Join-Path $root ("desktop\build\installer\TkCRM-{0}-win-x64-setup.exe" -f $version)
$required = @("TkCrm.Desktop.exe", "TkCrm.Updater.exe", "server\TkCrm.Server.exe", "server\_internal\frontend\dist\index.html")
foreach ($relative in $required) {
  $path = Join-Path $runtime $relative
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "缺少发布文件：$relative" }
}
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw "缺少安装器：$installer" }
$sourceFrontend = Join-Path $root "frontend\dist"
$packagedFrontend = Join-Path $runtime "server\_internal\frontend\dist"
$sourceFiles = @(Get-ChildItem -LiteralPath $sourceFrontend -Recurse -File)
$packagedFiles = @(Get-ChildItem -LiteralPath $packagedFrontend -Recurse -File)
if ($sourceFiles.Count -ne $packagedFiles.Count) { throw "Packaged frontend file count differs from current build" }
foreach ($file in $sourceFiles) {
  $relative = $file.FullName.Substring($sourceFrontend.Length).TrimStart('\')
  $packagedFile = Join-Path $packagedFrontend $relative
  if (-not (Test-Path -LiteralPath $packagedFile -PathType Leaf)) { throw "Packaged frontend file missing: $relative" }
  if ((Get-FileHash -LiteralPath $file.FullName).Hash -ne (Get-FileHash -LiteralPath $packagedFile).Hash) { throw "Packaged frontend is stale: $relative" }
}
Write-Output "PASS frontend parity: $($sourceFiles.Count) files match current build"
$forbidden = @(Get-ChildItem -LiteralPath $runtime -Recurse -Force -File | Where-Object { $_.Name -eq ".env" -or $_.Extension -in ".db",".sqlite",".sqlite3" })
if ($forbidden.Count -gt 0) { throw ("发布目录包含运行时数据：" + (($forbidden | ForEach-Object FullName) -join "; ")) }
Write-Output ("version={0}" -f $version)
foreach ($relative in $required) {
  $hash = (Get-FileHash (Join-Path $runtime $relative) -Algorithm SHA256).Hash
  Write-Output ("sha256 {0} {1}" -f $relative,$hash)
}
$installerHash = (Get-FileHash $installer -Algorithm SHA256).Hash
Write-Output ("sha256 installer {0}" -f $installerHash)
Write-Output "PASS package audit: required files present, installer present, runtime data isolated"
