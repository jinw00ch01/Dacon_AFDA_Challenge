# Ultra 역할 — 총괄·GPU 학습·제출물

작업 폴더 `C:\Dacon\Dacon_AFDA_Challenge`, Python `.venv-ultra5060\Scripts\python.exe`, GPU RTX 5060 8GB (batch 1부터 실측).
docs/threads/ULTRA_THREAD.md의 채택 기준·중지 조건은 유지한다. 단, "Codex 작업"은 이 Claude 에이전트로 읽는다.

## 목표와 일정 (KST)

마감까지 **제출 가능한 submit.zip을 항상 하나 보유**하고, 검증 지표가 좋아질 때만 교체한다.

| 단계 | 기한 | 완료 조건 |
|---|---|---|
| A. 안전망 v001 | 9/26 12:00 | 세 Stage를 모두 출력하는 `inference.py`와 가중치, harness package → preflight → Baseline 예제 전체 추론 → `harness check` 3개 통과, 실행 시간 기록 |
| B. 개선 반복 | 9/26–9/28 | spec → GPU job → result → Pro review → decision. 실험마다 변경 1개 |
| C. 동결 | 9/28 22:00 | 최종 후보 zip, SHA, 검증 근거, `submission_candidate` 보고 |

v001이 나오면 `human_actions`에 "DACON에 submit_v001.zip 업로드해 서버 설치·실행 검증"을 넣는다. 설치 오류는 제출 횟수에서 차감되지 않는다.

## 권장 출발점 (근거가 나오면 바꿔도 된다)

- 공통: `src/afda/`에 디코딩·전처리를 학습과 추론이 함께 쓰는 모듈로 만든다(CODE_REVIEW.md의 학습/추론 불일치 지적 참고). 노트북 원본 `src/baseline_inference.py`는 수정하지 않는다.
- S3(가중치 0.4): comma2k19 영상과 센서 proxy가 있다. 저해상도 광학 흐름·프레임 차분 같은 ego-motion 특징과 작은 시계열 모델이 빠르고 데이터 효율적이다. 클래스 규칙(STOPPED, 가감속 deadband, 조향 threshold)은 train split에서만 정하고, Pro의 제안을 반영한다.
- S2(가중치 0.4): Pro의 에이전트/사람 라벨(headwise mask)로 학습한다. 라벨이 적으면 사전학습 백본 특징 + 작은 시간 헤드, 또는 움직임 급변 기반 휴리스틱을 validation에서 비교한다. 채점은 프레임을 초로 바꿔 비교하므로 시간 오차를 줄이는 것이 핵심이다.
- S1(가중치 0.2): comma 원본 vs Pro 합성 재촬영(+ S23 실촬영). 원본과 재촬영에 같은 resize·인코딩을 적용해 코덱·해상도 지름길을 막는다.
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
