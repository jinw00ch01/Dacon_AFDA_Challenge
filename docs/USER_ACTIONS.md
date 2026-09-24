# 사용자 후속 작업 — 두 노트북 왕복 인계 완료

## 완료된 일

- Ultra GPU 환경과 Pro 360 CPU 환경 설치·점검을 완료했다.
- Pro 반환 ZIP의 외부 SHA/내부29개 해시/CRC를 확인하고 공유 코드 수정을 Ultra에 적용했다.
- Ultra에서 테스트17개와 doctor/inventory/GPU smoke를 재검증했다. Pro 재설치나 같은 결과 재전송은 필요 없다.
- data_description.md를 공식 Baseline 데이터 설명으로 등록했다. 같은 자료를 다시 제공할 필요는 없다.
- 최초 pro360_handoff_v001.zip에는 공통 의존성 파일 누락이 있었으므로 새 PC 설치용으로 재사용하지 않는다. 현재 프로젝트의 bundle 명령은 수정됐다.

## 이번에 구체화한 사항

1. 초기 comma1분/DoTA 주석 파일럿 이후, comma의 서로 다른 날짜24개 영상·센서와 Nexar train 영상104개를 추가 확보했다. 실제 결과는 DATA_ACQUISITION_RESULT.json, 사용 순서는 DATA_SOURCING_EXECUTION.md에 있다. 주석만 받은 DoTA와 실제 영상이 있는 Nexar를 구분한다.
2. comma2k19/DoTA/CCD/KITTI와 DINOv2/ResNet/MobileNet/MViT 후보의 출처·이용조건·보류 사유를 RESOURCE_LICENSES.md에 기록했다. Apache2.0 DINOv2 ViT-S/14 공식 가중치는 실제 확보·state_dict 로딩 확인했다. 다른 영상·가중치의 사용 조건이 모두 확정된 것은 아니다.
3. 사용자가 개인 참가라고 확인하여 팀 구성·병합 점검을 범위에서 제외했다. 공식 제출 마감은9월29일10:00, 종료는9월30일10:00, 2차 자료는10월5일10:00이다. https://www.dacon.io/competitions/official/236753/overview/schedule
4. 사용자가 생성한 jinw00ch01/Dacon_AFDA_Challenge 공개 저장소에 코드와 README를 게시했고 origin/main 추적을 연결했다. Git 사용법은 GIT_WORKFLOW.md를 따른다.
5. Linux CPU VM 준비와 CUDA 컨테이너/오프라인 추론 스크립트를 구성했다. 실제 검증 범위는 environment/README.md와 로컬 STATUS.md에 기록한다.

## 사용자가 직접 해야 할 일

- **제출 일정:** 개인 참가 기준9월29일10:00 전에 검증된 submit.zip을 제출한다. 현재 모델은 준비되지 않았으므로 제출 준비 완료 상태는 아니다.
- **시간 배정 완료:** 1인 총6시간30분으로 계획을 확정했다. S2 4시간10분, S1 1시간30분, S3 30분, 휴식20분. 첫날4시간10분/다음날2시간20분의 상세 순서와 물량 조정 기준은 [LABELING_AND_S23_PLAN.md](LABELING_AND_S23_PLAN.md)를 따른다. 영상 확보·설치 대기시간은 별도다.
- **물리적 촬영:** 확보한 comma24개에서 만든 MP4를 S23 Ultra로 각2회, 총48회 촬영한다. `data/derived/comma_subset_v1/s23_capture_ready.csv`의 실제 경로와 조건을 따른다.
- **S2 선별·라벨링:** Nexar104개 검수표에서 실제 접촉·차선 진입 적합 사례를30~50개 선별한다. 원본80개 양성은 near-miss도 포함한다. 선별30~45분은 기존 수동 작업6시간30분에 별도 추가한다. Hugging Face 웹 신청과 PC 인증은 사용자가 완료했으므로 반복하지 않는다.
- **GPU Linux 준비:** [WSL2_GPU_STEPS.md](WSL2_GPU_STEPS.md)의 관리자 PowerShell → 재부팅 → Ubuntu 설치/검증 순서를 따른다. WSL CUDA 연산과 최종 모델 오프라인 추론을 별도 완료 조건으로 관리한다.
- **Pro 동기화·검수:** [PRO360_STEPS.md](PRO360_STEPS.md)에 새 형제 폴더 clone, 기존 기반 Python 찾기, 새 CPU venv, 원본 자료 복사, 검수 세션 생성과 ZIP 반환 명령을 제공했다. 기존 venv는 복사하지 않는다.

영상 출처 조사, 소규모 다운로드, 출처 장부, 시간 정렬과 검수 후보 생성은 다시 사용자가 처음부터 할 필요 없다.

## 프로젝트의 다음 기술 작업

- D1: 공개 Stage3 영상의 컨테이너/라벨 시간축 대응 검수. 공식 평가 입력은10Hz로 확정됐으므로 두 문제를 구분한다. CAN은 추론 입력으로 요구하지 않는다.
- D2: Stage2 진입·회피·방향 라벨 가이드와 데이터 확보. 현재 -1 값을 임의 정답으로 바꾸지 않는다.
- D3: 같은 원본·파생·사고·주행이 학습/검증에 섞이지 않는 그룹 분할.
- M0: 위 자료가 준비되면 저메모리 decoder·CLI·AMP 학습 및 실제 checkpoint 검증.

Pro venv는 앱 번들 Python3.12를 기반으로 만들어졌다. 기반 런타임 경로가 사라지는 경우에만
Python3.12 x64 환경으로 재생성한다. CPU lock은 Ultra 환경에 설치하지 않는다.
