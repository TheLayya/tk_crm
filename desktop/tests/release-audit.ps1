$ErrorActionPreference = 'Stop'
$scriptRoot = $PSScriptRoot
$updaterSecurityTest = Join-Path $scriptRoot 'updater-security.ps1'
$packageUiTest = Join-Path $scriptRoot 'package-ui-layout.cjs'
$candidateManifest = Join-Path $scriptRoot '..\build\version.windows.json'
foreach ($required in @($updaterSecurityTest, $packageUiTest, $candidateManifest)) {
  if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required release audit input: $required" }
}

& (Join-Path $scriptRoot 'environment-audit.ps1')

& (Join-Path $scriptRoot 'package-audit.ps1')

& (Join-Path $scriptRoot 'update-readiness.ps1')

& (Join-Path $scriptRoot 'update-process.ps1')

& (Join-Path $scriptRoot 'window-geometry.ps1')

& (Join-Path $scriptRoot 'installer-rollback.ps1')

& (Join-Path $scriptRoot 'packaged-migration.ps1')

& (Join-Path $scriptRoot 'no-toolchain-smoke.ps1')

& $updaterSecurityTest
if ($LASTEXITCODE -ne 0) { throw 'Windows updater security matrix failed' }

$savedUiTests = $env:TKCRM_UI_TEST_FILES
try {
  $env:TKCRM_UI_TEST_FILES = 'ui-layout.cjs,card-key-layout.cjs,email-layout.cjs'
  & node $packageUiTest
  if ($LASTEXITCODE -ne 0) { throw '发布包 UI 布局回归失败' }
} finally {
  if ($null -eq $savedUiTests) { Remove-Item Env:TKCRM_UI_TEST_FILES -ErrorAction SilentlyContinue }
  else { $env:TKCRM_UI_TEST_FILES = $savedUiTests }
}

$candidate = Get-Content -LiteralPath $candidateManifest -Raw -Encoding utf8 | ConvertFrom-Json
$candidatePackage = Join-Path $scriptRoot ('..\build\installer\TkCRM-{0}-win-x64-setup.exe' -f ([string]$candidate.version))
& (Join-Path $scriptRoot 'windows-manifest-audit.ps1') -ManifestPath $candidateManifest -PackagePath $candidatePackage

Write-Output 'PASS release audit: environment and package checks passed'
