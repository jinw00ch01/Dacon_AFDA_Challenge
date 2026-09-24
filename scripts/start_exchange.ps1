param([Parameter(Mandatory=$true)][string]$Config)
$ErrorActionPreference = 'Stop'
$cfg = Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
$mutex = New-Object Threading.Mutex($false, ('Local\AFDAExchange-' + $cfg.role))
try { $acquired = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $acquired = $true }
if (-not $acquired) { $mutex.Dispose(); exit 0 }
try {
    Set-Location -LiteralPath $cfg.project_root
    New-Item -ItemType Directory -Path $cfg.state_root -Force | Out-Null
    $PID | Set-Content -LiteralPath (Join-Path $cfg.state_root 'supervisor.pid') -Encoding ascii
    $log = Join-Path $cfg.state_root 'supervisor.log'
    $syncthingArgs = @('serve','--home',('"'+$cfg.syncthing_home+'"'),'--no-browser','--no-console','--no-upgrade','--log-file',('"'+(Join-Path $cfg.state_root 'syncthing.log')+'"'))
    $syncthingProcess = Start-Process -FilePath $cfg.syncthing_exe -ArgumentList $syncthingArgs -WindowStyle Hidden -PassThru
    while (-not (Test-Path -LiteralPath (Join-Path $cfg.state_root 'STOP'))) {
        if ($syncthingProcess.HasExited) {
            $syncthingProcess = Start-Process -FilePath $cfg.syncthing_exe -ArgumentList $syncthingArgs -WindowStyle Hidden -PassThru
        }
        try {
            & $cfg.python -m exchange_bridge worker --config $Config *>> $log
        } catch { ('Worker error: '+$_.Exception.Message) | Add-Content -LiteralPath $log }
        Start-Sleep -Seconds $cfg.poll_seconds
    }
} finally {
    if ($null -ne $syncthingProcess -and -not $syncthingProcess.HasExited) {
        try { & $cfg.python -m exchange_bridge stop-transport --config $Config *>> $log } catch { }
    }
    $mutex.ReleaseMutex();$mutex.Dispose()
}
