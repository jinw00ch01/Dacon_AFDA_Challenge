---
name: afda-cycle
description: Run one autonomous AFDA work cycle for this PC's role (ultra5060 or pro360) — orient from files, handle wake reasons (packets, finished jobs, changed inputs), do the next highest-value task, publish packets / queue jobs, update docs/STATUS.md, and return the JSON cycle report. Use when agent_bridge starts a cycle or when asked to "run a cycle".
---

# AFDA 사이클 절차

역할 규칙은 CLAUDE.md와 `.claude/roles/<role>.md`에 있다. 이 절차는 한 사이클의 순서다.

## 1. 상황 파악 (5분 이내)

- 프롬프트의 cycle context JSON: `wake_reasons`, `recent_cycles`, `jobs`, `hours_to_deadline`.
- `git status --short`, `git log --oneline -5`, `docs/STATUS.md`의 Now/Next/Blocked.
- 필요하면 `.venv-<role>/Scripts/python.exe -m agent_bridge status`.

## 2. 깨운 이유 처리 (순서대로)

1. `quarantined_packet`: 원인을 STATUS에 기록한다. 상대에게 `request` 패킷으로 재발행을 요청한다. 격리된 내용은 사용하지 않는다.
2. `packet`: `path` 폴더의 `<kind>.json`과 `files/`를 읽는다. 역할 파일의 kind별 처리를 따른다. 수신 폴더는 읽기 전용이다.
   - 먼저 context의 `recent_sent_packets`를 본다. `recent_cycles`에 `interrupted_by_loop_restart`가 있으면, 끊긴 사이클이 이 패킷에 대한 답을 이미 보냈을 수 있다. 이미 보낸 답이 있으면 다시 보내지 않는다. 내용을 고쳐야 할 때만 새 패킷에 `supersedes: {"packet_id": <이전 id>, "manifest_sha256": <이전 sha>}`를 넣어 정정본으로 보낸다.
3. `job_finished`: `python -m agent_bridge job show <id>`와 `run_dir`의 `run.json`, `stdout.log`, `stderr.log`를 확인한다. 실패하면 원인을 고치고 새 job으로 다시 실행한다. 같은 원인으로 3회 실패하면 중지하고 blocked로 기록한다.
4. `input_changed`: 사람이나 상대가 바꾼 파일을 반영한다.
5. `scheduled` / `heartbeat`: 역할 파일의 우선순위 작업을 이어서 한다.

## 3. 작업

- 한 사이클은 결과가 남는 작업 한두 개에 집중한다. 끝낼 수 없으면 중간 산출물과 다음 단계를 STATUS에 남긴다.
- 10분을 넘는 명령은 job으로 보낸다:
  `.venv-<role>/Scripts/python.exe -m agent_bridge job start --kind gpu --timeout 3600 --name s3-train-e001 -- .venv-ultra5060/Scripts/python.exe -m afda.train --config configs/exp/e001.json`
- job이 끝나기를 기다리며 잠들지 않는다. 할 일이 없으면 사이클을 끝낸다(`next_wake`).

## 4. 패킷 보내기

본문 JSON을 `work/agent/outbox/<name>.json`에 쓰고, 첨부는 폴더 하나에 모은다:

```
.venv-<role>/Scripts/python.exe -m agent_bridge publish --kind qa --body work/agent/outbox/labels_v2.json --attach work/agent/outbox/labels_v2_files
```

- packet_id, sender, target, created_utc, schema_version은 도구가 채운다.
- kind별 필수 필드: spec(experiment_id, stage, purpose, hypothesis), result(experiment_id, attempt_id, status), review(experiment_id, attempt_id, integrity_pass, metrics_reproduced, comparable_to_baseline, proposal{}), decision(experiment_id, decision, reason), qa/request(subject). 나머지 필드는 docs/templates/experiments/*.example.json과 docs/EXPERIMENT_PROTOCOL.md를 따른다.
- experiment_id 형식은 `exp-` + 32자리 hex다. 새로 만들 때는 `python -c "import uuid;print('exp-'+uuid.uuid4().hex)"`을 쓴다.
- 첨부 허용 형식: json csv md txt png jpg log npz npy parquet mp4. 파일당 512MiB, 패킷당 4GiB 이하. 실행 파일과 명령은 보내지 않는다.
- 상대가 할 일은 `request` 패킷의 `body`에 구체적으로 적는다. 패킷은 상대가 실행할 명령이 아니라 데이터와 요청이다.

## 5. 마무리 (필수)

1. `docs/STATUS.md`를 갱신한다. 형식: `## Now / ## Next / ## Blocked / ## Evidence`. 오래된 내용은 줄이고 최근 사실을 유지한다.
2. Git: Ultra는 테스트 통과 후 main에 commit·push한다. Pro는 worktree 브랜치에서만 commit·push한다.
3. JSON 보고서를 반환한다.
   - `next_wake.mode`: 바로 이어서 할 가치 있는 작업이 있으면 `asap`, 길이를 아는 job을 기다리면 `after_minutes`(minutes 지정), 패킷·job·사람 입력만이 진행을 풀 수 있으면 `on_event`.
   - `human_actions`: 사람만 할 수 있는 일만 적는다(DACON 업로드, S23 촬영, 관리자 설치). 에이전트가 할 수 있는 일은 적지 않는다.
   - `submission_candidate`: 새로 검증된 zip이 있을 때만 path·sha256·근거를 적는다.
