# 사용자 후속 작업 — 두 노트북 왕복 인계 완료

## 완료된 일

- Ultra GPU 환경과 Pro 360 CPU 환경 설치·점검을 완료했다.
- Pro 반환 ZIP의 외부 SHA/내부29개 해시/CRC를 확인하고 공유 코드 수정을 Ultra에 적용했다.
- Ultra에서 테스트17개와 doctor/inventory/GPU smoke를 재검증했다. Pro 재설치나 같은 결과 재전송은 필요 없다.
- data_description.md를 공식 Baseline 데이터 설명으로 등록했다. 같은 자료를 다시 제공할 필요는 없다.
- 최초 pro360_handoff_v001.zip에는 공통 의존성 파일 누락이 있었으므로 새 PC 설치용으로 재사용하지 않는다. 현재 프로젝트의 bundle 명령은 수정됐다.

## 이번에 구체화한 사항

1. comma2k19 1분 실제 영상·센서와 DoTA 주석을 확보했다. 10Hz 연속 타깃599행, Stage2 검수 후보2,682개를 만들었다. 자세한 확보 방법과 인력 예산은 DATA_ACQUISITION.md에 있다.
2. comma2k19/DoTA/CCD/KITTI와 DINOv2/ResNet/MobileNet/MViT 후보의 출처·이용조건·보류 사유를 RESOURCE_LICENSES.md에 기록했다. Apache2.0 DINOv2 ViT-S/14 공식 가중치는 실제 확보·state_dict 로딩 확인했다. 다른 영상·가중치의 사용 조건이 모두 확정된 것은 아니다.
3. 사용자가 개인 참가라고 확인하여 팀 구성·병합 점검을 범위에서 제외했다. 공식 제출 마감은9월29일10:00, 종료는9월30일10:00, 2차 자료는10월5일10:00이다. https://www.dacon.io/competitions/official/236753/overview/schedule
4. 사용자가 생성한 jinw00ch01/Dacon_AFDA_Challenge 공개 저장소에 코드와 README를 게시했고 origin/main 추적을 연결했다. Git 사용법은 GIT_WORKFLOW.md를 따른다.
5. Linux CPU VM 준비와 CUDA 컨테이너/오프라인 추론 스크립트를 구성했다. 실제 검증 범위는 environment/README.md와 로컬 STATUS.md에 기록한다.

## 사용자가 직접 해야 할 일

- **제출 일정:** 개인 참가 기준9월29일10:00 전에 검증된 submit.zip을 제출한다. 현재 모델은 준비되지 않았으므로 제출 준비 완료 상태는 아니다.
- **라벨링 시간 배정:** 최소1인4~7시간을 제안한다(S2 50개 검수3~6시간, S1 실제 재촬영0.5~1시간, S3 정렬 검수0.5시간). 실제 가용 인력·시간은 사용자가 정한다.
- **물리적 촬영:** 허용된 독립 원본20~30개를 스마트폰으로 화면 재촬영한다. 원본과 파생은 같은 데이터 그룹으로 관리한다.
- **GPU Linux 준비:** 관리자 PowerShell에서 WSL2 설치와 필요한 재부팅/펌웨어 가상화 설정은 사용자가 수행한다. environment/README.md에 명령을 제공했다. CPU QEMU는 이 단계를 대체하지 않는다.
- **Pro 동기화:** 새 형제 폴더로 공개 저장소를 clone하고 기존 원본 자료를 로컬로 배치한다. 기존 venv 폴더는 복사하지 않는다.

영상 출처 조사, 소규모 다운로드, 출처 장부, 시간 정렬과 검수 후보 생성은 다시 사용자가 처음부터 할 필요 없다.

## 프로젝트의 다음 기술 작업

- D1: 공개 Stage3 영상의 컨테이너/라벨 시간축 대응 검수. 공식 평가 입력은10Hz로 확정됐으므로 두 문제를 구분한다. CAN은 추론 입력으로 요구하지 않는다.
- D2: Stage2 진입·회피·방향 라벨 가이드와 데이터 확보. 현재 -1 값을 임의 정답으로 바꾸지 않는다.
- D3: 같은 원본·파생·사고·주행이 학습/검증에 섞이지 않는 그룹 분할.
- M0: 위 자료가 준비되면 저메모리 decoder·CLI·AMP 학습 및 실제 checkpoint 검증.

Pro venv는 앱 번들 Python3.12를 기반으로 만들어졌다. 기반 런타임 경로가 사라지는 경우에만
Python3.12 x64 환경으로 재생성한다. CPU lock은 Ultra 환경에 설치하지 않는다.
