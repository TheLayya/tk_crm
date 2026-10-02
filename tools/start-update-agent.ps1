param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [Parameter(Mandatory = $true)][string]$Token,
  [Parameter(Mandatory = $true)][string]$Lifecycle,
  [string]$Python = 'python',
  [int]$Port = 8765
)

& $Python (Join-Path $PSScriptRoot 'update_agent.py') --root $Root --lifecycle $Lifecycle --token $Token --port $Port
