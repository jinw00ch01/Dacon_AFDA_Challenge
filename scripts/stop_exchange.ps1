param([switch]$DisableAutoStart)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $projectRoot 'configs\local-exchange.json'
$cfg = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
'Requested by user' | Set-Content -LiteralPath (Join-Path $cfg.state_root 'STOP') -Encoding ascii
if ($DisableAutoStart) {
    Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name ('AFDAExchange-'+$cfg.role) -ErrorAction SilentlyContinue
}
Write-Output 'Stop requested. An active CPU job finishes first. Run setup_exchange.ps1 again to resume.'
