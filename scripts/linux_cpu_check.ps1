param([string]$PythonExecutable = '.\.venv-ultra5060\Scripts\python.exe')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$vmDir = Join-Path (Get-Location) 'work/linux'
$qemuBin = Join-Path $vmDir 'qemu/qemu-system-x86_64.exe'
if (-not (Test-Path -LiteralPath $qemuBin)) { throw 'Prepare verified QEMU/Ubuntu assets first; see environment/README.md.' }
& $PythonExecutable scripts/make_linux_seed.py
if ($LASTEXITCODE -ne 0) { throw 'cloud-init seed generation failed' }
$vmName = 'contracts-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$overlay = Join-Path $vmDir ($vmName + '.qcow2')
$serial = Join-Path $vmDir ($vmName + '.serial.log')
$firmware = Join-Path $vmDir 'qemu/share/edk2-x86_64-code.fd'
$variables = Join-Path $vmDir ($vmName + '.vars.fd')
Copy-Item -LiteralPath (Join-Path $vmDir 'qemu/share/edk2-i386-vars.fd') -Destination $variables
& (Join-Path $vmDir 'qemu/qemu-img.exe') create -f qcow2 -F qcow2 -b (Join-Path $vmDir 'ubuntu.img') $overlay 8G
if ($LASTEXITCODE -ne 0) { throw 'Guest disk creation failed' }
& $PythonExecutable -m harness execute --profile ultra5060 --kind cpu --timeout 1800 -- $qemuBin -machine q35 -accel tcg -cpu max -smp 2 -m 2048 -drive "if=pflash,format=raw,readonly=on,file=$firmware" -drive "if=pflash,format=raw,file=$variables" -drive "file=$overlay,if=virtio,format=qcow2" -drive "file=$vmDir/seed.iso,if=virtio,format=raw,readonly=on" -netdev user,id=net0 -device virtio-net-pci,netdev=net0 -display none -serial "file:$serial" -monitor none -no-reboot
if ($LASTEXITCODE -ne 0) { throw "QEMU failed; inspect $serial" }
if (-not (Select-String -LiteralPath $serial -SimpleMatch 'AFDA_LINUX_EXIT=0' -Quiet)) { throw "Guest tests did not pass; inspect $serial" }
Write-Output "Linux CPU contracts passed: $serial"
