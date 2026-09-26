param([Parameter(Mandatory=$true)][string]$Config)
$ErrorActionPreference = 'Stop'
$cfg = Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
$mutex = New-Object Threading.Mutex($false, ('Local\AFDAExchange-' + $cfg.role))
try { $acquired = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $acquired = $true }
if (-not $acquired) { $mutex.Dispose(); exit 0 }

function Find-Syncthing {
    # Adopt a Syncthing still running for this home (left behind when a previous supervisor was
    # killed) instead of starting a second one that exits at once and is relaunched every poll.
    try {
        $all = @(Get-CimInstance Win32_Process -Filter "Name='syncthing.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($cfg.syncthing_home) })
        $ids = @($all | ForEach-Object { $_.ProcessId })
        $monitor = $all | Where-Object { $ids -notcontains $_.ParentProcessId } | Select-Object -First 1
        if ($null -eq $monitor) { return $null }
        return Get-Process -Id $monitor.ProcessId -ErrorAction SilentlyContinue
    } catch { return $null }
}

function Test-Exited($Process) {
    if ($null -eq $Process) { return $true }
    try { return $Process.HasExited } catch { return $false }  # unknown: assume running, never start a duplicate
}

function Write-Watchdog([string]$Message) {
    ((Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') + ' ' + $Message) | Add-Content -LiteralPath (Join-Path $cfg.state_root 'exchange_watchdog.log') -Encoding ascii
}

function Start-Syncthing {
    $found = Find-Syncthing
    if ($null -ne $found) {
        Write-Watchdog ('adopted running syncthing pid ' + $found.Id)
        return $found
    }
    return Start-Process -FilePath $cfg.syncthing_exe -ArgumentList $syncthingArgs -WindowStyle Hidden -PassThru
}

try {
    Set-Location -LiteralPath $cfg.project_root
    New-Item -ItemType Directory -Path $cfg.state_root -Force | Out-Null
    $stopFile = Join-Path $cfg.state_root 'STOP'
    if (Test-Path -LiteralPath $stopFile) { return }  # stopped on purpose (stop_exchange.ps1): start nothing
    $PID | Set-Content -LiteralPath (Join-Path $cfg.state_root 'supervisor.pid') -Encoding ascii
    $log = Join-Path $cfg.state_root 'supervisor.log'
    $syncthingArgs = @('serve','--home',('"'+$cfg.syncthing_home+'"'),'--no-browser','--no-console','--no-upgrade','--log-file',('"'+(Join-Path $cfg.state_root 'syncthing.log')+'"'))
    $syncthingProcess = Start-Syncthing
    $agentRoot = Join-Path $cfg.state_root 'agent'
    $agentTask = 'AFDA-Agent-' + $cfg.role
    $nextAgentCheck = (Get-Date).AddMinutes(5)
    while (-not (Test-Path -LiteralPath $stopFile)) {
        if (Test-Exited $syncthingProcess) {
            $syncthingProcess = Start-Syncthing
        }
        try {
            & $cfg.python -m exchange_bridge worker --config $Config *>> $log
        } catch { ('Worker error: '+$_.Exception.Message) | Add-Content -LiteralPath $log }
        if ((Get-Date) -ge $nextAgentCheck) {
            $nextAgentCheck = (Get-Date).AddMinutes(10)
            try {
                # Mirror of agent_bridge's exchange watchdog: restart a dead agent loop (its ledger is
                # rewritten every tick, even when paused) unless it was stopped on purpose.
                $ledgerPath = Join-Path $agentRoot 'ledger.json'
                if ((Test-Path -LiteralPath $ledgerPath) -and -not (Test-Path -LiteralPath (Join-Path $agentRoot 'STOP'))) {
                    $idle = ((Get-Date) - (Get-Item -LiteralPath $ledgerPath).LastWriteTime).TotalMinutes
                    if ($idle -gt 10) {
                        & schtasks.exe /Run /TN $agentTask *> $null
                        Write-Watchdog ('agent loop idle ' + [int]$idle + ' min; schtasks /Run ' + $agentTask + ' exit ' + $LASTEXITCODE)
                    }
                }
            } catch { Write-Watchdog ('agent watchdog error: ' + $_.Exception.Message) }
        }
        Start-Sleep -Seconds $cfg.poll_seconds
    }
} finally {
    if (-not (Test-Exited $syncthingProcess)) {
        try { & $cfg.python -m exchange_bridge stop-transport --config $Config *>> $log } catch { }
    }
    $mutex.ReleaseMutex();$mutex.Dispose()
}
