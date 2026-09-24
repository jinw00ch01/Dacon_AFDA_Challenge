param(
    [Parameter(Mandatory=$true)][ValidateSet('pro360','ultra5060')][string]$Role,
    [string]$PeerId = '',
    [string]$ExchangeRoot = 'C:\Dacon\AFDA_Exchange',
    [string]$PythonExecutable = '',
    [switch]$NoAutoStart
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot ".venv-$Role\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    if (-not $PythonExecutable) {
        $oldPython = 'C:\Dacon\Dacon_AFDA_Challenge\.venv-pro360\Scripts\python.exe'
        if ($Role -eq 'pro360' -and (Test-Path -LiteralPath $oldPython)) {
            $PythonExecutable = (& $oldPython -c 'import sys; print(sys._base_executable)').Trim()
        }
    }
    if ($PythonExecutable) {
        & (Join-Path $PSScriptRoot 'bootstrap.ps1') -Role $Role -PythonExecutable $PythonExecutable
    } else {
        & (Join-Path $PSScriptRoot 'bootstrap.ps1') -Role $Role
    }
    if ($LASTEXITCODE -ne 0) { throw 'Role environment bootstrap failed.' }
}
& $pythonPath -c 'import psutil'
if ($LASTEXITCODE -ne 0) { throw 'psutil is required in the role venv.' }
$stateRoot = Join-Path $env:LOCALAPPDATA "AFDA\$Role"
$syncthingHome = Join-Path $stateRoot 'syncthing'
$binRoot = Join-Path $stateRoot 'bin'
New-Item -ItemType Directory -Path $stateRoot,$syncthingHome,$binRoot,$ExchangeRoot -Force | Out-Null
$version = 'v2.1.5'
$zipName = "syncthing-windows-amd64-$version.zip"
$zipPath = Join-Path $binRoot $zipName
$expectedSha = '39571e4d0900c2a2cab14c0b170f49751340a869e49734ccc8079d9b98a7974b'
if (-not (Test-Path -LiteralPath $zipPath)) {
    $partial = $zipPath + '.partial'
    Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/syncthing/syncthing/releases/download/$version/$zipName" -OutFile $partial
    if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedSha) { throw 'Syncthing archive SHA-256 mismatch.' }
    Move-Item -LiteralPath $partial -Destination $zipPath
}
if ((Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedSha) { throw 'Existing Syncthing archive changed.' }
$syncthingExe = Join-Path $binRoot "syncthing-windows-amd64-$version\syncthing.exe"
if (-not (Test-Path -LiteralPath $syncthingExe)) { Expand-Archive -LiteralPath $zipPath -DestinationPath $binRoot }
$syncthingConfig = Join-Path $syncthingHome 'config.xml'
if (-not (Test-Path -LiteralPath $syncthingConfig)) {
    & $syncthingExe generate --home $syncthingHome --no-port-probing
    if ($LASTEXITCODE -ne 0) { throw 'Syncthing identity generation failed.' }
    [xml]$xml = Get-Content -LiteralPath $syncthingConfig -Raw
    $xml.configuration.gui.address = '127.0.0.1:8385'
    $xml.configuration.options.startBrowser = 'false'
    $xml.configuration.options.natEnabled = 'false'
    foreach ($folder in @($xml.configuration.folder)) { if ($null -ne $folder) { [void]$xml.configuration.RemoveChild($folder) } }
    $xml.Save($syncthingConfig)
}
$configPath = Join-Path $projectRoot 'configs\local-exchange.json'
if (Test-Path -LiteralPath $configPath) {
    $workerConfig = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    if ($workerConfig.role -ne $Role -or $workerConfig.exchange_root -ne $ExchangeRoot) { throw 'Existing exchange config has a different role or folder; preserve it.' }
    if ($PeerId) { $workerConfig.peer_device_id = $PeerId }
} else {
    $workerConfig = [ordered]@{
        version=1;role=$Role;project_root=$projectRoot;python=$pythonPath;exchange_root=$ExchangeRoot;
        syncthing_home=$syncthingHome;syncthing_exe=$syncthingExe;state_root=$stateRoot;
        peer_device_id=$PeerId;auto_git=$true;poll_seconds=15;review_debounce_seconds=30
    }
}
$workerConfig | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $configPath -Encoding UTF8
$stopFile = Join-Path $stateRoot 'STOP'
if (Test-Path -LiteralPath $stopFile) { Remove-Item -LiteralPath $stopFile }
$launchScript = Join-Path $PSScriptRoot 'start_exchange.ps1'
$launchArgs = @('-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',('"'+$launchScript+'"'),'-Config',('"'+$configPath+'"'))
# start_exchange is guarded by a per-role OS mutex; repeated setup is harmless.
Start-Process -FilePath 'powershell.exe' -ArgumentList $launchArgs -WindowStyle Hidden | Out-Null
$ready = $false
for ($attempt=0; $attempt -lt 40; $attempt++) {
    try {
        & $pythonPath -m exchange_bridge.transport configure --config $configPath 2>$null
        if ($LASTEXITCODE -eq 0) { $ready=$true; break }
    } catch { }
    Start-Sleep -Milliseconds 500
}
if (-not $ready) { throw "Syncthing startup failed; see $stateRoot" }
if (-not $NoAutoStart) {
    $runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    New-Item -Path $runKey -Force | Out-Null
    $launchCommand = 'powershell.exe ' + ($launchArgs -join ' ')
    New-ItemProperty -Path $runKey -Name "AFDAExchange-$Role" -Value $launchCommand -PropertyType String -Force | Out-Null
}
& $pythonPath -m exchange_bridge.transport status --config $configPath
Write-Output 'AFDA local setup complete. Initial peer registration is required on BOTH devices.'
Write-Output 'Local dashboard: http://127.0.0.1:8385'
