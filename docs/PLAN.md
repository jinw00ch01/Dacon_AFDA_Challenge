# 프로젝트 계획 및 두 노트북 하네스

## 목적과 순서

overview.md의 3-Stage 분석 모델을 만들기 전에, 환경/데이터/실험/검증/인계 경로를 고정한다.
기존 계획 파일은 없었으므로 이 문서를 최초 실행 계획으로 작성했다.
하네스는 역할별 환경, 실행 명령, 자원 한도, 입력·출력 계약, 재현 기록, 다음 작업의 연결을 뜻한다.
모델 학습 전체를 미리 수행하는 요청으로 확대하지 않는다.

## 장비별 역할

| 장비 | 담당 | 초기 자원 설정 | 인계 결과 |
|---|---|---|---|
| Pro 360 / i7-1360P / RAM16GB / Iris Xe | 데이터 조사, 라벨 검수, CPU 테스트, 보고서·코드 리뷰 | CPU4 threads, workers0, 작업 RSS6GiB, 캐시20GiB, 여유디스크20GiB 이상 | 데이터 출처표, 그룹 분할, 라벨, 검증된 코드 변경 |
| Ultra / Core Ultra7 / RAM32GB / RTX5060 8GB | GPU 실험, 특징 캐시, 모델 검증, 패키징 | batch1, workers0, CPU4 threads, 작업 RSS16GiB, 캐시80GiB, 여유디스크40GiB 이상 | checkpoint, run.json, 환경 lock, 예측·지표 |
| 추후 Linux/L40S 평가 유사 환경 | 오프라인 설치/전체 추론/최종 자원 측정 | 공식 CPU7/RAM60GB/VRAM44.7GiB 내 | 제출 후보 검증 기록 |

RAM 제한/타임아웃은 execute가 프로세스 트리에 적용한다. 캐시 한도는 운영 정책이며 자동 삭제하지 않는다.
batch/workers는 후속 학습 코드가 config를 읽어야 적용된다. 추출한 베이스라인은 원래 설정 그대로다.
GPU 작업은 Ultra에서 1개씩 실행한다. 두 노트북 간 분산학습은 초기 범위에 넣지 않는다.
CPU PC에서 소규모 ResNet forward를 하고 GPU PC에서 ResNet/MViT forward를 실행한다.
Pro 360 실물 설치·CPU 검증 결과를 반환 ZIP으로 수신했다. 무결성 및 공유 코드 재검증 결과는 STATUS.md에 기록한다.

## 실행 흐름

1. 사용자의 목적·공식 데이터 계약 → docs 및 AGENTS 규약.
2. bootstrap → venv → doctor → inventory → contract tests → synthetic smoke.
3. 실제 학습 전 데이터 registry/license/timebase/split을 확정.
4. 작은 실험 1개를 execute로 실행 → stdout/stderr·설정·코드 해시·시간·RAM 기록.
5. 동일 split에서 지표와 실패 사례 확인 → 승인된 다음 실험 한 가지 변경.
6. 가중치/추론 모듈을 package → 정적 preflight → 별도 Linux 오프라인 종단간 게이트.
7. 제출 및 2차 보고서에 필요한 데이터 출처·설계·실험 근거를 함께 축적.

## 환경 전략

- Python3.12 로컬 venv. 전역 Python의 torch nightly/numpy2/pandas3를 수정하지 않는다.
- Ultra torch2.8.0+cu128 / torchvision0.23.0+cu128, Pro는 동일 버전 CPU wheel.
- numpy1.26.4/pandas2.2.2/OpenCV headless4.10.0.84/Pillow10.4.0 등 문서 버전 사용.
- 설치 근거: [PyTorch 공식 이전 버전 안내](https://pytorch.org/get-started/previous-versions/)의 v2.8.0 설치 조합.
- 공통 직접 의존성 고정 + 검증된 실제 pip freeze를 requirements/ultra5060.lock.txt에 보관한다.
- CPU wheel lock은 Pro 360에서 별도로 생성한다. GPU lock을 CPU PC에 설치하지 않는다.
- 평가서버 기본 패키지를 제출 requirements에 중복 설치하지 않는다. 추가 의존성만 명시한다.
- 추가 요청에 따라 Linux 구성을 시도했다. WSL 설치 명령은 실패했고, 관리자 재부팅 없는 QEMU CPU 검증과 CUDA 컨테이너 실행 경로를 준비했다. environment/README.md 참조.

## 단계별 완료 조건

| 단계 | 실행 내용 | 완료 조건 |
|---|---|---|
| H0 (이번) | 코드 분석, 역할 설정, Ultra venv, 테스트/진단, Pro 인계 자료 | 로컬 근거 저장, 사용자 작업표, Pro 실제 실행 여부 구분 |
| H1 | Pro 설치 및 왕복 인계, 코드 변경 동기화 | Pro doctor/inventory/tests/CPU smoke, 인계 SHA 검증, 1개 결과 왕복 |
| D0 | Stage 정의/외부 데이터 허용/시간축 확인·라벨 계획 | S3 매핑 확정, 출처·라이선스 기록, scene group 기반 분할 |
| M0 | 베이스라인 CLI 이관 및 저메모리 데이터 파이프라인 | 유한 버퍼·클립 선택 디코드, batch1 AMP 실측, 체크포인트 round trip |
| M1 | Stage별 학습/검증 개선 | S2 미라벨 masking과 실제 새 라벨, S3 다수 클래스 편향 점검, S1 실제 재촬영 검증 |
| E0 | 3개 Stage 통합/추론 튜닝 | 누락·중복0, 범주/프레임/표본 계약, 원본 입력 불변, 재실행 일관성 |
| S0 | Linux 오프라인 최종 검증 | 설치10분/전체60분/크기 제한/모든 모델 로딩/외부 접근 없음 |

단계는 달력 추정보다 완료 조건으로 관리한다. 외부 데이터 허용 범위와 라벨링 양이 확정되면 일정 산정한다.
공개 Git은 사용자가 지정한 jinw00ch01/Dacon_AFDA_Challenge로 연결한다. 데이터 계획/조건은 DATA_ACQUISITION.md와 RESOURCE_LICENSES.md를 기준으로 한다.
우선순위는 Stage2/3(각 0.4) 데이터 타당성과 시간축, 다음 Stage1(0.2) 원본-재촬영 일반화다.
공개 예제만으로 순위/정확도 목표치를 제시하지 않는다.

## 공식 데이터 설명 반영

사용자가 공식 Baseline 데이터 설명으로 지정한 data_description.md를 데이터 계약 근거에 추가했다.
별도 학습 데이터셋은 제공되지 않는다. Baseline 공개 예제는 실행·형식 점검에 사용하며,
실제 성능 학습용 데이터는 이용조건을 확인하여 직접 구성한다.
Stage1은 영상당 ORIGINAL/RERECORDED, Stage2는 사고별 이미지 폴더와 파일명의 원본 프레임 번호,
Stage3는 10Hz 영상과 0부터 시작하는 0.1초 단위 sample_index를 기준으로 한다.
CAN은 평가 정답 생성용이며 비공개 추론 입력이 아니다.
Stage3 공개 예제의 컨테이너/라벨 시간축 불일치를 비공개 평가 입력의 FPS 문제로 일반화하지 않는다.

## 협업·하네스 운영

- 이번 인계는 sample 포함 ZIP과 SHA manifest를 사용한다. 개인 장치 ID가 든 pc_info.md는 인계/버전 관리에서 제외한다.
- Git 저장소는 초기화하고 .gitignore를 적용하되 원격 공개/계정 연결/자동 push는 하지 않는다.
- 원격 저장소를 사용한다면 사용자가 private remote를 정한 뒤 초기 commit과 push를 별도 수행한다.
- 작업 소유자는 docs/TASKS.md에서 정하고 파일 소유권을 나눈다. 같은 파일을 두 PC가 동시에 편집하지 않는다.
- 코드만 Git, 데이터/가중치는 체크섬을 가진 버전 묶음으로 공유한다. venv는 각 PC에서 새로 만든다.
- 긴 작업은 execute 사용. 실패 시 원본을 지우거나 랜덤 가중치로 조용히 대체하지 않는다.
- 인계 메시지: 작업ID / 입력버전·SHA / 실행명령 / 변경파일 / 결과 run / 실패·제약 / 다음 한 단계.
- 실험 ledger에는 seed뿐 아니라 split/data/checkpoint/config/code SHA, 패키지 lock, 지표 정의도 연결한다.
- sample smoke와 학습 성능 보고서는 분리한다. 데이터 추가 전에 개인정보·사용권 근거를 registry에 기록한다.
