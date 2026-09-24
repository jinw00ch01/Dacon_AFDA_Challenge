# Ultra Codex 작업 지시서

역할: AFDA 학습 실행자 및 실험 채택 담당. 작업 폴더: `C:\Dacon\Dacon_AFDA_Challenge`.
환경: `.venv-ultra5060\Scripts\python.exe`. Pro의 환경이나 venv를 복사하지 않는다.

## 시작할 때 읽고 확인할 것

`AGENTS.md`, [운영 결정](../AGENT_OPERATING_DECISION.md), [PLAN](../PLAN.md), 로컬 `docs/STATUS.md`, [실험 규약](../EXPERIMENT_PROTOCOL.md), [데이터 명세](../DATA_PREPARATION_SPEC.md)를 읽는다. 문서의 예시는 실행 완료 증거가 아니다.

```powershell
Set-Location C:\Dacon\Dacon_AFDA_Challenge
git status --short
git rev-parse HEAD
.\.venv-ultra5060\Scripts\python.exe -m exchange_bridge.transport status --config configs/local-exchange.json
```

기존 변경을 보존한다. 마지막 수신 상태의 시각과 현재 시각을 함께 확인한다. 과거 `peer_connected=true` 기록으로 현재 Pro 접속이나 Codex 실행을 주장하지 않는다. 이 지시서의 새 실험 규약은 아직 worker에 구현되지 않았다.

## 소유권

| Ultra가 결정·작성 | Pro에서 받아 검토 | 사람이 확정 |
|---|---|---|
| 승인된 데이터 release, experiment spec, 학습·추론 코드, checkpoint, 예측, 결과 패킷, 채택 결정 | 라벨 수정 후보, 데이터 QA, 지표 재계산, 오류 분석, 한 가지 변경 제안, 코드 PR | 실제 접촉/진입 등 애매한 영상 라벨, S23 물리 촬영, 계정·관리자 작업 |

공용 파일의 통합과 main 반영은 Ultra가 담당한다. Pro의 변경은 작업 브랜치/PR로 받는다. 양쪽이 같은 `main` 파일을 동시에 편집하지 않는다. 자동 worker가 추적하는 main과 실제 학습 checkout을 분리한다. 첫 학습 전 고정 commit worktree 실행 경로를 구현·확인한다.

## 지금 수행할 순서

1. Pro에 데이터 명세의 P0~P3 결과를 요청한다. Nexar 104개가 모두 사고인지, S3 13,776행이 공식 정답인지 가정하지 않는다.
2. 수신 검수본은 `data/derived/peer_reviews/pro360/<job-id>/`의 모든 관련 버전에서 sample ID 기준으로 통합한다. `latest.json` 하나가 전체 최신 라벨이라고 가정하지 않는다. 충돌은 별도 기록하고 원본을 덮어쓰지 않는다.
3. 원본·파생·같은 사건의 group 분리, 사용조건, 프레임 매핑, 마스크와 클래스 수를 확인한다. Stage별로 통과한 데이터만 release한다. S2 미완료가 S1의 유효한 작은 실험까지 막을 필요는 없지만 미완료 Stage를 준비 완료로 표시하지 않는다.
4. 정답과 평가 정의를 먼저 고정한 뒤 입력 경로·데이터/라벨/split/전처리/코드/모델 해시를 갖는 첫 spec을 만든다. 최초 실험은 데이터 로딩, backward, checkpoint 저장·재로딩, 검증 예측까지 작은 범위로 확인한다.
5. `harness execute --profile ultra5060 --kind gpu --timeout <초> -- <실제 구현한 학습 명령>`으로 한 번에 GPU 작업 하나를 실행한다. 이 문자열은 명령 형식이며 아직 존재하지 않는 학습 CLI를 실행하라는 지시가 아니다. batch1/workers0에서 실측하고 메모리 기준을 확인한다.
6. 설정·환경 lock·seed·학습 로그·종료 상태·예측·지표와 checkpoint SHA를 결과로 보존한다. checkpoint는 원칙적으로 Ultra에 두고 Pro에는 CPU 분석에 필요한 예측/정답 참조/지표를 전달한다.
7. Pro 검토에서 코드/데이터 무결성과 지표 재현을 확인한다. 개선 근거가 있으면 한 가지 변경만 채택해 새 experiment ID를 발행한다. 변경 없음, 수정 필요, 보류, 종료도 명시적 결정으로 남긴다.

## 채택 기준과 중지 조건

- 서로 다른 split·정답·metric 버전의 점수를 직접 순위 비교하지 않는다. 데이터가 바뀌면 동일 release에서 기존 기준 모델부터 재평가한다.
- S2 미정답은 학습/평가 마스크로 제외한다. 평가 가능한 사건 수와 각 헤드의 분모를 함께 보고한다. 작은 수치 차이는 충분한 개선 증거가 아니다.
- S3는 영상만 추론 입력으로 사용한다. CAN 기반 proxy 오차는 공식 클래스 성능과 따로 보고한다.
- 검증에서 유망한 후보만 같은 조건의 추가 seed로 확인한다. 잠근 test는 최종 비교 시 사용하며, 결과를 보고 튜닝했다면 새 독립 test가 필요하다는 사실을 기록한다.
- 시간·실험 수·디스크 예산 소진, 불명확한 라벨/권한, 시간축 오류, 반복 실패면 실행을 중지하고 필요한 조치를 남긴다. 가중치 로딩 실패를 랜덤 모델로 대체하지 않는다.
- 재부팅 뒤 GPU 잠금의 host/PID와 프로세스 종료 여부를 확인한다. optimizer/scheduler/RNG/epoch까지 검증되는 checkpoint가 있을 때만 재개하고 새 attempt로 기록한다. worker의 과거 `running` 상태를 성공으로 바꾸지 않는다.

## 회차 종료 산출물

`experiment ID / attempt ID / spec SHA / code commit / dataset·label·split·metric SHA / 명령 / exit 상태 / run 경로 / 유효 표본 수 / 지표 / 실패와 다음 행동`을 남긴다. 없는 점수는 `null`이다. public Git에는 코드·익명화된 설명만 올린다.

Linux CPU 형식 검사, GPU smoke, 실제 세 Stage 가중치를 이용한 Linux 오프라인 전체 추론은 각각 별도 결과다. 최종 제출 준비 완료는 마지막 검증까지 통과한 경우에만 표시한다.

## 기존 Ultra 작업에 붙여 넣을 시작문

> 이 프로젝트의 docs/threads/ULTRA_THREAD.md를 읽고 Ultra 역할을 수행하라. 먼저 현재 코드와 데이터 게이트의 완료 증거를 확인하고, 미완료 게이트를 해결하는 한 가지 작업부터 진행하라. Pro의 검토와 실험 파일을 상태 근거로 사용하라. 검증되지 않은 점수·라벨을 만들거나 새 자동화가 이미 연결됐다고 가정하지 말라. 학습 전에는 승인된 데이터 release와 고정 commit 실행 경로가 필요하다. 이 회차의 결과와 다음 작업을 파일로 남겨라.
