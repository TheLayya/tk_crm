param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ReleaseArguments
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..\..')).Path
$python = Join-Path $root 'backend\.venv312\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}
if (-not $ReleaseArguments) { $ReleaseArguments = @('--help') }
Push-Location $root
try {
    & $python (Join-Path $root 'tools\release.py') @ReleaseArguments
    if ($LASTEXITCODE -ne 0) { throw "Release operation failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}
