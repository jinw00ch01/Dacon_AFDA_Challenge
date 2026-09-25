# AFDA — Claude Code 운영 규약

@AGENTS.md

위 AGENTS.md는 기본 규약이다. 아래 **2026-09-25 사용자 결정**이 AGENTS.md와 docs/의 Codex 전제 문구보다 우선한다.
운영 설명: [docs/CLAUDE_OPERATION.md](docs/CLAUDE_OPERATION.md).

## 이 PC의 역할

- 역할은 `configs/local-exchange.json`의 `role`(ultra5060 | pro360)이다. `CLAUDE.local.md`가 `.claude/roles/<role>.md`를 불러온다. 파일이 없으면 직접 읽는다.
- Ultra(RTX 5060): 총괄. 데이터 release 동결, spec·result·decision 작성, GPU 학습, main 통합, submit.zip 생성.
- Pro 360(CPU): 데이터 QA, S2 에이전트 라벨, S1 합성 재촬영, CPU 지표 재계산, review와 제안 1개.
- 무인 실행(`AFDA_AUTONOMOUS=1`)은 `python -m agent_bridge loop`가 `claude -p`로 시작한다. 절차: `.claude/skills/afda-cycle/SKILL.md`.

## 2026-09-25 사용자 결정

1. Codex 작업 대신 **PC별 Claude Code 에이전트 + agent_bridge 루프**로 운영한다. 사람은 Ultra 최초 설정과 DACON 업로드만 한다.
2. **S2 라벨은 에이전트가 만들 수 있다.** `scripts/stage2_agent_label.py`로 `data/derived/labels/agent/`에 `agent_labeled`(모델·UTC·confidence·근거)로 따로 기록한다. 사람 CSV의 `review_status=reviewed` 행이 항상 우선한다. 에이전트는 사람 CSV를 수정하지 않고 `reviewed`로 표시하지 않는다. 지표 보고에는 라벨 출처(human/agent) 수를 함께 적는다.
3. **S1은 합성 재촬영과 S23 실촬영을 병행한다.** 실촬영 파일이 있으면 검증 split에 우선 사용한다. 합성본만으로 측정한 점수는 "synthetic"으로 표시한다.
4. **권한은 허용목록 + guard 훅**(`.claude/hooks/guard.py`)이다. 거부되면 우회하지 말고 허용된 방법(venv python 스크립트, agent_bridge)으로 바꾼다.
5. **Git: Ultra만 main에 push한다.** Pro는 `pro/<topic>` 브랜치를 worktree(`../Dacon_AFDA_Challenge_wt/<topic>`)에서 만들어 push하고, Ultra가 검토 후 병합한다.
6. **마감: 제출 2026-09-29 10:00 KST (01:00Z).** 에이전트는 업로드하지 않는다. 검증된 zip을 만들고 `submission_candidate`로 보고한다.
7. 라벨링용 프레임은 640px 이하로 줄여 Claude(Anthropic API)에만 보여 준다. 그 밖의 외부 서비스로 영상·프레임·라벨을 보내지 않는다.

## 공통 실행 규칙

- Python은 역할 venv만 사용한다: `.venv-<role>/Scripts/python.exe`. 패키지 설치도 이 venv에만 하고 버전을 고정한다.
- 셸 명령은 10분 안에 끝나야 한다. 더 긴 학습·평가·대량 처리는 `python -m agent_bridge job start --kind cpu|gpu --timeout <초> --name <이름> -- <명령>`으로 큐에 넣는다. 완료되면 루프가 다음 사이클을 깨운다.
- 상대 PC와의 통신은 패킷으로만 한다: `python -m agent_bridge publish --kind <kind> --body <json> [--attach <폴더>]`. `C:\Dacon\AFDA_Exchange`에 직접 쓰지 않는다.
- 상태의 근거는 대화가 아니라 파일이다: `docs/STATUS.md`(로컬, Git 제외), `python -m agent_bridge status`, 패킷, `runs/`.
- 사용자가 읽는 글(`docs/STATUS.md`, 사이클 보고의 summary·human_actions, 패킷의 subject·body)은 한국어로 쓴다. 코드·명령·식별자는 그대로 둔다.
- 보호 경로(읽기만 가능): `data/external/`, `data/captures/`, `Baseline/`, 사람 CSV 2개, `data/derived/labels/human/`, `data/derived/peer_reviews/`, 수신 패킷.
- 점수는 검증 split에서 측정한 것만 보고한다. 없는 값은 null로 둔다. 가중치 로딩이 실패하면 랜덤 가중치로 대체하지 않는다.
- 제출 코드는 오프라인에서 동작해야 한다: `weights=None`로 모델을 만든 뒤 `load_state_dict`로 가중치를 불러오고, 추론 중 다운로드하지 않는다. 전체 60분, 설치 10분 제한을 지킨다(evaluation.md).
