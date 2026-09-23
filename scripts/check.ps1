param([ValidateSet('pro360','ultra5060')][string]$Role = 'ultra5060')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot ('.venv-' + $Role + '/Scripts/python.exe')
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts/bootstrap.ps1 first.' }
& $pythonPath -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Harness tests failed.' }
& $pythonPath -m harness doctor --profile $Role
if ($LASTEXITCODE -ne 0) { throw 'Environment check failed.' }
& $pythonPath -m harness inventory --profile $Role
if ($LASTEXITCODE -ne 0) { throw 'Data check failed.' }
& $pythonPath -m harness smoke --profile $Role
if ($LASTEXITCODE -ne 0) { throw 'Model smoke failed.' }
