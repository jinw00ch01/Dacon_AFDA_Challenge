# Claude Code 두 PC 무인 운영

작성: 2026-09-25. [운영 결정](AGENT_OPERATING_DECISION.md)의 "PC별 Codex 작업 하나"를 사용자 결정에 따라 **PC별 Claude Code 에이전트 + `agent_bridge` 루프**로 바꾼다. 규약 문서(EXPERIMENT_PROTOCOL.md, DATA_PREPARATION_SPEC.md)는 그대로 쓰고, 그동안 명세만 있던 A1(패킷·ACK·장부)과 A2(로컬 wake)를 구현했다.

## 구조

```text
 Ultra (RTX 5060)                                   Pro 360 (CPU)
 ┌───────────────────────────┐                      ┌───────────────────────────┐
 │ 작업 스케줄러: 로그인 시    │                      │ 작업 스케줄러: 로그인 시    │
 │  agent_bridge loop (20초)   │                      │  agent_bridge loop (20초)   │
 │   ├ 패킷 가져오기·ACK        │   Syncthing          │   ├ 패킷 가져오기·ACK        │
 │   ├ GPU/CPU job 실행·감시    │ ◄──experiments/v1──► │   ├ CPU job 실행·감시        │
 │   └ 이유가 있으면 claude -p  │  (spec/result/review │   └ 이유가 있으면 claude -p  │
 │      (.claude/roles/ultra)  │   decision/qa/req/ack)│      (.claude/roles/pro)    │
 └───────────────────────────┘                      └───────────────────────────┘
          코드: GitHub main ← Ultra만 push      Pro: pro/* 브랜치 → Ultra가 병합
```

- 루프는 가볍다. Claude는 **깨울 이유가 있을 때만** 실행된다: 새 패킷, 끝난 job, 사람·상대가 바꾼 입력, 에이전트가 요청한 재실행(`next_wake`), 90분 heartbeat.
- 같은 이유는 한 번만 전달된다. 실패한 사이클은 이유를 유지하고 2분부터 최대 1시간까지 간격을 늘려 재시도한다.
- 10분을 넘는 작업은 Claude 밖의 detached job으로 돌고, 끝나면 다음 사이클을 깨운다. GPU job은 Ultra에서 한 번에 하나이고 commit된 코드에서만 시작한다.
- 매 사이클은 `--json-schema` 보고서(요약, 행동, 사람 할 일, next_wake, 제출 후보)를 남긴다. 사람 할 일이나 제출 후보가 생기면 Windows 알림과 `work/agent/HUMAN_ACTIONS.md`로 알린다.
- 보고서 도구 호출이 깨져 CLI가 `error_max_structured_output_retries`로 끝나면(다른 항목이 `summary` 안으로 새는 현상), 루프가 세션 기록(`~/.claude/projects/*/<session_id>.jsonl`)의 마지막 보고서 시도를 복구해 검증하고, 통과하면 성공으로 처리한다(`report_salvaged: true`, loop.log에 기록). 이 현상을 줄이려고 스키마에서 `summary`를 마지막 항목으로 둔다.

## 안전장치

| 장치 | 내용 |
|---|---|
| guard 훅 (`.claude/hooks/guard.py`) | 모든 셸·편집 호출 전에 실행한다. force push·기록 삭제, 원본·사람 라벨 삭제/수정, 외부 업로드, 시스템·레지스트리·스케줄러 변경, 전역 pip, Pro의 GPU 실행을 거부한다. 무인 실행에서는 허용목록 밖 프로그램, 자기 정책 수정, 중첩 claude 실행, 서비스 제어도 거부한다. |
| settings 거부 규칙 | 훅이 실행되지 못해도 원본 경로 편집과 force push를 막는다. 무인 모드의 셸 명령은 훅의 허용이 없으면 자동 거부된다(fail-closed). |
| 원본 읽기 전용 | 설정 스크립트가 `data/external`, `data/captures`, `Baseline` 파일에 읽기 전용 속성을 건다. |
| 예산 (`configs/agent_policy.json`) | 사이클당 USD 상한, 하루 사이클 수·USD 상한, 사이클 시간 제한, 마감 뒤 자동 중지(9/30 10:00 KST). PC별 조정은 `configs/local-agent-policy.json`. |
| 패킷 검사 | UTF-8 strict JSON, 작성 권한(kind별), manifest SHA, 부분 수신 대기, 변조·위장 격리, 실행 파일 첨부 거부. 수신 사본은 읽기 전용이다. |

## PC별 최초 1회 설정

시작 메뉴의 Windows PowerShell에서 실행한다. **Codex 앱이나 스토어(MSIX) 버전 Claude 데스크톱 앱 안의 터미널에서 실행하지 않는다.** 이런 앱 안의 셸은 `%LOCALAPPDATA%`에 새로 쓰는 파일을 앱 샌드박스(`Packages\<앱>\LocalCache`)로 보낸다. 그래서 설정 상태가 샌드박스에 갇히고, 앱 안에서 실행한 `pause`·`resume`·`stop`·`publish`도 실제 루프에 전달되지 않는다(2026-09-25 Ultra에서 확인). setup 스크립트와 상태를 쓰는 agent_bridge 명령은 이를 감지하면 아무것도 바꾸지 않고 멈춘다. Pro의 Claude 앱은 일반 설치본이라 해당하지 않는다. 기존 교환 서비스가 Codex 앱의 MSIX 가상화 폴더(`%LOCALAPPDATA%\Packages\OpenAI.Codex_…\LocalCache`)에 설치돼, 로그인 자동 시작이 실제로 등록되지 않았다. 설정 스크립트는 Syncthing 신원(키)을 그대로 옮기므로 장치 재등록이 필요 없다.

먼저 각 PC의 프로젝트 폴더에서 `claude`를 한 번 실행한다. "이 폴더를 신뢰" 질문을 수락하고, 로그인이 만료됐으면 `/login` 한 뒤 `/exit`한다. 신뢰하지 않은 폴더에서는 headless 실행이 프로젝트 훅·권한을 무시하므로 설정 스크립트가 중단된다(종료 코드 2·3과 안내 문구).

```powershell
# Pro 360
Set-Location C:\Dacon\Dacon_AFDA_Challenge_git
git pull --ff-only
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_claude_agents.ps1 -Role pro360

# Ultra
Set-Location C:\Dacon\Dacon_AFDA_Challenge
git pull --ff-only
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_claude_agents.ps1 -Role ultra5060
```

스크립트가 하는 일: 교환 상태 이전 → `setup_exchange.ps1` 재실행(수신 폴더 versioning 버그 수정) → 교환 서비스를 작업 스케줄러 `AFDA-Exchange-<role>`로 실행 → 원본 읽기 전용 → `CLAUDE.local.md` 역할 연결 → guard·폴더 신뢰·claude 인증 확인 → 작업 스케줄러 `AFDA-Agent-<role>` 등록·시작.
여러 번 실행해도 안전하다. 관리자 권한은 필요 없다.

전원: 무인 운영 중에는 전원을 연결하고 Windows 절전을 "안 함"으로 설정한다(설정 → 시스템 → 전원). 루프는 실행 중 유휴 절전을 막지만, 덮개를 닫거나 전원 정책으로 인한 절전은 막지 못한다.

## 확인·중지

```powershell
.\.venv-<role>\Scripts\python.exe -m agent_bridge status      # 루프·사이클·패킷·job·예산
.\.venv-<role>\Scripts\python.exe -m agent_bridge inbox       # 받은 패킷
.\.venv-<role>\Scripts\python.exe -m agent_bridge job list
.\.venv-<role>\Scripts\python.exe -m agent_bridge pause       # 새 사이클 중지 (job은 계속)
.\.venv-<role>\Scripts\python.exe -m agent_bridge resume
.\.venv-<role>\Scripts\python.exe -m agent_bridge wake --reason "CLAUDE.md 결정 N 반영"   # 규칙을 바꾼 뒤 바로 사이클 시작
powershell -File scripts\setup_claude_agents.ps1 -Role <role> -Uninstall   # 루프 작업 제거
```

기록 위치: `%LOCALAPPDATA%\AFDA\<role>\agent\`(ledger.json, loop.log, cycles/<id>/stdout.json·prompt.md, jobs/<id>/), 프로젝트 `work/agent/last_cycle.json`·`HUMAN_ACTIONS.md`, 각 에이전트의 `docs/STATUS.md`.
사이클 대화를 직접 보려면 `claude --resume <session_id>`를 쓴다(session_id는 ledger에 있다).

## 사용량 한도와 코드 갱신

- 2026-09-25 사용자 결정: Claude 추가 사용량(실제 요금)은 끈다. Max 한도에 걸린 사이클은 실패로 세지 않는다. 루프는 오류 문구에서 초기화 시각을 읽어 그때까지 대기하고(모르면 30분), 한도 1회당 알림을 한 번만 보낸다. 깨운 이유는 보존했다가 재개할 때 처리한다.
- 두 PC가 같은 계정이면 한도를 함께 쓴다. `status`의 `usage_limit_until_utc`로 대기 시각을 확인한다.
- 루프는 사이클 사이에 `agent_bridge/*.py` 변경을 감지하면 모듈을 다시 읽는다. 코드 갱신 때문에 재시작할 필요가 없다.
- 재시작이 꼭 필요하면(루프 본문 변경 등) `pause` → 진행 중인 사이클과 job이 끝나기를 기다림 → 작업 스케줄러에서 `AFDA-Agent-<role>` 중지·시작 → `resume` 순서로 한다. job과 사이클은 스케줄러 작업과 같은 job 객체에 있어, 바로 중지하면 함께 종료된다.

## 자동 복구 (2026-09-26 추가)

9/26 19:57~19:58에 두 PC의 교환 감시 프로세스가 종료 코드 0xC000013A로 꺼졌다. 작업 스케줄러는 이 종료를 실패로 보지 않아 다시 켜지 않았고, 파일 교환이 약 3시간 멈췄다. 그래서 두 서비스가 서로를 살핀다.

| 감시하는 쪽 | 멈춤 판단 | 조치 |
|---|---|---|
| 에이전트 루프 → 교환 서비스 | `start_exchange.ps1` 프로세스가 없고, 교환 worker 상태(`%LOCALAPPDATA%\AFDA\<role>\worker-state.json`)가 2분 넘게 갱신되지 않음. 1분마다 확인 | `schtasks /Run /TN AFDA-Exchange-<role>`, 작업이 없으면 `start_exchange.ps1`을 직접 실행. 10분에 한 번까지. 1시간 안에 3번째이거나 실패하면 사람에게 알림 |
| 교환 서비스 → 에이전트 루프 | 루프 장부(`...\agent\ledger.json`, 일시중지 중에도 20초마다 기록)가 10분 넘게 갱신되지 않음. 10분마다 확인 | `schtasks /Run /TN AFDA-Agent-<role>` |

- 사람이 일부러 멈춘 경우는 건드리지 않는다. 교환은 `stop_exchange.ps1`이 만드는 `<state_root>\STOP`, 루프는 `agent_bridge stop`이 만드는 `<state_root>\agent\STOP`으로 판단한다. 작업 스케줄러에서 작업을 "끝내기"만 하면 멈춤으로 보고 다시 켠다. 오래 멈추려면 위 명령을 쓴다.
- 새 감시 프로세스는 남아 있는 Syncthing을 이어받아 중복 실행하지 않는다.
- 기록: 루프 쪽 조치는 `...\agent\loop.log`, 교환 쪽 조치는 `%LOCALAPPDATA%\AFDA\<role>\exchange_watchdog.log`에 남는다.
- Pro 시험(9/26 23:09): 교환 감시 프로세스를 끄자 2분 만에 루프가 다시 켰고, 새 감시 프로세스가 남아 있던 Syncthing을 이어받았다.

## 사람이 하는 일

1. Ultra에서 위 설정 명령을 1회 실행한다.
2. 알림이 오면 `work/agent/HUMAN_ACTIONS.md`를 보고 DACON에 zip을 업로드한다. 첫 안전망 zip으로 서버 설치를 조기 검증하는 것을 권장한다.
3. 선택 작업: 시간이 나면 Nexar CSV에서 라벨을 `reviewed`로 검수하거나 S23 촬영 파일을 `data/captures/s23/`에 넣는다. 루프가 변경을 감지해 반영하고, 사람 라벨이 에이전트 라벨보다 우선한다.

## 알려진 한계

- 두 PC가 켜져 있고 로그인된 동안에만 진행한다. 꺼진 동안의 job은 `lost`로 표시되고 에이전트가 새 job으로 재실행을 판단한다.
- 에이전트 라벨은 사람 검수보다 부정확할 수 있다. confidence와 출처별 표본 수를 지표와 함께 보고한다.
- 자체 validation 점수는 공식 점수가 아니다(S2 세부 채점식 미확정). 최종 판단은 DACON 리더보드와 대조한다.
- WSL2/Linux GPU 최종 재현(S0)은 관리자 설치가 필요해 무인 범위 밖이다. Windows GPU 실측과 정적 검사로 대신하고, 이 점을 위험으로 기록한다.
