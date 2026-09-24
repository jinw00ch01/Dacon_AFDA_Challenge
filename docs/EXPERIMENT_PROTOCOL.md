# 두 PC 실험 파일 규약 v1 — 구현 명세

작성: 2026-09-25. **이 문서와 예제는 향후 실험 제어 계층의 설계다. 현재 `exchange_bridge` 작업 큐에서 실행되는 새 기능이 아니다.** 원본·라벨·예측·모델과 실제 패킷은 공개 Git에 올리지 않는다.

## 현재 코드에서 확인한 경계

| 현재 기능 | 가능한 일 | 추가 구현이 필요한 일 |
|---|---|---|
| Git main 수신 | 수정 없는 지정 저장소에서 주기적 fast-forward | 실행 중 학습을 위한 고정 commit checkout |
| Syncthing | 지정 전송 폴더의 파일 동기화 | 파일의 의미 판단, 작업 채택, Codex 실행 |
| CPU worker | ping, verify_bundle, import_bundle, prepare_review, run_contract_tests, return_reviews | 학습·지표 재계산·에이전트 review·실험 결정 |
| 검수 자동 반환 | 지정 CSV 2개와 S23 MP4/MOV | 임의 experiment/QA 파일 자동 반환 |
| 중복 방지 | 처리한 job 재실행 방지, 중단 작업 기록 | 학습 checkpoint resume, 실험별 시도·예산 관리 |

기존 큐 JSON은 `version,id,sender,target,action,bundle,manifest_sha256,code_commit,created_utc`만 받는다. `jobs/`에 아래 spec을 넣거나 `action=train`을 추가해도 실행되지 않는다. 기존 job ID는 UUID의 32자리 hex다. 새 실험 ID와 구분한다.

현재 bundle 한도는 파일당 512MiB, 전체 8GiB/5,000파일이며 import 후 여유공간은 Pro 20GiB, Ultra 40GiB다. 대형 checkpoint는 Ultra에 보관하고 Pro에는 예측과 분석 자료를 전달한다. 전체 데이터 bundle을 결과 검토마다 다시 만들지 않는다.

## 파일 흐름과 작성자

```text
Pro: 데이터 QA + 라벨 후보 → Ultra: release 동결 + spec
Ultra: 고정 코드로 학습 → result + predictions → Pro
Pro: CPU 검증 + review + 한 가지 proposal → Ultra
Ultra: decision → 채택 시 새 spec, 아니면 수정·보류·종료
```

Ultra가 `spec/result/decision`을, Pro가 `review`를 작성한다. 수신자는 상대 패킷을 수정하지 않고 자신의 송신 폴더에 ACK를 작성한다. 정정은 새 패킷이며 `supersedes`로 이전 패킷을 가리킨다.

향후 어댑터의 송신 경로는 `<exchange_root>/<sender_direction>/experiments/v1/<packet_id>/`다. 기존 `jobs`, `bundles`, `results` namespace와 섞지 않는다. 로컬 작업본은 Git 제외 경로 `data/derived/experiment_packets/`에 둔다. 경로를 문서에 정의한 것만으로 현 worker가 수집하지는 않는다.

| 패킷 | 최소 파일 | 완료 의미 |
|---|---|---|
| spec | `spec.json`, config, 참조 release/metric 목록 | 실행 가능한 입력과 제한 확정 |
| result | `result.json`, `predictions.csv`, 지표/환경/로그 참조 | 실행 종료; 성공 여부는 status로 별도 판단 |
| review | `review.json`, CPU 재계산 지표, 사례 목록 | 무결성·재현 확인과 한 가지 제안 |
| decision | `decision.json` | Ultra가 채택/거절/수정 요청/종료 결정 |
| ack | `ack.json` | 특정 패킷을 검증하여 수신; 성능·제안 승인과 다름 |

모든 패킷에 `manifest.json`과 마지막에 쓰는 `COMMITTED.json`을 둔다. 파일명과 ID에는 영상 속 개인정보를 넣지 않는다. 패킷별로 읽기 전용 보존하며 변경 가능한 `latest` 포인터는 탐색 보조로만 사용한다.

## 공통 필드와 직렬화

예제: [spec](templates/experiments/spec.example.json), [result](templates/experiments/result.example.json), [review](templates/experiments/review.example.json), [decision](templates/experiments/decision.example.json). `example_only: true`인 예제는 실행 거부 대상이다. 예제의 null/설명 문자열은 실제 SHA·ID·값으로 채워야 한다.

| 필드 | 규칙 |
|---|---|
| schema_version | `afda.experiment.v1`; 지원하지 않는 버전 거부 |
| kind | spec/result/review/decision/ack |
| packet_id | 새 UUID hex 32자리, 패킷마다 유일 |
| experiment_id | `exp-<UUID hex 32자리>`; 설정/데이터/코드 변경 시 새 ID |
| attempt_id | result/review는 `a001`부터; 같은 spec의 실행 시도 식별 |
| sender, target | ultra5060/pro360; 폴더의 작성자와 일치 |
| created_utc | UTC RFC3339, `Z` 사용; 정렬/중복 제거를 시각 하나에 의존하지 않음 |
| parent / supersedes | 참조 패킷 ID와 manifest SHA 또는 null; 원인·정정 관계 |
| provenance | 실제 작성 도구/모델 식별자(알 때), 코드 commit, 근거 파일; 비밀·대화 전문 제외 |

JSON은 UTF-8, 중복 키 금지, NaN/Infinity 금지다. CSV는 UTF-8, sample ID는 문자열, 소수점은 `.`이다. ID/sha/필드 타입을 엄격히 검사하고 알 수 없는 실행 필드를 허용하지 않는다. 경로는 패킷 내부 상대 POSIX 경로로 표현하며 `..`, 절대 경로, symlink, 실행 파일 첨부와 임의 셸 명령을 거부한다. 로컬 데이터 경로는 신뢰하는 로컬 registry에서 해시로 해석한다.

해시는 **디스크에 확정된 파일 바이트의 SHA-256**이다. JSON을 재직렬화하거나 줄바꿈을 바꾸면 다른 파일로 취급한다. manifest는 payload 파일의 상대 경로·bytes·sha256을 정렬하여 기록한다. manifest 자신과 COMMITTED는 목록에서 제외한다. COMMITTED에는 packet ID와 manifest의 SHA를 기록한다. 두 파일의 순환 해시를 만들지 않는다.

## spec에 반드시 고정할 내용

- `stage`, `purpose`(smoke/train/evaluate), `baseline_experiment_id`, 단 하나의 `hypothesis`와 `change`.
- dataset manifest, label release, split manifest, preprocessing config, metric spec의 경로 식별자와 SHA. 소스 목록만 같아도 라벨이 다르면 다른 실험이다.
- Git full commit, 의존성 lock SHA, 초기 가중치 SHA 및 출처, seed 목록, 실행기의 사전 등록된 `runner_id`. 전달받은 자유 텍스트 명령은 실행하지 않는다.
- train/validation/test 선택, sample 수 및 group 수, head별 유효 라벨 수. test 사용 목적을 명시한다.
- batch/workers/AMP/epochs/LR 등 실제 적용 설정. 프로필의 기본 batch 값이 학습 코드에 자동 적용된다고 가정하지 않는다.
- 실행 시간, 회차 GPU 합계, 실험 수, 실패 재시도, 디스크/메모리 제한과 종료 조건. 정책 파일 SHA도 포함한다.

코드와 데이터가 모두 준비된 뒤 `APPROVED`로 전이한다. spec 파일이 도착했다는 이유로 학습을 시작하지 않는다. 승인된 decision 또는 최초 기준 실험의 명시적 controller 승인 이벤트가 필요하다. 여기서 controller는 Ultra 작업이며 매 회 사용자 클릭을 요구한다는 의미가 아니다.

## result·review·decision 내용

result는 `spec_sha256`, 실제 code commit·환경·입력 해시, 시작/종료 UTC, exit code, `status`, harness run 식별자, seed별 지표, 예측·checkpoint SHA, resource measurements를 담는다. `status`는 succeeded/failed/interrupted다. 실패에는 error와 재현 조건을 넣고 없는 지표는 null로 남긴다. 성공 시 예측·지표와 실제 checkpoint(학습인 경우)의 해시가 필수다.

각 지표에는 `name`, `value`, `direction`, `definition_sha256`, `n_samples`, `n_groups`, `valid_count`, `split`을 기록한다. “score” 숫자 하나로 Stage·분모·평가 정의를 숨기지 않는다. 예측 파일에는 sample ID, 원본 group, 출력, 마스크와 release 참조를 연결할 수 있어야 한다. 정답 원문은 이미 수신한 동일 해시 release를 참조해 중복 전송을 줄인다.

분석용 예측 테이블의 group·mask 등 부가 열은 제출 CSV에 그대로 넣지 않는다. 제출 시에는 각 Stage의 공식 열만 출력하고 별도로 계약 검사를 통과해야 한다.

review는 입력 result SHA, 재계산 코드/metric SHA, 일치 오차·표본 누락, 분석 근거와 제안을 담는다. `integrity_pass`, `metrics_reproduced`, `comparable_to_baseline` 중 하나라도 false면 개선 채택을 보류한다. 관측 사실과 기대 효과는 분리한다. proposal은 `parameter_or_transform`, `old_value`, `new_value`, `reason`, `falsification`, `estimated_cost` 한 묶음이다.

decision은 spec/result/review SHA, `accept/reject/request_revision/stop`, 근거, 새 실험 ID(accept일 때), 잔여 예산을 기록한다. accept도 실행기의 데이터/코드/자원 검사를 생략하지 않는다.

## 평가를 비교하는 규칙

| Stage | 우선 보고 | 주의 |
|---|---|---|
| S1 | Macro F1, 클래스별 지표, 원본 group 수 | 재촬영 형제가 서로 다른 split에 섞이면 비교 무효 |
| S2 | 헤드별 유효 수; collision/entry 시간 오차; evasion/side 분류 지표 | 프레임→시간은 해당 영상 매핑으로 변환. 진단 MAE를 공식 점수로 대체하지 않음 |
| S3 | 가감속/조향 클래스별 지표와 Macro F1, 클래스 분포 | 조향 제외 마스크는 GT STOPPED; 연속 센서 proxy 오차와 구분 |

공식 Stage 가중치는 0.2/0.4/0.4이나 S2의 세부 점수식·허용 오차와 Stage 내부 결합식을 완전히 확인하고 metric fixture를 검증하기 전에는 임의 식으로 종합 점수를 만들지 않는다. `evaluation.md` 및 [공식 평가 안내](https://www.dacon.io/competitions/official/236753/overview/evaluation)를 대조해 metric registry를 고정한다. 이전 대화의 0.742 같은 숫자는 설명용 예시이지 측정 결과가 아니다.

검증셋은 실험 선택에, 잠근 test는 최종 확인에 사용한다. leaderboard 점수는 별도 수동 기록이며 로컬 validation 점수와 합치지 않는다. 비공개 평가 입력/정답을 학습·튜닝·pseudo-labeling에 사용하지 않는다. 동일 사건 그룹 단위로 비교하고, 필요한 불확실성 분석은 프레임별 독립 표본 가정 대신 그룹 단위 재표집을 사용한다. 유망 후보의 추가 seed 실험은 예산 내에서 수행한다.

## 원자적 전달·중복 방지·복구

1. 송신자는 `.staging-<id>`에서 payload와 manifest를 작성하고 해시를 검증한다. 같은 볼륨의 확정 디렉터리로 이동한 뒤 COMMITTED를 마지막에 쓴다. 수신 순서 자체는 보장되지 않는다고 가정한다.
2. 수신자는 marker만 보고 시작하지 않는다. manifest SHA, 모든 파일의 크기/해시, schema, sender, 참조 버전을 확인한다. 누락은 waiting_for_files, 변조·충돌은 quarantined다. 네트워크 수신과 실험 승인 상태를 분리한다.
3. 수신 ACK는 자신의 송신 폴더에 새 불변 패킷으로 작성한다. ACK의 참조 SHA로 송신 완료를 확인한다. 같은 packet ID에 다른 해시가 오면 덮어쓰지 않는다.
4. 로컬 장부에서 `(experiment_id, spec_sha256, attempt_id)` 실행 claim과 `(result_manifest_sha256, reviewer_role)` 검토 claim을 원자적으로 확보한다. OS 프로세스 잠금과 영속 장부를 함께 사용한다. 전달 중복은 허용하되 실행 효과는 중복되지 않게 한다.
5. 상태는 `DRAFT → DATA_READY → APPROVED → RUNNING → RESULT_READY → REVIEWED → DECIDED`다. FAILED/INTERRUPTED/BLOCKED/CANCELLED는 별도 종료·대기 상태다. 이벤트에는 작성자·입력 SHA·이유를 기록하고 과거 이벤트를 수정하지 않는다. 주 상태는 Ultra가, 수신/검토 장부는 각 PC가 소유한다.
6. 재부팅 후 RUNNING을 자동 성공/재실행 처리하지 않는다. 프로세스, 잠금, checkpoint SHA와 optimizer/scheduler/RNG 복구 가능성을 확인한다. 같은 spec의 재시도는 새 attempt, 설정 변경은 새 experiment다. 재시작 원인과 부분 출력은 보존한다.
7. 자동 Git 수신 checkout에서 장시간 학습하지 않는다. 승인된 commit의 별도 worktree와 고정 환경으로 실행하며 활성 작업의 코드를 pull하지 않는다. 코드가 다르면 대기하고 강제 reset하지 않는다.
8. transient 실패 재시도 상한은 정책에서 정한다. OOM 때문에 batch를 바꾸면 새 spec이다. 예산 소진·불명확한 데이터·반복 실패는 사람이 볼 수 있는 blocked 사유로 남긴다. 원본·실행 로그·전송 스냅샷을 자동 삭제하지 않는다.

## 아직 구현해야 할 것

- strict schema 검사기 및 예제 실행 거부, release/metric registry와 SHA resolver.
- 실험 패킷 publisher/importer/ACK; 부분 수신·변조·중복·충돌·재시작 회귀 검사.
- 단일 GPU controller, 고정 commit worktree 실행기, 예산·attempt·checkpoint 복구 장부.
- CPU metric runner와 review writer; 지표 fixture 및 group/mask 검증.
- 각 PC의 Codex 로컬 wake 연결, unchanged 상태 무호출, 결과 해시당 호출 제한.

위 구현과 실제 왕복 검증 전에는 **“전송 자동화 완료”와 “학습·분석 반복 자동화 완료”를 구분**한다. 이번 변경은 문서와 예제만 추가한다.
