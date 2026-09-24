# Ultra: WSL2와 Linux GPU 설치 명령

2026-09-24 기준 이 PC의 Windows GPU는 RTX 5060 Laptop 8GB, 드라이버 591.74로 확인했다.
WSL 런타임은 아직 설치되지 않았다. 아래는 사용자가 실행할 순서이며 설치/재부팅 완료 기록이 아니다.
Pro에서는 이 절차를 실행하지 않는다. 설치 시 인터넷과 수 GB 이상의 다운로드 공간이 필요하며 Ultra 여유 공간 40GB 이상을 유지한다.

## 1. Windows 관리자 PowerShell

저장하지 않은 작업을 저장한다. 시작 메뉴에서 Windows Terminal 또는 PowerShell을 **관리자 권한으로 실행**한다.

```powershell
nvidia-smi
wsl --install -d Ubuntu-24.04 --web-download
```

설치 결과를 확인한 뒤 재시작이 요구되면 시작 메뉴의 **다시 시작**을 직접 선택한다.
명령들을 실행하던 창은 닫히므로 아래는 재부팅 후 새 창에서 시작한다.
설치가 실패했다면 재설치 반복 대신 맨 아래 오류 분기를 따른다.

## 2. 재부팅 후 Windows PowerShell

```powershell
wsl --update
wsl --set-default-version 2
wsl --list --verbose
```

목록에 Ubuntu-24.04가 있고 VERSION이 **2**인지 확인한다.
Ubuntu가 없을 때만 관리자 창에서 `wsl --install -d Ubuntu-24.04 --web-download`를 다시 실행한다.
VERSION이 1일 때만 `wsl --set-version Ubuntu-24.04 2`를 실행한다.

```powershell
wsl -d Ubuntu-24.04
```

첫 실행에서 Linux 사용자 이름과 비밀번호를 직접 설정한다. 비밀번호 입력은 화면에 표시되지 않는다.
이후 명령은 **Ubuntu Bash 창**에서 실행한다. Windows PowerShell에 붙여 넣지 않는다.

## 3. Ubuntu에서 GPU 확인

```bash
uname -r
nvidia-smi
```

`nvidia-smi: command not found`일 때만 다음 경로를 시도한다.

```bash
/usr/lib/wsl/lib/nvidia-smi
```

RTX 5060이 표시되어야 한다. 둘 다 실패하거나 GPU를 찾지 못하면 Python 설치보다 WSL/Windows 드라이버 문제를 먼저 해결한다.
**WSL 안에 Linux NVIDIA 디스플레이 드라이버를 설치하지 않는다.** CUDA는 Windows 드라이버를 통해 제공된다.
아래 PyTorch wheel 사용에는 별도 CUDA Toolkit 설치가 필요하지 않다.
[NVIDIA WSL 공식 안내](https://docs.nvidia.com/cuda/wsl-user-guide/).

## 4. Linux 전용 clone 및 가상환경

WSL 홈 디렉터리에 별도 clone한다. Windows의 `.venv-ultra5060`을 복사하지 않는다.
아래 경로가 이미 있다면 clone을 반복하지 말고 `cd ~/afda/Dacon_AFDA_Challenge` 후 변경사항을 확인하고 `git pull --ff-only`한다.
각 단계에서 오류가 발생하면 다음 단계로 진행하지 않는다.

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip git ffmpeg libglib2.0-0 libgl1
mkdir -p ~/afda
cd ~/afda
git clone https://github.com/jinw00ch01/Dacon_AFDA_Challenge.git
cd Dacon_AFDA_Challenge
python3 --version
python3 -m venv .venv-linux-cu128
.venv-linux-cu128/bin/python -m pip install --upgrade pip
.venv-linux-cu128/bin/python -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
.venv-linux-cu128/bin/python -m pip install -r requirements/local-common.txt
.venv-linux-cu128/bin/python -m pip check
```

Ubuntu 24.04의 Python 3.12를 사용한다. wheel 조합은 [PyTorch 공식 이전 버전 안내](https://pytorch.org/get-started/previous-versions/) 기준이다.
Windows freeze 파일에는 Windows 전용 항목이 있을 수 있으므로 이를 Linux에 일괄 설치하지 않는다.

## 5. CUDA 실제 연산과 계약 테스트

Ubuntu Bash, clone한 프로젝트 루트에서 실행한다. 아래 GPU 검사는 다운로드를 하지 않으며 모델 정확도 검사가 아니다.

```bash
.venv-linux-cu128/bin/python -m harness execute --profile ultra5060 --kind gpu --timeout 120 -- .venv-linux-cu128/bin/python -c 'import platform,torch,torchvision; assert platform.system()=="Linux"; print(platform.platform()); print("torch",torch.__version__,"torchvision",torchvision.__version__,"cuda",torch.version.cuda); assert torch.cuda.is_available(), "CUDA unavailable"; print(torch.cuda.get_device_name(0)); x=torch.randn(512,512,device="cuda"); y=x@x; torch.cuda.synchronize(); assert torch.isfinite(y).all().item(); print("CUDA_MATMUL_PASS")'
.venv-linux-cu128/bin/python -m harness execute --profile ultra5060 --kind cpu --timeout 180 -- .venv-linux-cu128/bin/python -m unittest discover -s tests -v
```

완료 기준: GPU run의 exit code 0 및 CUDA_MATMUL_PASS, 계약 테스트 18개 통과.
각 명령이 출력한 runs 경로에 stdout/stderr/환경·코드 해시가 남는다. 패키지 설치가 끝난 뒤에만 이 검사를 한다.

네트워크를 끈 **계약 테스트**도 확인하려면 아래를 추가 실행한다.

```bash
mkdir -p artifacts
set -o pipefail
sudo unshare --net -- .venv-linux-cu128/bin/python -m unittest discover -s tests -v 2>&1 | tee artifacts/wsl-offline-contracts.log
```

이 명령은 별도 네트워크 namespace의 테스트 프로세스에만 적용한다. 다른 WSL 작업의 네트워크를 끄지 않는다.
통과해도 실제 모델 오프라인 추론 통과는 아니다. 모델 준비 후 environment/README.md의 컨테이너 경로로 전체 입력·모델 로딩·출력·시간·메모리를 검증한다.
Docker와 NVIDIA Container Toolkit 설치/이미지 빌드는 그 별도 단계이며, 이번 WSL CUDA 행렬 검사에는 필요하지 않다.
RTX 5060 8GB 실측은 평가 서버 L40S 성능을 대변하지 않는다.

## 오류별 다음 행동

| 증상 | 다음 행동 |
|---|---|
| 오류 740 / 관리자 권한 요구 | Windows 관리자 PowerShell에서 설치 명령 재실행 |
| 다운로드가 0%에 머무름 | 위 --web-download 사용; 네트워크 연결 확인 |
| Ubuntu 목록 없음 | 관리자 창에서 배포판 설치 후 첫 실행 완료 |
| VERSION 1 | 해당 배포판만 --set-version Ubuntu-24.04 2 |
| 0x80370102 / Virtual Machine Platform 요구 | 아래 선택 기능 명령 후 재부팅, 작업 관리자 CPU의 가상화 상태 확인 |
| GPU 미노출 | Windows nvidia-smi → wsl --update → 재부팅 후 WSL 확인 순서. Linux 드라이버 설치로 우회하지 않음 |

선택 기능 오류가 있을 때만 Windows **관리자** PowerShell에서:

```powershell
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
```

작업을 저장하고 직접 재부팅한다. 펌웨어 가상화가 꺼져 있다면 해당 Samsung 모델의 UEFI 안내에 따라 활성화한다.
기존 배포판을 삭제하는 `wsl --unregister`는 해결 절차에 포함하지 않는다.
[Microsoft 설치 안내](https://learn.microsoft.com/en-us/windows/wsl/install), [수동 구성 안내](https://learn.microsoft.com/en-us/windows/wsl/install-manual).

## 사용자에게 필요한 완료 증거

Windows의 `wsl --list --verbose`, Ubuntu의 `nvidia-smi`, CUDA_MATMUL_PASS와 테스트 결과 및 해당 runs 폴더를 보관한다.
계정 비밀번호나 인증 토큰을 기록/전송하지 않는다. Baseline·모델·영상은 Git clone에 포함되지 않으므로 추후 필요한 데이터만 로컬로 복사한다.
