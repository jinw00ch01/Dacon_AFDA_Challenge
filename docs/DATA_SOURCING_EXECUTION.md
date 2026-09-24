# 실제 영상 확보 실행안 — 2026-09-24

사용자가 영상을 처음부터 찾아다닐 필요가 없도록, 출처 선정·수집 코드·작업 순서를 정했다.
일반 주행은 comma2k19를 직접 확보하고, 사고 후보는 Nexar 공식 배포본을 우선한다.
실제 수집 수량과 검사 결과는 DATA_ACQUISITION_RESULT.json을 기준으로 한다.

## 1. 무엇을 어디서 확보하는가

| 용도 | 선정한 원천 | 확보 단위 | 판단 근거 |
|---|---|---|---|
| S1 화면 재촬영 원본 | comma.ai 공식 comma2k19 | 서로 다른 날짜 24개, 각 약1분; 10초 재생용 MP4 24개 제작 | 공식 데이터 카드 MIT, 라이선스 원문 보관 |
| S3 영상 기반 속도·조향 보조 학습 | 위와 같은 comma2k19 | 각 영상의 frame_times, CAN speed/steering timestamp/value | 영상과 센서가 함께 있어 사람이 연속값을 추측할 필요가 없음 |
| S2 실제 사고 후보 | Nexar 공식 Nexar Collision Prediction | 양성80개 + 정상24개, 영상 합계1,796,382,995바이트 | 자체 블랙박스 자료, 데이터 자체의 사용·수정·배포 조건 명시 |

공식 출처: [comma2k19 데이터 카드](https://huggingface.co/datasets/commaai/comma2k19/blob/main/README.md),
[comma2k19 MIT 원문](https://github.com/commaai/comma2k19/blob/master/LICENSE),
[Nexar 데이터](https://huggingface.co/datasets/nexar-ai/nexar_collision_prediction),
[Nexar 이용조건](https://huggingface.co/datasets/nexar-ai/nexar_collision_prediction/blob/main/LICENSE).

comma2k19는 특정 캘리포니아 고속도로와 제한된 차량에서 얻은 자료다. 서로 다른 날짜를 분리해도 한국 도로·차종·도심 상황을 포괄하지 않는다.
Nexar 양성은 실제 충돌과 near-miss가 섞여 있다. 사고80개 확보 또는 DACON 정답80개 확보로 표현하지 않는다.
S2용 접촉/진입/방향/회피 공간 라벨과 고의성 정답은 자동으로 제공되지 않는다. 사고만 보고 고의라고 라벨링하지 않는다.

## 2. 이용조건에 대한 사용 결정

- comma2k19: 공식 데이터 카드의 MIT 표기와 프로젝트 MIT 원문을 보존한다. 라이선스·저작권 표시를 유지하며 영상 변환/화면 재촬영의 원천으로 사용한다. 원본은 수정하지 않고 파생 경로와 해시를 별도 기록한다.
- Nexar: **현재는 MIT가 아닌 Nexar Open Data License**다. 출처 인용과 재배포 시 고지 보존, 영리 재판매 금지, 재식별·유해/무기 목적·부당한 보험 활용 등 제한을 준수하는 사고 분석 연구용으로 선정했다. 변형 미디어 관련 조항 때문에 이번 S1 재촬영/합성 원천에는 배정하지 않는다.
- Nexar는 웹페이지가 공개되어도 파일 접근에는 로그인과 연락처 공유를 포함한 조건 동의가 필요하다. 실제 익명 영상 요청은 HTTP401로 실패했다. 타인 미러·우회 경로로 접근 제한을 피하지 않는다.
- 대회는 공개 접근 가능한 자원, 최소 비영리 이용 허용, 개별 조건 확인 및 출처 기록을 요구한다. Nexar의 계정 동의형 접근이 대회의 공개 자원 기준에 부합하는지 운영상 의문이 있으면 주최 측에 확인한다. 계정 승인이 대회 운영자의 별도 적합성 승인을 뜻하지는 않는다.
- 2차 자료는 학습 데이터 파일도 포함하도록 안내되어 있다. 원본 재배포 조건과 고지를 함께 보관한다. 공개 Git에는 영상·센서·가중치·개인정보를 게시하지 않는다.

근거: [DACON 규칙](https://www.dacon.io/competitions/official/236753/overview/rules).

## 3. Nexar 계정 연결 및 재다운로드 방법

현재 사용자가 웹 접근 신청과 PC OAuth 인증을 완료했다. 같은 PC에서는 다시 로그인할 필요 없이 유효한 인증으로 다운로드한다.
아래1~4는 다른 PC에서 처음 접근하거나 인증이 만료된 경우의 절차다.

1. [Nexar 공식 데이터 페이지](https://huggingface.co/datasets/nexar-ai/nexar_collision_prediction)를 연다.
2. Hugging Face 계정으로 로그인한다. 없으면 무료 계정을 만들고 필요한 이메일 확인을 마친다.
3. 데이터 접근 조건과 연락처 공유 항목을 읽고 본인이 동의할 경우 접근 요청한다. 승인 소요시간은 보장하지 않는다.
4. 페이지에서 train 파일에 접근할 수 있게 되면, Ultra의 일반 PowerShell에서 아래 로그인 명령을 실행한다. 브라우저 로그인 방식이 제시되면 안내된 페이지와 코드로 본인이 로그인한다. 토큰 방식이면 토큰은 로컬 입력창에만 입력한다.

현재 Ultra에는 다운로드 전용 `.venv-data-tools`를 별도로 준비했다. 학습 venv의 torch/의존성은 바꾸지 않았다.

```powershell
Set-Location C:\Dacon\Dacon_AFDA_Challenge
.\.venv-data-tools\Scripts\hf.exe auth login
```

로그인과 데이터 접근 승인은 별도 단계다. 토큰·비밀번호는 채팅, Git, 실행 명령 인수에 넣지 않는다.
[HF 공식 CLI 안내](https://huggingface.co/docs/huggingface_hub/guides/cli), [접근 신청형 데이터 안내](https://huggingface.co/docs/hub/datasets-gated).

승인 및 로컬 로그인이 끝나면 아래 명령으로104개를 받는다. 사용자 요청에 따라 후속 실행을 에이전트에게 맡겨도 된다.

```powershell
.\.venv-ultra5060\Scripts\python.exe -m harness execute --profile ultra5060 --kind cpu --timeout 3600 -- .\.venv-data-tools\Scripts\python.exe scripts/fetch_nexar_subset.py
```

출력은 `data/external/nexar_subset_v1/`이다. train 폴더만 사용하며 Nexar test-public/test-private는 받지 않는다.
전체 배포본을 무작정 받지 않고 고정 revision/seed로 정한 목록, CSV 원주석, README/LICENSE를 받는다.
공식 LFS SHA-256을 대조하며 정답이 빈 `stage2_candidates.csv`를 생성한다. 학습용 최종 라벨은 아직 아니다.
전체 디코딩 검증 뒤에는 `data/derived/nexar_subset_v1/stage2_review_with_metadata.csv`를 실제 작업표로 사용한다. source_time_of_event_seconds는 원 데이터의 사고/near-miss 시각이며 DACON 충돌 정답으로 자동 복사하지 않는다.

다른 PC에서 전용 도구 환경이 필요할 때만:

```powershell
# 해당 PC의 정상 작동하는 Python 3.12 경로로 실행한다.
& $pythonPath -m venv .venv-data-tools
.\.venv-data-tools\Scripts\python.exe -m pip install -r requirements/data-tools.txt
```

## 4. 다운로드 뒤의 작업 배정

### S1: 이미 정한 촬영 계획에 실제 파일 연결

`data/derived/comma_subset_v1/s1_playback/SRC001_ORIGINAL.mp4`부터24개를 사용한다.
`s23_capture_ready.csv`에는 원본 경로·출처·주행 그룹·16/4/4 분할이 채워진다.
이를 이전 빈 계획표 대신 사용하고, S23로 실제 촬영한 파일명·설정·SHA만 추가한다.
촬영 계획은 LABELING_AND_S23_PLAN.md의48회/90분 그대로다. 10초 재생본도 원본에서 만든 파생이며 전체1분 HEVC는 별도 보존한다.

### S2: 확보한 자료의 30~45분 선별, 이후 250분 라벨링

1. 양성80개를 실제 접촉/near-miss/판단불가로 먼저 나눈다. near-miss에 충돌 프레임을 만들지 않는다.
2. 실제 접촉 영상 중 옆 차선 진입 과정과 필요한 프레임이 보이는 것을 우선 골라30~50개 목표로 검수한다. 소스 안에 해당 사례가 충분하다는 보장은 없다.
3. 전후 맥락이 잘린 영상, 차선 경계가 안 보이는 영상, 접촉 여부가 모호한 영상은 해당 라벨을 비워 둔다.
4. 정상24개는 음성 후보로 활용하되 정상 영상에 임의의 사고/진입 프레임을 붙이지 않는다.
5. 장면·차량·시간·유사 프레임으로 중복을 확인한 뒤 사건 그룹을 확정하고, 동일 사건은 같은 split에 둔다. 파일 ID가 다르다는 이유만으로 독립 사건으로 가정하지 않는다.

기존6시간30분 예산은 촬영·라벨링·검수 예산이다. 새 사고 자료 선별30~45분과 계정/다운로드 대기는 별도다.
독립30개 미만이면 후속 배치로 양성 후보를 확대하며 미정의 항목을 임의 정답으로 채워 수량을 맞추지 않는다.

### S3: 자동 정렬값 검수 후 공식 클래스 매핑

`s3_auxiliary_10hz.csv`는 영상 timestamp와 CAN을 정렬한 연속 보조 타깃이다.
같은 센서 시각에 중복 측정값이 있는 경우 평균으로 합치고 처리 개수와 최대 차이를 기록한다. 원 센서 파일은 보존한다.
SRC014는 프레임 대응 오차가30ms 기준을 초과하여 S3 타깃에서 전체 제외한다. S1 재생용으로는 사용할 수 있다.
촬영용 MP4는20fps로 통일한 파생본이며 S3 타깃은 이 MP4가 아닌 원본 프레임 타임스탬프에서 생성한다.
공식 속도/조향 클래스 정답이나 실제 CAN 없는 추론 입력으로 혼동하지 않는다. CAN은 학습 타깃 생성에만 사용한다.
정지·급조향 등 클래스 분포를 확인한 뒤 필요한 경우 추가 날짜/상황을 확보한다.

## 5. Nexar를 사용할 수 없을 때

계정 동의가 불가능하면 이번에 받은 comma 자료로 S1/S3를 먼저 진행한다. S2는 억지로 대체 라벨을 만들지 않는다.

대안1: DoTA 작성자 배포 영상을 검토한다. 저장소 MIT와 원 채널 공유 허가 설명은 있지만, 대회 학습 및 2차 데이터 제출까지의 영상 이용 범위 확인이 아직 충분하지 않다.
작성자에게 확인할 질문은 아래와 같으며 **아직 발송하지 않았다**.

> May I use the DoTA video files to train a non-commercial model for the DACON Accident Fraud Detection AI competition, and provide the used video subset with attribution to the organizers for reproducibility review? Are these uses covered by the video permissions you obtained, and are there additional restrictions beyond the repository license?

대안2: 사용자가 권리를 가진 블랙박스 원본 또는 촬영자로부터 학습·변환·대회 검증 제출 허가를 받은 자료. 출처·허가 범위를 서면 기록한다. 새 사고 상황을 연출하거나 위험 운전을 하지 않는다.
무작위 유튜브 다운로드·불명확한 재업로드 모음·인터넷에 공개됐다는 이유만으로 사용 허가를 가정하는 방법은 이번 확보 경로로 선택하지 않았다.

## 재현 명령: 일반 주행 원본

```powershell
.\.venv-ultra5060\Scripts\python.exe -m harness execute --profile ultra5060 --kind cpu --timeout 1800 -- .\.venv-ultra5060\Scripts\python.exe scripts/fetch_comma_subset.py --count 24
$ffmpegPath = (& .\.venv-data-tools\Scripts\python.exe -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())").Trim()
.\.venv-ultra5060\Scripts\python.exe -m harness execute --profile ultra5060 --kind cpu --timeout 1800 -- .\.venv-ultra5060\Scripts\python.exe scripts/prepare_comma_subset.py --ffmpeg $ffmpegPath
```

기존 원본은 SHA가 일치할 때만 재사용한다. 파생 폴더가 이미 있으면 준비 스크립트는 덮어쓰지 않고 중단한다.
전체 약95GB 대신 공개 ZIP의 필요한 바이트 범위만 읽는다. 서버 범위 응답·ZIP CRC·로컬 SHA-256을 검사한다.
전체 ZIP을 받지 않았으므로 기록된 ZIP 전체 배포자 SHA를 검증했다고 주장하지 않는다.
