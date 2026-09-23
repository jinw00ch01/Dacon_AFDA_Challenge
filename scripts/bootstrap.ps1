param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('pro360','ultra5060')][string]$Role,
    [string]$PythonExecutable
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$commonRequirements = Join-Path $projectRoot 'requirements/local-common.txt'
if (-not (Test-Path -LiteralPath $commonRequirements)) {
    throw 'Missing requirements/local-common.txt; obtain a complete source handoff before installing.'
}
$venvPath = Join-Path $projectRoot ('.venv-' + $Role)
if (-not (Test-Path -LiteralPath (Join-Path $venvPath 'Scripts/python.exe'))) {
    if ($PythonExecutable) {
        & $PythonExecutable -m venv $venvPath
    } else {
        & py -3.12 -m venv $venvPath
    }
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 venv creation failed.' }
}
$pythonPath = Join-Path $venvPath 'Scripts/python.exe'
& $pythonPath -c 'import sys; assert sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 x64 is required.' }
& $pythonPath -m pip install 'pip==25.2' --timeout 180 --retries 5
if ($LASTEXITCODE -ne 0) { throw 'pip bootstrap failed.' }
if ($Role -eq 'ultra5060') {
    # Official Windows Python 3.12 CUDA 12.8 wheels. The alternate R2 index host
    # timed out here, so keep downloads on the official primary host.
    & $pythonPath -m pip install 'https://download.pytorch.org/whl/cu128/torch-2.8.0%2Bcu128-cp312-cp312-win_amd64.whl' 'https://download.pytorch.org/whl/cu128/torchvision-0.23.0%2Bcu128-cp312-cp312-win_amd64.whl' --timeout 60 --retries 3 --resume-retries 3
} else {
    & $pythonPath -m pip install 'torch==2.8.0' 'torchvision==0.23.0' --index-url 'https://download.pytorch.org/whl/cpu' --timeout 60 --retries 3 --resume-retries 3
}
if ($LASTEXITCODE -ne 0) { throw 'PyTorch installation failed.' }
& $pythonPath -m pip install -r $commonRequirements --timeout 180 --retries 5
if ($LASTEXITCODE -ne 0) { throw 'Common dependency installation failed.' }
& $pythonPath -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed.' }
& $pythonPath -m harness doctor --profile $Role
if ($LASTEXITCODE -ne 0) { throw 'Environment check failed. See runs/.' }
