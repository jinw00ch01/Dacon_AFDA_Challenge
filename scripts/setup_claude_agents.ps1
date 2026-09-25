param(
    [Parameter(Mandatory=$true)][ValidateSet('pro360','ultra5060')][string]$Role,
    [switch]$NoStart,
    [switch]$SkipClaudeCheck,
    [switch]$SkipRawDataProtection,
    [switch]$Uninstall
)
# One-time setup per PC for the Claude Code agent loop. Run from a normal PowerShell
# (NOT from inside the Codex app: its MSIX sandbox hides files and autostart entries).
# Idempotent: re-run it after fixing whatever it reports. No administrator rights needed.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot ".venv-$Role\Scripts\python.exe"
$pythonw = Join-Path $projectRoot ".venv-$Role\Scripts\pythonw.exe"
$config = Join-Path $projectRoot 'configs\local-exchange.json'
$agentTask = "AFDA-Agent-$Role"
$exchangeTask = "AFDA-Exchange-$Role"
$realState = Join-Path $env:LOCALAPPDATA "AFDA\$Role"
$user = "$env:USERDOMAIN\$env:USERNAME"

function Get-ExchangeProcesses {
    $pattern = [regex]::Escape("AFDA\$Role\")
    Get-CimInstance Win32_Process -Filter "Name='syncthing.exe' OR Name='powershell.exe'" |
        Where-Object { $_.CommandLine -and ($_.CommandLine -match $pattern -or $_.CommandLine -match 'start_exchange\.ps1') }
}
function Stop-Exchange([string]$stateDir) {
    New-Item -ItemType File -Path (Join-Path $stateDir 'STOP') -Force | Out-Null
    for ($i = 0; $i -lt 40 -and (Get-ExchangeProcesses); $i++) { Start-Sleep -Seconds 3 }
    $left = Get-ExchangeProcesses
    if ($left) { $left | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Start-Sleep -Seconds 3 }
    Remove-Item -LiteralPath (Join-Path $stateDir 'STOP') -ErrorAction SilentlyContinue
}
function Register-UserTask([string]$name, $action) {
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
}

if ($Uninstall) {
    & $python -m agent_bridge --config $config stop | Out-Null
    Unregister-ScheduledTask -TaskName $agentTask -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "Removed $agentTask. The exchange service ($exchangeTask) is left running."
    exit 0
}
if (-not (Test-Path -LiteralPath $python)) { throw "Missing $python. Run scripts/bootstrap.ps1 -Role $Role first." }

# 1. Move exchange state out of the Codex MSIX sandbox, keeping the Syncthing identity (no re-pairing).
$virtual = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Packages') -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Join-Path $_.FullName "LocalCache\Local\AFDA\$Role" } |
    Where-Object { Test-Path -LiteralPath (Join-Path $_ 'syncthing\config.xml') } | Select-Object -First 1
if ($virtual -and -not (Test-Path -LiteralPath (Join-Path $realState 'syncthing\config.xml'))) {
    Write-Output "Migrating exchange state out of the app sandbox: $virtual"
    Stop-Exchange $virtual
    New-Item -ItemType Directory -Path $realState -Force | Out-Null
    Get-ChildItem -LiteralPath $virtual -Force | Where-Object { $_.Name -notin @('STOP','worker.lock','supervisor.pid') } |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $realState -Recurse -Force }
    Rename-Item -LiteralPath $virtual -NewName ($Role + '.migrated-' + (Get-Date -Format 'yyyyMMddHHmmss'))
}

# 2. Re-apply exchange settings outside the sandbox (fixes the receive-folder versioning bug),
#    then hand the supervisor to Task Scheduler so it does not depend on this console.
& (Join-Path $PSScriptRoot 'setup_exchange.ps1') -Role $Role
Stop-Exchange $realState
$exchangeAction = New-ScheduledTaskAction -Execute 'powershell.exe' -WorkingDirectory $projectRoot `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSScriptRoot\start_exchange.ps1`" -Config `"$config`""
Register-UserTask $exchangeTask $exchangeAction
Start-ScheduledTask -TaskName $exchangeTask
Write-Output "Exchange service running as scheduled task $exchangeTask."

# 3. Raw data read-only (defence in depth; new files can still be added).
if (-not $SkipRawDataProtection) {
    foreach ($dir in @('data\external','data\captures','Baseline')) {
        $full = Join-Path $projectRoot $dir
        if (Test-Path -LiteralPath $full) { Get-ChildItem -LiteralPath $full -Recurse -File | ForEach-Object { $_.IsReadOnly = $true } }
    }
}

# 4. Role memory for Claude Code (git-ignored) and guard/claude self-test.
@"
# AFDA role of this PC: $Role
@.claude/roles/$Role.md
"@ | Set-Content -LiteralPath (Join-Path $projectRoot 'CLAUDE.local.md') -Encoding UTF8
New-Item -ItemType Directory -Path (Join-Path $projectRoot 'work\agent\outbox') -Force | Out-Null
& $python -m agent_bridge --config $config selftest
if ($LASTEXITCODE -ne 0) { throw 'agent_bridge selftest failed (python on PATH for hooks? claude installed?).' }

# 5. Claude Code must trust this folder (else project hooks/permissions are ignored) and be logged in.
$claudeJson = Join-Path $env:USERPROFILE '.claude.json'
$key = $projectRoot.Replace('\', '/')
$trusted = & $python -c "import json,sys;d=json.load(open(sys.argv[1],encoding='utf-8'));p=d.get('projects',{});print(any(k.lower()==sys.argv[2].lower() and v.get('hasTrustDialogAccepted') for k,v in p.items()))" $claudeJson $key
$howTo = "In a terminal: cd `"$projectRoot`"; claude   -> accept 'trust this folder', type /login if asked, then /exit. Re-run this script."
if ($trusted.Trim() -ne 'True') { Write-Output "ACTION NEEDED: Claude Code has not trusted this folder yet. $howTo"; exit 2 }
if (-not $SkipClaudeCheck) {
    $claude = (& $python -c "from agent_bridge.runner import resolve_claude;from agent_bridge.state import load_policy;print(resolve_claude(load_policy('$Role'))[0])").Trim()
    Remove-Item Env:CLAUDECODE -ErrorAction SilentlyContinue
    $answer = ('Reply with exactly: AFDA-OK' | & $claude -p --output-format json --max-budget-usd 0.5) -join "`n"
    if ($LASTEXITCODE -ne 0 -or $answer -notmatch 'AFDA-OK') { Write-Output "ACTION NEEDED: claude -p cannot run ($answer). $howTo"; exit 3 }
    Write-Output 'claude -p authentication: OK'
}

# 6. Agent loop as a scheduled task: starts at logon, restarts if it dies. Runs as this user.
$agentAction = New-ScheduledTaskAction -Execute $pythonw -Argument "-m agent_bridge --config `"$config`" loop" -WorkingDirectory $projectRoot
Register-UserTask $agentTask $agentAction
& $python -m agent_bridge --config $config resume | Out-Null
if (-not $NoStart) { Start-ScheduledTask -TaskName $agentTask }
Write-Output "Agent loop task '$agentTask' registered$(if (-not $NoStart) {' and started'})."
Write-Output "Status: .venv-$Role\Scripts\python.exe -m agent_bridge status   | Pause: ... pause   | Resume: ... resume"
Write-Output 'Keep the PC plugged in and set Windows sleep to Never while the agents should work.'
