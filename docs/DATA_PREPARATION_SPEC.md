# 라벨링·전처리 시작 전 데이터 처리 명세

작성: 2026-09-25. 이 문서의 체크 항목은 준비 완료 주장과 구분한다. 아래 현황은 Ultra 작업본과 2026-09-24 수집·검증 기록을 기준으로 한다. Pro에서 아직 반환하지 않은 작업까지 없다고 단정하지 않는다.

## 1. 이미 있는 자료와 아직 없는 정답

| 자료 | 확보 상태 | 지금 사용할 수 있는 범위 | 다음 조건 |
|---|---|---|---|
| Baseline 공개 예제 | 로컬 배포본 | 실행·출력 형식 점검 | 실제 학습셋으로 취급하지 않음 |
| Nexar train | positive 80 + negative 24 = 104개, 약 68분 | 사고/near-miss/정상 선별 | 실제 접촉·진입·프레임·방향·회피 공간 검수 |
| comma2k19 | 서로 다른 날짜 24개 주행, 약 24분 및 센서 | S1 원천, S3 보조 타깃 | 사건/주행 그룹, 센서 의미와 클래스 기준 검수 |
| comma S1 재생본 | 24개, 각 약 10초, 20fps | S23 화면 재촬영 | 실제 휴대폰 촬영 48회 |
| comma S3 보조값 | 23개 주행, 13,776행 | 10Hz 연속 센서 proxy | 시간 원점·프레임 매핑·클래스 정의 |
| DoTA | 주석 후보 2,682개 | 출처/라벨 구조 조사 | 해당 실제 영상은 이 수량만큼 확보한 것이 아님 |
| DINOv2 ViT-S/14 | 공식 가중치 다운로드·state_dict 로딩 확인 | 사전학습 후보 | 영상 모델 구성·학습·오프라인 forward 검증 |

Ultra의 Nexar CSV는 104행 모두 actual_contact/collision_frame/entry_frame이 비어 있다. 촬영표 48행의 실제 휴대폰 파일명도 비어 있고 촬영 폴더에 실제 파일이 확인되지 않았다. **원본 영상은 있으며 DACON용 학습 정답은 아직 준비 중이다.**

Nexar revision은 `260710de7e076bc3f5259071421a77dd76d36ac3`, comma 배포 revision은 `4bff77c7254c654c28d4c2726186b4e825adccee`다. 재수집 시 최신 main 대신 기록된 버전·원본 manifest를 기준으로 한다. 2026-09-24 Nexar 104개는 공식 SHA 대조와 전체 122,175프레임 디코드 검사를 통과했다. 수신 사본은 별도로 해시를 확인한다.

## 2. 순서와 담당: P0 → P1 → P2 → P3 → P4

| 게이트 | Pro 작업 | Ultra 결정 | 통과 증거 |
|---|---|---|---|
| P0 출처·무결성 | inventory, 라이선스 원문/조건, 해시·디코드 기록 | 사용/보류 범위 | 파일별 출처·SHA·권한 상태, 손상 없음 |
| P1 그룹·시간축 | 중복 사건/주행 확인, PTS·센서 점검 | canonical source와 제외 사유 | group manifest, 원본 프레임 대응 |
| P2 split | 그룹별 train/validation/test 후보 | split 동결 | 그룹 교집합 0, 클래스·조건 분포 |
| P3 라벨·파생 | 사람 검수 지원, 마스크, 촬영 QA, 센서 proxy | 충돌 해결·Stage별 라벨 승인 | 라벨 버전, 검수 이력, 유효 표본 수 |
| P4 release | 자동 검사와 오류 보고 | 불변 release 및 manifest SHA 발행 | 해시·경계·커버리지·누수 검사 통과 |

자동 해시·인덱스 생성은 지금 할 수 있다. 정답 판단과 물리 촬영은 사용자가 맡는다. 새 검사 코드 구현 시 원본과 기존 검수 CSV를 덮어쓰지 않고 새 출력 버전을 생성한다. 현재 준비 스크립트에는 기존 출력 폴더가 있으면 중단하는 동작도 있으므로 재실행 전 목적과 출력 경로를 확인한다.

## 3. P0: 원본 보존·사용조건·inventory

원본은 `data/external/`, 휴대폰 원본은 `data/captures/s23/`에 보존한다. 재인코딩·리사이즈·오디오 제거·프레임 추출은 `data/derived/<version>/`에 새로 만든다. 손상/조건 미확정은 inventory의 `quarantined` 상태로 학습에서 제외하고 원본을 삭제하지 않는다.

source inventory의 필수 열:

| 필드 | 의미 |
|---|---|
| source_id, relative_path, sha256, bytes | PC 간 동일 자료 확인; 선행 0이 있는 ID는 문자열 |
| source_url, revision, license_path, license_sha256 | 실제 받은 버전과 보관한 원문 |
| use_status, permitted_stage, decision_note | eligible/pending/excluded와 사용 범위·판단 근거 |
| source_group, event_group, parent_source_id | 주행/사건 중복과 파생 관계 |
| width, height, codec, nominal_fps, decoded_frames, duration_pts_seconds | 실제 디코드·컨테이너 정보 |
| pts_map_path, pts_map_sha256, decode_status | 프레임 번호와 시각 대응 근거 |
| split, exclusion_reason | 배정 및 제외 근거; 미확정 split은 빈 값 |

라이선스·README·출처 manifest도 영상과 함께 보관한다. comma MIT 표기, Nexar 별도 Open Data License를 [이용조건 장부](RESOURCE_LICENSES.md)와 대조한다. Nexar는 사고 분석용으로 제한하고 이 계획의 화면 재촬영 원천은 comma만 사용한다. HF 접근 승인은 DACON이 모든 활용 방식을 승인했다는 뜻이 아니다.

Nexar [원문 라이선스](https://huggingface.co/datasets/nexar-ai/nexar_collision_prediction/blob/main/LICENSE)와 [대회 규칙](https://www.dacon.io/competitions/official/236753/overview/rules)을 사용 직전에 대조한다. 보유한 파일·라벨·가중치를 공개 Git에 재배포하지 않는다. 원본 영상이나 번호판/얼굴을 외부 AI 서비스에 전송하는 작업은 현재 기본 경로에 포함하지 않는다. 보고서에는 비식별 집계와 로컬 sample ID를 우선한다.

## 4. P1~P2: 중복·시간축·분할을 먼저 확정

1. SHA가 같은 파일을 찾고 대표 source를 기록한다. 파일명이 다르다고 독립 표본으로 세지 않는다.
2. 비슷한 장면·사건은 저해상도 fingerprint로 후보를 만들고 사람이 확인한다. 부분 클립·크롭·재업로드는 같은 event_group으로 묶는다. fingerprint 유사도만으로 자동 삭제하지 않는다.
3. 같은 사고, 같은 연속 주행, 원본과 모든 재촬영·증강은 같은 split에 둔다. 같은 차량·노선·카메라 특성도 기록해 일반화 한계를 설명한다.
4. comma의 기존 24개 날짜 그룹 16/4/4 배정을 출발점으로 유지하고 S1/S3의 같은 source는 같은 split을 상속한다. 날짜가 다르다는 사실만으로 24개의 완전히 독립된 도메인이라고 주장하지 않는다. SRC014의 S3 제외로 Stage별 유효 수가 달라질 수 있다.
5. Nexar는 접촉/진입 선별과 사건 중복 확인 후 group 단위로 약 70/15/15를 목표로 배정한다. 숫자보다 검증/시험의 유효 라벨과 클래스 확보를 우선하고 실제 개수를 기록한다. 검증·시험에서 평가할 수 없는 헤드는 `not_estimable`로 둔다.
6. split을 동결한 다음 crop·sampling·정규화 통계·클래스 가중치·threshold를 train에서만 결정한다. 이미 생성된 파생물은 계보를 확인해 split을 소급 연결하고 누수 시 release에서 제외한다.

프레임 매핑은 `source_id, decoded_index, original_frame_id, pts_seconds, time_origin_seconds, derived_index, derived_pts_seconds, offset_seconds`를 기록한다. 원본 frame 번호, 디코드 순서, 10Hz sample_index는 서로 다른 값이다.

Nexar의 기존 audit는 전체 디코드 수와 nominal FPS를 확인했지만 프레임별 PTS 표는 생성하지 않았다. `event_seconds × fps`는 탐색용 시작 위치일 뿐 정답이 아니다. 프레임별 표시 순서·PTS를 추출해 VFR·중복/누락을 확인하고, CFR이 검증된 경우에만 `frame/fps` 변환을 사용한다. 프레임 추출·crop 이후에도 원래 번호를 복원할 수 있어야 한다.

## 5. S2 라벨 명세와 실제 작업

작업본: `data/derived/nexar_subset_v1/stage2_review_with_metadata.csv`. metadata의 source_label/time_of_event/time_of_alert는 출처 정보이며 DACON 정답이 아니다. positive에는 near-miss가 포함된다.

기존 CSV 칼럼은 유지한다. 다음 enum과 추가 정보는 release용 새 sidecar/정규화 파일에 저장한다. 현재 CSV 또는 worker가 이 enum을 검사한다고 가정하지 않는다.

| 항목 | 기록 규칙 |
|---|---|
| actual_contact | yes/no/uncertain; 불확실하면 이유 작성 |
| lane_entry_suitable | yes/no/uncertain; 피해 차량·가해 의심 차량의 쌍과 차선 식별 |
| collision_frame | 해당 두 차량의 실제 접촉이 처음 확인되는 원본 프레임; 프레임 범위 내 정수 |
| entry_frame | 피해 차량이 가해 의심 차량의 차선에 처음 진입하는 원본 프레임; 화면에 처음 보이는 시점과 구분 |
| evasion_space | 충돌 시점의 회피 공간 0/1; 판단 근거를 적고 애매하면 미정답 |
| entry_side | 화면 기준 LEFT/RIGHT; FRONT 같은 새 제출 범주를 만들지 않음 |
| origin_group_confirmed, split | 중복 사건 확인 및 동결된 split 참조 |
| review_status | unreviewed/needs_review/reviewed/excluded; 검토자·UTC·guideline 버전은 sidecar에 기록 |
| validity mask | collision_valid/entry_valid/evasion_valid/side_valid 각각 Boolean |
| uncertainty | 후보 프레임 범위, 가림/야간/다중 사건, 객체 쌍 설명, 제외 사유 |

0번 프레임은 실제 첫 프레임이다. 빈 라벨을 0이나 -1로 치환하지 않는다. “사건 없음”과 “아직 검수하지 않음”도 구분한다. 정상·near-miss를 collision_frame=0인 사고로 학습시키지 않는다. 헤드별 마스크로 유효 정답만 loss와 지표에 포함한다. entry가 없는 실제 접촉 사례도 모든 헤드를 억지로 채우지 않는다.

작업 순서:

1. 첫 3개로 기준을 맞춘다. 전체 문맥을 보고 차량 쌍·진입 차선을 적은 다음 프레임 단위로 접촉과 경계를 찾는다.
2. 104개를 선별한다. source event 시각 주변부터 탐색하되 필요한 경우 앞뒤 전체를 본다. 적합한 30~50개를 목표로 하되 실제 유효 사례가 부족하면 숫자를 채우기 위해 억지 라벨링하지 않는다.
3. 라벨마다 프레임 매핑과 출처를 연결한다. entry > collision, 경계 프레임, 방향 애매함은 재검수 대상으로 표시하며 자동으로 순서를 뒤집지 않는다.
4. 다음 날 최소 10건을 기존 답을 가리고 재검수한다. 차이를 기록하고 모호한 사례를 needs_review로 되돌린다. 한 사람이 두 번 보는 것은 독립 annotator 합의가 아니다.
5. train/validation/test의 각 헤드 유효 수와 클래스 분포를 출력한다. 평가할 표본이 없는 헤드는 점수를 제시하지 않는다.

초기 v1에서는 좌우 반전·역재생을 끈다. 좌우 반전을 도입하려면 side/steer 방향과 객체·차선 의미를 모두 변환하고 검증해야 한다. 시간 crop은 원본 프레임 복원표가 있는 경우에만 허용한다.

## 6. S1 S23 Ultra 촬영과 처리

작업본: `data/derived/comma_subset_v1/s23_capture_ready.csv`. 재생본은 `s1_playback/SRC001_ORIGINAL.mp4`부터 24개다. 디지털 trim/transcode는 물리 재촬영이 아니므로 원본 계열로 둔다.

환경은 [상세 촬영 계획](LABELING_AND_S23_PLAN.md)을 따른다. 초기 설정은 FHD 30fps, 1x 주 카메라, 가능하면 수동 셔터 1/60·ISO100·WB5000K·고정 초점이며 밝기에 따라 ISO50~400에서 기록한다. HDR·자동 FPS·자동 밝기 등 조건 변경 기능은 끄고, 화면 주사율은 가능하면 60Hz로 맞춘다. 3회 시험 촬영을 먼저 보고 과노출·심한 깜빡임·초점 이탈을 조정한다.

| 조건 | 화면 | 밝기·각도 |
|---|---|---|
| C1 | Pro | 70%, 정면 |
| C2 | Pro | 40%, 약 ±20도 |
| C3 | Ultra | 70%, 정면 |
| C4 | Ultra | 40%, 약 ±20도 |

홀수 source는 C1+C4, 짝수는 C2+C3로 48회 촬영한다. 원본 전체가 포함되도록 앞뒤 여유 약 2초를 확보한다. 실제 거리·각도·밝기·설정·take와 파일명을 기록한다. 장치별 조건이 특정 split이나 클래스 하나에만 몰리지 않도록 점검한다.

휴대폰 원본을 그대로 Pro에 복사하고 SHA·디코드·source 매칭을 검사한다. 표의 SHA는 휴대폰 파일용이며 재생본 SHA는 기존 report에서 참조한다. 흐림·반사로 내용을 구분할 수 없는 take는 제외/재촬영 사유를 남긴다. 적당한 모아레·반사 자체는 실제 재촬영 특성이므로 전부 제거하지 않는다.

모델용 파생물은 원본과 재촬영에 같은 resize/crop/오디오 처리 규칙을 적용한다. 베젤·플레이어 버튼·검은 테두리·코덱만 보고 분류하는지 별도로 확인한다. 재촬영 영상만 다른 해상도나 오디오 유무를 갖지 않게 한다. 원본과 폰의 시간축은 달라 프레임 번호를 직접 같다고 놓지 않는다.

원본 24개와 재촬영 48개의 수 불균형은 train sampler/loss에서 처리할 수 있지만 val/test 수를 복제로 부풀리지 않는다. 같은 source의 모든 take는 동일 split이다.

## 7. S3 시간축과 센서 proxy: 분류 정답 생성 전 필수 확인

원본: `data/external/comma2k19_subset_v1/segments/`의 video.hevc, global_pose/frame_times, CAN speed 및 steering_angle의 t/value 배열.
현재 보조 CSV: `data/derived/comma_subset_v1/s3_auxiliary_10hz.csv`.

현재 구현은 영상 frame_times와 디코드 프레임 수를 대조하고, 센서 중복 시각을 평균으로 합친 후 공통 시간 구간을 0.1초 간격으로 보간한다. 외삽은 하지 않으며 센서 보간 구간 간격은 최대 0.1초, 가장 가까운 영상 프레임 오차는 최대 0.03초다. SRC014는 이 시간 오차 조건을 넘겨 제외됐다. 원본은 보존한다.

| 열 | 의미와 확인 |
|---|---|
| sample_index | 현재 유효 10Hz 구간의 0 기반 순번 |
| source_frame_index | 해당 시각에 대응하는 원본 디코드 프레임 |
| elapsed_seconds | 원본 frame_times 시작 대비 경과 시간 |
| frame_offset_seconds | 선택한 영상 프레임과 표본 시각의 차이 |
| speed_mps | 센서 속도; 단위·영상과 일치 확인 |
| steering_angle_deg | 센서 각도; 부호·중립 bias를 영상과 대조 |
| acceleration_mps2_proxy | 속도의 수치 미분; 현재 별도 smoothing 없이 계산 |
| label_kind | 공식 정답과 구분하는 보조값 표기 |

**현재 CSV가 있다는 사실은 대응하는 10Hz 학습 영상이 완성됐다는 뜻이 아니다.** S1 재생 MP4는 원본 중간의 20fps 클립이므로 이 CSV와 바로 조합하지 않는다.

첫 SRC001의 sample_index=0은 elapsed_seconds=0.1에 대응한다. 따라서 source별 `time_origin_seconds = 첫 유효 elapsed_seconds`를 저장하고, 대응 파생 영상의 sample_index=0도 바로 그 시각으로 만들어야 한다. `sample_index × 0.1`을 원본 시작 시각으로 오해하면 한 프레임 이상 밀릴 수 있다.

다음 절차로 분류용 release를 만든다.

1. source별 frame_times 단조 증가·센서 coverage·중복 처리 이력·최대 offset·누락을 보고한다. 기존 보고서의 통과와 새로운 파생물 검사를 구분한다.
2. 실제 10Hz 영상 또는 선택 프레임 목록을 만들고 CSV 각 행과 1:1 대응시킨다. 경계·시작/끝·급변 구간을 시각적으로 검사한다. 모든 source의 sample_index는 0..N-1이어야 한다.
3. STOPPED 임계값, 가감속 deadband, 조향 중앙 bias/threshold, 평활화 창을 train만 보고 정의한다. 이 값은 공식 기준으로 확인되기 전까지 자체 proxy 규칙이다. 고속도로 데이터에서 정지/급감속/큰 조향 클래스가 부족할 수 있다.
4. 센서값과 영상 의미가 불일치하거나 임계값 주변이 애매하면 confidence/mask를 둔다. 원하는 비율을 맞추려고 정답 threshold를 사후 변경하지 않는다. 부족한 클래스는 추가 주행 확보 또는 한계 보고로 처리한다.
5. ACCELERATING/DECELERATING/CONSTANT/STOPPED, LEFT/STRAIGHT/RIGHT로 매핑하되 규칙 버전과 클래스별 수를 저장한다. 검증/시험에는 고정된 train 규칙을 적용한다.
6. 조향 지표는 **정답 가감속이 STOPPED인 행**을 제외한다. 제출 예측은 그 행에도 steer_label을 출력한다. 예측을 STOPPED로 바꿔 어려운 조향 표본을 지표에서 숨기지 않는다.

센서 proxy 13,776행을 공식 정답 13,776개라고 부르지 않는다. 최종 추론에는 영상만 입력하고 CAN은 학습 정답 생성·정렬 검증에만 사용한다.

## 8. 사람 시간과 자동 처리의 분리

기존 계획의 수동 390분에 Nexar 선별 30~45분을 더해 **총 420~435분(7시간~7시간15분)**을 초기 배정한다. 다운로드·해시·디코드·새 매핑 도구 실행 시간은 별도다.

| 작업 | 시간 | 목표 |
|---|---:|---|
| Nexar 104개 선별 | 30~45분 | 실제 접촉·진입 적합 후보; 부족하면 물량 축소 |
| S2 기준 맞추기 | 20분 | 3개로 정의·차량 쌍·경계 일치 |
| S2 본 라벨링 | 180분 | 우선 30개, 평균 시간이 허용하면 50개까지 |
| S2 다음 날 blind 재검수 | 30분 | 최소 10건과 불확실 사례 |
| S2 정리·유효 수 확인 | 20분 | 마스크·그룹·누락 보고 |
| S23 준비·시험·48회 촬영·수신 QA | 90분 | 실제 파일과 촬영표 연결 |
| S3 파일럿 시각 검수 | 30분 | 대표 source의 시간축·센서 의미 확인 |
| 휴식 | 20분 | 작업 사이 배치 |

S2 첫 10건의 평균이 4분을 넘거나 불확실률이 높으면 50개 목표를 30개 이하로 낮추고 근거를 기록한다. S3 30분은 대표 구간 spot check이며 23개 전체의 분류 정답 승인 시간이 아니다. 자동 오류 보고에서 나온 경계·불일치와 클래스 기준 검수에는 추가 시간이 필요할 수 있다. 완료하지 못한 게이트는 일정 때문에 pass로 바꾸지 않는다.

## 9. P4 release 산출물과 완료 판정

제안 경로는 `data/derived/releases/<release_id>/`이며 아직 생성된 학습 release가 아니다.

- `sources.csv`: 출처·권한·그룹·무결성 inventory.
- `splits.csv`: source/event group → split의 고정 배정.
- `frame_time_map.csv`: 각 Stage 파생물과 원본 프레임/시간 대응.
- `labels_stage1.csv`, `labels_stage2.csv`, `labels_stage3.csv`: Stage별 라벨·유효 마스크·검토 이력 참조.
- `preprocess.json`, `label_rules.json`: 실제 적용 파라미터와 규칙 버전.
- `qa.json`: gate 결과, 제외 목록, split별 그룹·클래스·유효 수, 판단자·UTC·증거.
- `manifest.json`: 위 파일과 사용 데이터의 해시 및 부모 버전.

원본 SHA/출처 누락 0, split group 교집합 0, 라벨 범주/프레임 경계 오류 0, 유효 S3 행의 대응 누락 0, 미라벨 마스크 존재, 사람 판단이 필요한 항목의 명시적 상태가 필요하다. 제외된 표본은 목록에 남기고 학습 loader가 제외·mask를 실제 적용하는지 작은 batch로 확인한다.

공개 Git에는 이 규칙·검사 코드·빈 예제만 둔다. 두 PC에는 동일 해시 release를 전달하고 Ultra가 이를 실험 spec에 고정한다. release 이후 라벨 수정은 새 버전이다. 기존 결과를 새 정답으로 조용히 덮어쓰지 않는다.
