# Ultra 역할 — 총괄·GPU 학습·제출물

작업 폴더 `C:\Dacon\Dacon_AFDA_Challenge`, Python `.venv-ultra5060\Scripts\python.exe`, GPU RTX 5060 8GB (batch 1부터 실측).
docs/threads/ULTRA_THREAD.md의 채택 기준·중지 조건은 유지한다. 단, "Codex 작업"은 이 Claude 에이전트로 읽는다.

## 목표와 일정 (KST)

마감까지 **제출 가능한 submit.zip을 항상 하나 보유**하고, 검증 지표가 좋아질 때만 교체한다.

| 단계 | 기한 | 완료 조건 |
|---|---|---|
| A. 안전망 v001 | **완료** | 9/26 16:54 제출. 리더보드 S1 0.5650 / S2 0.2060 / S3 0.4656, 종합 약 0.382, 실행 15분 29초 |
| B1. v002 | 9/27 12:00 | 결정 10 반영: 공식 채점식 모듈, S2 ±0.3초 적중 최적화(상수 시점 기준과 비교), S3 0.7·0.3 선택, S1 v1+v1c 혼합. Stage별로 v001보다 나은 후보만 싣는다 |
| B2. v003 | 9/28 12:00 | 확장 데이터(결정 8) 재학습 결과 반영 |
| C. 동결 | 9/28 22:00 | 최종 후보 zip, SHA, 검증 근거, `submission_candidate` 보고. 9/29 오전 제출분은 오류 대응용으로 남긴다 |

**제출(결정 10):** 후보 zip이 준비되면 `submission_candidate`로 보고하고, `human_actions`에 업로드를 넣는다. 설치 오류는 제출 횟수에서 차감되지 않지만 실행 오류는 차감된다(하루 3회). 사용자가 리더보드 점수를 알려 주면 Stage별 최고 점수와 모델 SHA를 `docs/STATUS.md`에 기록한다. 다음 zip은 Stage별 최고 모델을 조합해 만든다.

**우선순위(결정 10):** S2(0.4 배점, 0.206) > S3(가감속 비중 0.7) > S1(v1 중심 혼합, 리더보드로 판단). 공식 채점식 모듈을 가장 먼저 만든다.

## 데이터 확장 (CLAUDE.md 결정 8, 9/25 14:20 승인)

A 단계(v001)를 늦추지 않는다. GPU가 S2·S1을 학습하는 동안 CPU·네트워크로 확장을 준비하고, 준비된 것부터 v002 후보 실험에 쓴다.

| 순서 | 작업 | 산출물·완료 조건 |
|---|---|---|
| 1 | comma2k19 확장: 센서 로그를 먼저 받아 구간별 정지·회전·가감속 비율을 계산하고, 약 200구간(3~4시간)을 골라 영상을 받는다 | release `s3-aux-v2`(10Hz CSV, split, 시간축 QA). 기존 val 4개 source는 그대로 두고, 새 주행은 origin_group 단위로 split을 배정한다 |
| 2 | S3 e002: 확장 데이터로 재학습 | 고정 기준(기존 val 4개 source)과 새 val 두 가지로 보고한다. e001보다 좋아지면 채택한다 |
| 3 | Nexar positive 약 300개 추가(고정 revision) | `nexar_event` 충돌 라벨(time_of_event × fps, `contact_unverified`). 원본과 프레임 수가 같은 640px 사본을 Pro에 `request` 패킷으로 배치 전송한다(패킷당 4GiB 이하) |
| 4 | S2 재학습: 에이전트 라벨 + `nexar_event` 라벨 | 라벨 출처별 수와 검증 지표. Pro의 접촉·진입 라벨이 오면 release를 갱신한다 |
| 5 | 새 comma 구간에서 S1용 10초 재생 클립 약 76개 생성 → Pro에 `request`로 전송 | Pro가 합성해 `qa`로 보내면 S1을 재학습한다 |

확장 데이터 재학습은 9/28 18:00까지 끝내고, C 단계(22:00 동결)에서 기준 모델과 비교해 고른다. 다운로드가 늦어지면 받은 만큼으로 진행한다.

## 권장 출발점 (근거가 나오면 바꿔도 된다)

- 공통: `src/afda/`에 디코딩·전처리를 학습과 추론이 함께 쓰는 모듈로 만든다(CODE_REVIEW.md의 학습/추론 불일치 지적 참고). 노트북 원본 `src/baseline_inference.py`는 수정하지 않는다.
- S3(가중치 0.4): comma2k19 영상과 센서 proxy가 있다. 저해상도 광학 흐름·프레임 차분 같은 ego-motion 특징과 작은 시계열 모델이 빠르고 데이터 효율적이다. 클래스 규칙(STOPPED, 가감속 deadband, 조향 threshold)은 train split에서만 정하고, Pro의 제안을 반영한다.
- S2(가중치 0.4): Pro의 에이전트/사람 라벨(headwise mask)로 학습한다. 라벨이 적으면 사전학습 백본 특징 + 작은 시간 헤드, 또는 움직임 급변 기반 휴리스틱을 validation에서 비교한다. 채점은 프레임을 초로 바꿔 비교하므로 시간 오차를 줄이는 것이 핵심이다.
- S1(가중치 0.2): **CLAUDE.md 결정 9·10을 따른다.** v1(광학)을 중심으로 v1c(디지털, 코덱 동일 쌍 포함)를 섞어 학습한다. 채택 기준은 합성 검증 v1·v1c 중 낮은 값, S23 실촬영(생기면 최우선), 리더보드 S1(현재 최고 0.565)이다. Baseline 공식 예제 10개는 참고 지표로만 쓴다. 224 전체 축소 대신 원해상도 패치 입력을 후보로 검토한다.
- 사전학습 가중치: 확보된 DINOv2 ViT-S/14(Apache-2.0)나 torchvision ImageNet 가중치를 학습 때만 받고, 제출물에는 state_dict로 포함한다. 새 가중치는 docs/RESOURCE_LICENSES.md와 docs/MODEL_REGISTRY.json에 기록한다.
- `harness package`의 `MODELS` 목록과 `validate_zip`은 베이스라인 파일 이름에 고정돼 있다. 모델 파일이 바뀌면 이 목록·검사기·tests를 함께 고친다.
- 60분 제한: 평가 입력 규모는 비공개다. Baseline 예제의 영상당 시간을 재고 여유 있게 설계한다(디코딩 해상도·프레임 간격 축소, AMP, 배치).

## 사이클마다 할 일

1. Pro 패킷 처리: `qa`(라벨·합성 데이터·QA) → 데이터를 확인하고 release로 동결(`data/derived/releases/<id>/manifest.json`, SHA 기록). `review` → 채택/거절/수정 요청/중지를 `decision` 패킷으로 보낸다. `request` → 처리하거나 거절 사유를 답한다.
2. 끝난 GPU job: run 디렉터리의 로그·지표를 확인하고 `result` 패킷(`predictions.csv`, 지표, 환경 lock, checkpoint SHA)을 Pro에 보낸다. checkpoint는 Ultra에만 둔다.
3. 남은 시간에는 표의 현재 단계에서 가장 가치 있는 작업을 한다. GPU는 한 번에 job 하나다. job 실행 중에는 코드 정리, 추론 속도 측정, 패키징 검증 같은 CPU 작업을 한다.
4. main 통합: Pro의 `origin/pro/*` 브랜치를 `git fetch`로 받아 diff와 테스트를 확인하고 병합한다. push 전에 `python -m unittest discover -s tests`를 통과시킨다.
5. Pro에게 필요한 일은 `request` 패킷으로 구체적으로 요청한다(대상 ID, 산출 형식, 기한).

## spec·result·decision 규칙

- spec에는 data release SHA, split, metric 정의, code commit, 변경 1개, seed, 예산을 넣는다(docs/EXPERIMENT_PROTOCOL.md). 첫 기준 실험은 controller(Ultra) 자체 승인으로 시작할 수 있다.
- GPU job은 commit된 깨끗한 트리에서만 시작된다. 먼저 commit한다.
- 같은 release·metric에서만 점수를 비교한다. 데이터가 바뀌면 기준 모델을 새 release에서 다시 평가한다.
- 제출 후보 교체 조건: 같은 validation에서 종합(0.2·S1 + 0.4·S2 + 0.4·S3, 자체 진단 지표임을 명시)이 개선되고, Stage별 계약 검사·실행 시간이 통과할 것.
