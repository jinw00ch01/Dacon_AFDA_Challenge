# Dacon_AFDA_Challenge

**AFDA = Accident Fraud Detection AI**

블랙박스 영상을 바탕으로 사고 분석에 필요한 단서를 추출하는 프로젝트입니다.
DACON의 [블랙박스 영상 기반 지능형 고의사고 분석 모델 AI 경진대회](https://www.dacon.io/competitions/official/236753/overview/description)를 대상으로,
영상 판별·사고 시점 분석·차량 상태 추정을 재현 가능한 학습 및 평가 과정으로 연결합니다.

| Stage | 목표 | 출력 |
|---|---|---|
| 1 | 원본과 화면 재촬영 영상 구분 | ID, answer |
| 2 | 충돌·진입 시점, 회피 공간과 진입 방향 분석 | ID, collision_frame, entry_frame, evasion_space, entry_side |
| 3 | 영상으로 가감속·조향 상태 추정 | ID, sample_index, accel_label, steer_label |

Stage 2는 원본 프레임 번호를 유지합니다. Stage 3의 실제 평가 입력은10Hz이며 정지 구간에도 조향 출력을 채웁니다.
CAN은 외부 학습 데이터의 정답 생성에 활용할 수 있지만 제출 추론은 영상만으로 동작해야 합니다.
출력은 사고 분석의 기술적 단서이며 그 자체가 고의성 판정은 아닙니다.

제출은 세 모델을 각각 올리는 방식이 아니라 세 추론 함수와 가중치를 담은 하나의 `submit.zip` 방식입니다.
서버가 비공개 입력으로 실행·채점합니다. 최신 조건은 [공식 평가 안내](https://www.dacon.io/competitions/official/236753/overview/evaluation)를 따릅니다.

현재 두 노트북 실행 하네스와 데이터 파일럿을 준비했습니다. 학습된 최종 모델과 대회 성능 점수는 아직 없습니다.
Linux Ubuntu CPU VM의 네트워크 분리 테스트18개와 GitHub Actions의 Linux/Windows 테스트를 통과했습니다.
실제 가중치를 이용한 CUDA 세 Stage 전체 추론은 다음 검증 단계입니다.
Pro 360은 데이터 정리·라벨 검수·CPU 테스트, Ultra는 GPU 실험·모델 검증·패키징을 담당합니다.

공개 저장소에는 직접 작성한 코드와 계획·출처를 올립니다. 영상·가중치·실행 로그·장치 식별자·공식 배포 원본은 별도 보관합니다.

계획: [docs/PLAN.md](docs/PLAN.md), 분석: [docs/CODE_REVIEW.md](docs/CODE_REVIEW.md),
사용자 작업: [docs/USER_ACTIONS.md](docs/USER_ACTIONS.md).
추가 문서: [데이터 확보](docs/DATA_ACQUISITION.md), [이용조건](docs/RESOURCE_LICENSES.md),
[Git 협업](docs/GIT_WORKFLOW.md), [Linux 검증 환경](environment/README.md).

## 저장소 구성과 데이터 파일럿

`harness/`는 실행·출력 계약·인계 검사, `configs/`는 역할별 자원 설정,
`scripts/`는 환경 설치·공개 데이터 확보·정렬, `requirements/`는 버전 고정,
`tests/`는 회귀 검사, `environment/`는 Linux 검증, `docs/`는 계획과 출처를 담습니다.

comma2k19 실제 주행 영상·센서, DoTA 주석, CCD 출처 문서를 합쳐49개 파일 약63.45MB를 확보했습니다.
comma 영상1,200프레임을 실제 디코드하고 타임스탬프로10Hz 연속 센서 타깃599행을 정렬했습니다.
이는 파이프라인 확인용이며 충분한 학습셋 또는 공식 클래스 정답은 아닙니다.
이후 comma 공식 배포본의 서로 다른 날짜24개 주행과 Nexar 공식 train 영상104개를 추가 확보했습니다.
Nexar 양성80개는 사고와 near-miss 혼합이며, 정상24개와 함께 직접 검수할 자료입니다.
추가 확보·이용조건·작업 경로는 [실제 영상 확보 실행안](docs/DATA_SOURCING_EXECUTION.md)과 [검증 결과](docs/DATA_ACQUISITION_RESULT.json)를 참고하세요.
사전학습 후보로 Apache2.0의 DINOv2 ViT-S/14 공식 가중치를 확보하고 안전한 state_dict 로딩을 확인했습니다.
대회용 미세조정과 영상 추론은 아직 수행하지 않았습니다.

```powershell
git clone https://github.com/jinw00ch01/Dacon_AFDA_Challenge.git
cd Dacon_AFDA_Challenge
# 아래 설치 뒤 역할에 맞는 Python으로 실행
.\.venv-pro360\Scripts\python.exe scripts/fetch_public_pilot.py
.\.venv-pro360\Scripts\python.exe scripts/prepare_public_pilot.py
```

수집기는 작성자 저장소의 고정 revision만 사용하고 Git blob 해시와 SHA-256을 기록합니다.
공식 Baseline은 사이트에서 직접 받아 로컬 `Baseline/`에 배치합니다.
원본 자료가 없는 새 clone에서는 `inventory`, `extract`, `bundle`에 추가 자료가 필요합니다.
`python -m unittest discover -s tests -v`는 원본 데이터 없이 실행할 수 있습니다.

## 설치 및 점검 (PowerShell)

```powershell
Set-Location C:\Dacon\Dacon_AFDA_Challenge
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap.ps1 -Role ultra5060
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1 -Role ultra5060
```

Pro 360에서는 두 명령의 역할을 `pro360`으로 바꿉니다. Python 3.12와 py launcher가 필요합니다.
실행 정책은 이 프로세스에서만 적용됩니다. 관리자 권한이나 영구 정책 변경은 필요하지 않습니다.

`py -3.12`가 없고 Python 3.12 x64 실행 파일이 따로 있다면 bootstrap에
`-PythonExecutable 'C:\path\to\python.exe'`를 전달할 수 있습니다. 기존 venv가 있으면
해당 환경을 사용하며 Python 3.12 x64인지 검사합니다. Pro 실물의 검증 현황은
로컬 실행 로그를 기준으로 확인합니다.

```powershell
$pythonPath = '.\.venv-ultra5060\Scripts\python.exe'
& $pythonPath -m harness extract
& $pythonPath -m harness inventory --profile ultra5060
& $pythonPath -m harness execute --profile ultra5060 --kind gpu --timeout 180 -- $pythonPath -m harness smoke --profile ultra5060
```

각 명령은 `runs/<UTC>_<command>_<id>/run.json`에 설정·코드 해시·상태를 기록합니다.
`execute`는 stdout/stderr, 프로세스 트리 RAM 표본 최대치, 시간 제한과 GPU 잠금을 추가합니다.
RAM은 0.2초 간격 표본이므로 순간 최대치를 놓칠 수 있습니다. GPU 잠금은 이 프로젝트의 execute 실행에만 적용됩니다.

## 출력 검사와 제출 구성

`check`는 모델 호출 없이 CSV 계약을 검사합니다. expected JSON은 평가 입력에서 별도로 만든 매니페스트입니다.
Stage 1은 `{"영상ID": null}`, Stage 2는 `{"사고ID": [0, 1, 2]}`처럼 실제 원본 프레임 번호 목록,
Stage 3은 `{"영상ID": 100}`처럼 검증된 10Hz 입력의 총 표본 수를 사용합니다.

```powershell
& $pythonPath -m harness check --stage stage2 --csv artifacts/stage2.csv --expected artifacts/stage2_expected.json
& $pythonPath -m harness package --inference src/baseline_inference.py --model-dir artifacts/model --output artifacts/submit_v001.zip
& $pythonPath -m harness preflight --zip artifacts/submit_v001.zip
```

위 package는 학습된 4개 모델 파일이 있어야 성공합니다. 현재 제출용 학습 모델은 없습니다.
ZIP 검사 범위는 파일 구조·크기·CRC·함수 서명입니다. 네트워크 차단, 가중치 호환성, 정확도와 실행시간 검증을 대신하지 않습니다.
패키저는 현재 베이스라인의 고정 파일 목록만 포함하므로 새 모델 자산을 추가할 때 목록/검증기도 함께 변경해야 합니다.

## 노트북 간 인계

```powershell
& $pythonPath -m harness bundle --include-samples --output artifacts/pro360_handoff_v001.zip
```

수신 PC의 새 작업 폴더에 압축 해제하고 `python -m harness verify-handoff --profile pro360`을 실행합니다.
검증은 수신 직후, 코드나 문서를 수정하기 전에 실행합니다. 수정 후 원본 manifest와의 불일치는
예상된 결과이며 기존 manifest를 덮어써 수신 증거를 바꾸지 않습니다.
venv·대형 캐시·개인 장치 정보·가중치·실행 로그는 제외됩니다. 설치 후 생성되는 파일은 무결성 검사 대상 원본 목록에 추가되지 않습니다.
데이터 전송은 이번에는 ZIP/USB 등으로 수동 인계하고, 이후 코드만 Git으로 동기화합니다.
두 PC의 동일 파일을 동시에 수정하거나 가상환경 폴더를 복사하지 않습니다.

## 다음 개발과 출처

사용자 실행 문서: [1인6시간30분 배정과 S23 Ultra 촬영](docs/LABELING_AND_S23_PLAN.md),
[Ultra WSL2/GPU 설치 순서](docs/WSL2_GPU_STEPS.md), [Pro 새 clone·검수·반환 명령](docs/PRO360_STEPS.md).

다수 주행·사고 그룹 확보 → Stage 2 수동 라벨 검수 → 저메모리 디코더/작은 학습 실험 →
그룹 분리 검증 → 실제 가중치 통합 추론 → Linux GPU 오프라인 검증 순서로 진행합니다.
공개 예제만으로 모델 성능을 주장하지 않습니다.

외부 자원은 [대회 규칙](https://www.dacon.io/competitions/official/236753/overview/rules)과 각각의 이용조건을 함께 따릅니다.
comma2k19·DoTA·CCD·KITTI 및 Torchvision 후보의 출처와 미완료 확인 사항은 이용조건 문서에 기록했습니다.
제3자 데이터·가중치를 이 프로젝트 코드와 같은 라이선스로 재배포하지 않습니다.
이 프로젝트 자체의 별도 오픈소스 라이선스는 아직 지정하지 않았습니다.
