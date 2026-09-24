# Pro 360: 새 clone부터 데이터 검수·반환까지

일반 PowerShell에서 아래 블록을 순서대로 실행한다. 관리자 권한이나 WSL은 필요 없다.
기존 폴더 `C:\Dacon\Dacon_AFDA_Challenge`는 보존하고 새 폴더 `C:\Dacon\Dacon_AFDA_Challenge_git`를 사용한다.
Pro는 CPU 환경 점검, 출처·라벨 검수, S23 촬영표와 S3 정렬 검수를 맡는다. GPU 학습·최종 패키징은 Ultra 담당이다.

## 1. 여유 자원 확인과 새 clone

불필요한 브라우저·앱을 닫고 시작한다. 사용 가능 RAM 3GB 이상을 권장하며 디스크는 20GB 이상을 유지한다.

```powershell
$ErrorActionPreference = 'Stop'
$oldRoot = 'C:\Dacon\Dacon_AFDA_Challenge'
$newRoot = 'C:\Dacon\Dacon_AFDA_Challenge_git'
git --version
if ($LASTEXITCODE -ne 0) { throw 'Git for Windows 설치를 먼저 확인하세요.' }
Get-PSDrive C | Select-Object Name, @{N='FreeGB';E={[math]::Round($_.Free / 1GB, 1)}}
$memoryInfo = Get-CimInstance Win32_OperatingSystem
[math]::Round($memoryInfo.FreePhysicalMemory / 1MB, 1)
if (Test-Path -LiteralPath $newRoot) { throw '새 폴더가 이미 있습니다. 아래의 재개 절차를 사용하세요.' }
git clone https://github.com/jinw00ch01/Dacon_AFDA_Challenge.git $newRoot
if ($LASTEXITCODE -ne 0) { throw 'clone 실패: 이후 단계를 중단합니다.' }
Set-Location -LiteralPath $newRoot
git remote -v
```

재개하는 경우에만 아래를 실행한다. status에 변경이 있으면 덮어쓰거나 reset하지 말고 먼저 검수 자료와 변경을 보존한다.

```powershell
$oldRoot = 'C:\Dacon\Dacon_AFDA_Challenge'
$newRoot = 'C:\Dacon\Dacon_AFDA_Challenge_git'
Set-Location -LiteralPath $newRoot
git status --short
git pull --ff-only
```

공개 저장소 읽기/clone에는 로그인이 필요 없다. Git이 없다면 [Git for Windows 공식 설치](https://git-scm.com/downloads/win) 후 새 PowerShell을 연다.

## 2. 기존 Python의 기반 실행 파일로 새 venv 만들기

Pro의 기존 venv는 정상 검증되었지만 py 런처는 없었다. 기존 venv를 실행하여 기반 Python 위치를 찾는다.
venv 폴더를 복사하는 작업은 아니다. 기반 런타임이 사라졌을 때만 Python 3.12 x64를 별도 설치하고 $basePython을 그 실행 파일로 바꾼다.

```powershell
$oldPython = Join-Path $oldRoot '.venv-pro360\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $oldPython)) { throw '기존 Pro Python 경로를 확인하세요.' }
$basePython = (& $oldPython -c "import sys; print(sys._base_executable)").Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $basePython)) { throw '기반 Python 3.12 x64를 찾지 못했습니다.' }
& $basePython -c "import sys,struct; print(sys.version); assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 x64가 필요합니다.' }
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1 -Role pro360 -PythonExecutable $basePython
if ($LASTEXITCODE -ne 0) { throw '환경 설치 실패: 출력 오류부터 해결하세요.' }
$pythonPath = Join-Path $newRoot '.venv-pro360\Scripts\python.exe'
& $pythonPath -m pip check
```

bootstrap은 새 `.venv-pro360`에 CPU torch 2.8.0/torchvision 0.23.0과 공통 의존성을 설치한다.
기존 앱 기반 런타임은 추후 제거될 수 있으므로 그때는 venv를 재생성한다. 전역 Python 설정은 바꾸지 않는다.

## 3. 필요한 Baseline과 참조 문서만 로컬 복사

새 clone에는 대회 원본 영상이 없다. 아래는 기존 Baseline/data와 원본 노트북·설명만 복사한다.
목적지에 파일이 있으면 중단하므로 최초 복사 때만 실행한다. 모델·venv·기존 runs는 복사하지 않는다.

```powershell
$sourceData = Join-Path $oldRoot 'Baseline\data'
$targetBaseline = Join-Path $newRoot 'Baseline'
$targetData = Join-Path $targetBaseline 'data'
if (-not (Test-Path -LiteralPath $sourceData)) { throw '기존 Baseline/data 위치를 확인하세요.' }
if (Test-Path -LiteralPath $targetData) { throw '새 폴더에 이미 데이터가 있습니다. 기존 복사본부터 확인하세요.' }
New-Item -ItemType Directory -Path $targetBaseline -Force | Out-Null
Copy-Item -LiteralPath $sourceData -Destination $targetData -Recurse
Get-ChildItem -LiteralPath (Join-Path $oldRoot 'Baseline') -File | Where-Object { $_.Extension -eq '.ipynb' -or $_.Name -eq 'requirements.txt' } | ForEach-Object {
    $destination = Join-Path $targetBaseline $_.Name
    if (Test-Path -LiteralPath $destination) { throw "기존 파일 보존: $destination" }
    Copy-Item -LiteralPath $_.FullName -Destination $destination
}
foreach ($referenceName in @('overview.md','evaluation.md','data_description.md')) {
    $source = Join-Path $oldRoot $referenceName
    $destination = Join-Path $newRoot $referenceName
    if ((Test-Path -LiteralPath $source) -and -not (Test-Path -LiteralPath $destination)) {
        Copy-Item -LiteralPath $source -Destination $destination
    }
}
& $pythonPath -m harness execute --profile pro360 --kind cpu --timeout 600 -- powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1 -Role pro360
if ($LASTEXITCODE -ne 0) { throw 'Pro 종합 점검 실패: runs의 stderr를 확인하세요.' }
```

기대 결과: 현재 회귀 테스트21개, doctor, Baseline20영상 inventory, CPU synthetic smoke 통과.
이는 새 clone의 실행 점검이며 모델 정확도 검증은 아니다.

## 4. 소규모 자료와 검수 세션 생성

인터넷 연결 상태에서 진행한다. 약 63.5MB 파일럿이며, 전체 DoTA 사고 영상이나 S1 독립 원본 24개를 내려받는 명령은 아니다.
fetch는 출처·해시를 검증하며, prepare는 센서 정렬과 미라벨 후보를 만든다.

```powershell
& $pythonPath -m harness execute --profile pro360 --kind cpu --timeout 900 -- $pythonPath scripts/fetch_public_pilot.py
if ($LASTEXITCODE -ne 0) { throw '공개 파일럿 확보 실패' }
& $pythonPath -m harness execute --profile pro360 --kind cpu --timeout 300 -- $pythonPath scripts/prepare_public_pilot.py
if ($LASTEXITCODE -ne 0) { throw '파일럿 정렬 실패' }
& $pythonPath -m harness execute --profile pro360 --kind cpu --timeout 180 -- $pythonPath scripts/prepare_review_session.py --session pro_20260924 --with-frames
if ($LASTEXITCODE -ne 0) { throw '새 세션명 또는 실행 오류를 확인하세요.' }
$reviewRoot = Join-Path $newRoot 'data\derived\review_sessions\pro_20260924'
explorer.exe $reviewRoot
```

이미 세션이 있으면 마지막 생성 명령을 반복하지 않고 기존 폴더를 연다. 새 세션이 필요할 때만 이름을 바꾼다.

## 5. Pro에서 실제로 할 일

2026-09-24 추가 확보: Ultra에 comma24개와 Nexar104개 실제 영상이 있다. 공개 Git에는 영상이 없으므로 USB 등으로 필요한 data 하위 경로를 그대로 복사한다.
S1은 `data/derived/comma_subset_v1/`, S2는 `data/external/nexar_subset_v1/train/` 및 `data/derived/nexar_subset_v1/`를 사용한다.
원본의 LICENSE/README/manifest도 함께 보존한다. S3 원 센서를 재검증하려면 `data/external/comma2k19_subset_v1/`도 복사한다.

1. **지금 가능:** 위 설치·점검 후 Ultra의 새 실제 영상 자료를 수신한다. 기존 DoTA 파일럿 CSV는 여전히 영상 없는 후보이며 Nexar 작업표와 섞지 않는다.
2. **S3 30분:** stage3_alignment_20.csv와 stage3_frames/의 20장을 대조한다. 프레임 번호는 0기반이며 시간/센서 간격도 확인한다. alignment_ok를 확인한 행만 채우고 notes에 문제를 기록한다. 공식 분류 정답을 새로 만든 것으로 표시하지 않는다.
3. **S1 90분:** LABELING_AND_S23_PLAN.md에 따라 양쪽 화면과 S23 Ultra로48테이크 촬영. `data/derived/comma_subset_v1/s23_capture_ready.csv`에 실제 촬영값·휴대폰 파일명·해시를 추가한다. 원본과 파생은 같은 split으로 묶는다.
4. **S2 선별30~45분 + 검수250분:** `data/derived/nexar_subset_v1/stage2_review_with_metadata.csv`를 사용한다. 실제 접촉/near-miss를 나누고 차선 진입이 보이는 사례를 우선한다. 실제 원본 프레임 번호와 추출 이미지 파일명의 대응을 확인한다. 불확실 항목은 빈칸과 이유를 남기며 다음 날10개를 가리고 재검수한다.
5. **반환:** 검수 CSV·S3 표본 이미지·session.json·문제 메모를 ZIP으로 Ultra에 전달한다. 영상 원본은 별도 USB 폴더로 전달한다. Pro에서 DINO/MViT 전체 학습을 시작하지 않는다.

S2용 전문 프레임 라벨링 UI는 아직 구현하지 않았다. 후보 CSV 생성은 라벨링 도구나 실제 정답 확보 완료를 뜻하지 않는다.
6시간 30분의 상세 배정과 품질에 따른 물량 조정은 LABELING_AND_S23_PLAN.md를 따른다.

## 6. 검수 결과 ZIP과 SHA 만들기

아래 session.json은 생성 당시 수량이다. 완료 라벨 수는 사람이 검수한 CSV에서 다시 집계해야 한다.
CSV 편집은 UTF-8로 저장하고 열 이름·프레임 번호를 유지한다. 메모도 검수 폴더 안에 넣는다.

```powershell
$reviewRoot = Join-Path $newRoot 'data\derived\review_sessions\pro_20260924'
$artifactRoot = Join-Path $newRoot 'artifacts'
New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$handoffZip = Join-Path $artifactRoot "pro_review_$stamp.zip"
Compress-Archive -LiteralPath $reviewRoot -DestinationPath $handoffZip
$digest = (Get-FileHash -LiteralPath $handoffZip -Algorithm SHA256).Hash.ToLowerInvariant()
"$digest  $([IO.Path]::GetFileName($handoffZip))" | Set-Content -LiteralPath ($handoffZip + '.sha256') -Encoding ascii
Get-Item -LiteralPath $handoffZip
```

ZIP과 sha256을 함께 USB 등으로 Ultra에 전달한다. 검수 데이터는 공개 Git에 올리지 않는다.
실행 증거가 필요한 경우 해당 runs의 run.json/stdout/stderr만 별도 전달하며 장치 식별 정보가 있을 수 있어 공개하지 않는다.
코드 변경이 필요할 때는 GIT_WORKFLOW.md에 따라 별도 브랜치에서 해당 파일만 add한다. 이번 데이터 작업에는 Git commit/push가 필수가 아니다.
