# Linux 검증 환경

실행 범위를 구분한다. CPU Linux 계약 테스트는 실제 모델의 GPU 추론 통과와 다르다.

## 2026-09-23 실제 검증 결과

- QEMU11.1.0 TCG로 Ubuntu24.04.4/kernel6.8.0-139를 실제 부팅했다.
- Python3.12.3, Ubuntu psutil5.9.8에서 네트워크 namespace 분리(`lo DOWN`만 존재) 후18개 계약 테스트 통과, exit0.
- VM 준비·부팅·검사·종료 약112.28초, Windows에서 관측한 QEMU 최대 RSS 표본1.479GiB. VM은 정상 종료되어 백그라운드에서 계속 실행되지 않는다.
- 로컬 로그: `work/linux/contracts-20260923-215143.serial.log`, 하네스 run `20260923T125143Z_execute_37212c00`.
- 별도 [GitHub Actions 검증](https://github.com/jinw00ch01/Dacon_AFDA_Challenge/actions/runs/35863327222)에서도 Ubuntu24.04/Windows 각각 Python3.12 + psutil6.1.1의18개 테스트를 통과했다.
- CPU VM psutil은 평가 버전과 다르다. Torch/CUDA/실제 영상 추론은 이 검사의 대상이 아니다. CUDA Docker 이미지는 정의만 작성했고 아직 빌드·실행하지 않았다.

## 로컬 환경 준비

현재 Windows에서 WSL 명령은 존재하지만 런타임은 설치되어 있지 않다.
`wsl --install --no-distribution --web-download` 실행은 오류로 종료됐다.
관리자 권한·재부팅 없이 실행할 수 있는 QEMU TCG CPU 가상 머신을 별도로 준비한다.
QEMU는 [공식 사이트의 Windows 배포 링크](https://www.qemu.org/download/#windows),
Ubuntu 이미지는 [Canonical 배포](https://cloud-images.ubuntu.com/minimal/releases/noble/release-20260905/)에서 받는다.
작성자 SHA-512 및 Canonical SHA-256을 검증한다. 설치 프로그램은 실행하지 않고 작업 폴더에 압축 해제한다.

`scripts/make_linux_seed.py`는 cloud-init ISO를 생성한다. guest 안에 하네스와 테스트만 복사하고
준비 단계에서 Python/psutil 설치 후 `unshare --net`으로 네트워크 namespace를 분리해 계약 테스트를 실행한다.
Windows 폴더 공유나 외부 수신 포트는 열지 않는다. 결과를 serial 로그에 남긴 후 guest를 종료한다.
이 CPU VM에는 CUDA가 없고, 평가서버 설치 패키지 전체를 재현하지 않는다.

재현 명령(PowerShell, 프로젝트 루트):

```powershell
.\.venv-ultra5060\Scripts\python.exe -m harness execute --profile ultra5060 --kind cpu --timeout 1800 -- .\.venv-ultra5060\Scripts\python.exe scripts/prepare_linux_assets.py
.\.venv-ultra5060\Scripts\python.exe -m pip install --target work/vm-tools pycdlib==1.14.0
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/linux_cpu_check.ps1
```

자산은 `work/linux/`에 보관하며 디스크는 매 실행 새로운 sparse overlay를 만든다.
QEMU는2개 가상 CPU/2GiB RAM으로 실행하고 하네스가30분 타임아웃을 적용한다.
원본 Ubuntu 이미지는 변경하지 않는다. 다운로드 약470MB, QEMU 해제 크기 약1.3GB다.

## 실제 모델용 Linux CUDA 경로

Dockerfile과 `run_offline.py`를 준비했다. Python3.12 계열 Ubuntu24.04 + torch2.8.0/cu128 + torchvision0.23.0,
직접 필요한 공통 패키지 버전을 사용한다. 공식 전체 이미지 복제본은 아니다.
추가 모델 의존성이 생기면 버전을 고정해서 추가하고 이미지 digest/전체 freeze를 기록한다.

Docker + NVIDIA Container Toolkit이 있는 Linux 또는 GPU 지원 WSL2에서:

```bash
docker build -f environment/Dockerfile -t afda-eval:local .
mkdir -p artifacts/linux-output
timeout 3600 docker run --rm --name afda-offline --network none --gpus all \
  --cpus 7 --memory 16g --shm-size 1g --read-only --tmpfs /tmp:rw,size=2g \
  -v "$PWD/artifacts/submission:/submission:ro" \
  -v "$PWD/artifacts/evaluation-data:/data:ro" \
  -v "$PWD/artifacts/expected:/expected:ro" \
  -v "$PWD/artifacts/linux-output:/output:rw" \
  afda-eval:local --require-cuda
```

`artifacts/submission`에는 검증된 제출 ZIP을 풀고, 평가 유사 데이터는 stage1/2/3 폴더로 준비한다.
expected에는 stage1.json(ID→null), stage2.json(ID→원본 프레임 번호 목록),
stage3.json(ID→검증된10Hz 표본 수)을 별도로 만든다. 공개 Baseline S3 FPS값에서 표본 수를 자동 유추하지 않는다.
모든 출력은 pandas.DataFrame 및 CSV 계약을 검사한다. 네트워크 차단은 Docker가 담당하며 코드만으로 주장하지 않는다.
시간 초과 후 container가 남는지 `docker ps -a --filter name=afda-offline`로 확인하고 해당 컨테이너만 중지한다.
로컬 메모리16GiB는 노트북 보호 한도이며 공식60GB 한도와 다르다. RTX5060 결과를 L40S 성능으로 발표하지 않는다.

## WSL2가 필요한 사용자 단계

[Microsoft 공식 설치 안내](https://learn.microsoft.com/en-us/windows/wsl/install)를 따라 관리자 PowerShell에서
`wsl --install -d Ubuntu-24.04`를 실행하고 필요할 때 직접 재부팅한다.
현재 세션에서는 관리자 승격이나 자동 재부팅을 하지 않았다. 펌웨어 가상화가 비활성화되어 있으면 먼저 켜야 한다.
WSL에서 `nvidia-smi`가 정상 동작한 뒤 Docker GPU 실행을 확인한다.

## 완료 조건

- Linux CPU: 실제 부팅, OS/Python 기록, 네트워크 분리된 테스트 로그.
- 모델 CUDA: 실제 학습 가중치 로딩, 세 Stage 전체 입력 처리, 출력 누락0, 반복 결과, 시간/RAM/VRAM 기록.
- 최종 제출: 필요한 추가 패키지 설치 제한과 크기·시간 조건까지 최신 공식 안내로 확인.

학습 가중치가 아직 없으므로 CUDA 세 Stage 전체 추론 게이트는 미실행이다.
