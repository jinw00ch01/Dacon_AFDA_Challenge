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
8. **데이터 확장(14:20 승인).** 안전망 v001은 지금 데이터로 먼저 만든다. 확장은 GPU 학습과 병행해 준비하고, v002 이후 버전에 반영한다.
   - **S3:** comma2k19를 약 3~4시간(약 200구간)으로 늘린다. 센서 로그를 먼저 받아 정지·회전·가감속이 많은 구간을 고르고, origin_group(주행) 단위 split을 유지한다. 기존 validation 4개 source는 e001과 비교하는 고정 기준으로 남긴다.
   - **S2:** Nexar train positive를 약 300개 더 받는다. HF 인증은 Ultra에만 있다. 충돌 시점은 Nexar `time_of_event`로 만든다. 근거: 에이전트 라벨 59개와 비교했을 때 오차 중앙값이 0.09초이고, 52개가 0.5초 이내다. `label_source=nexar_event`로 표시하고, 접촉을 확인하기 전에는 `contact_unverified`로 둔다. 진입 시점·방향·회피 공간은 Pro가 차선 진입 사례 위주로 라벨한다.
   - **S1:** 확장된 comma 구간에서 새 source를 골라 합성 재촬영 source를 약 100개로 늘린다.
   - **수집 스크립트:** 기존 상한(Nexar positive 100개, comma 24개·날짜당 1구간)은 이 범위까지 올려도 된다. 고정 revision과 SHA 기록, 라이선스 원문 보관은 지킨다.
   - **Pro 디스크:** 여유는 약 24GB다. Pro로 보내는 영상은 원본과 디코드 프레임 수가 같은 640px 사본으로 만들고, 프레임 수 일치를 확인해 보낸다. Pro는 새 데이터를 합계 8GB 이하로 유지한다.

## 공통 실행 규칙

- Python은 역할 venv만 사용한다: `.venv-<role>/Scripts/python.exe`. 패키지 설치도 이 venv에만 하고 버전을 고정한다.
- 셸 명령은 10분 안에 끝나야 한다. 더 긴 학습·평가·대량 처리는 `python -m agent_bridge job start --kind cpu|gpu --timeout <초> --name <이름> -- <명령>`으로 큐에 넣는다. 완료되면 루프가 다음 사이클을 깨운다.
- 상대 PC와의 통신은 패킷으로만 한다: `python -m agent_bridge publish --kind <kind> --body <json> [--attach <폴더>]`. `C:\Dacon\AFDA_Exchange`에 직접 쓰지 않는다.
- 상태의 근거는 대화가 아니라 파일이다: `docs/STATUS.md`(로컬, Git 제외), `python -m agent_bridge status`, 패킷, `runs/`.
- 사용자가 읽는 글(`docs/STATUS.md`, 사이클 보고의 summary·human_actions, 패킷의 subject·body)은 한국어로 쓴다. 코드·명령·식별자는 그대로 둔다.
- 보호 경로(읽기만 가능): `data/external/`, `data/captures/`, `Baseline/`, 사람 CSV 2개, `data/derived/labels/human/`, `data/derived/peer_reviews/`, 수신 패킷.
- 점수는 검증 split에서 측정한 것만 보고한다. 없는 값은 null로 둔다. 가중치 로딩이 실패하면 랜덤 가중치로 대체하지 않는다.
- 제출 코드는 오프라인에서 동작해야 한다: `weights=None`로 모델을 만든 뒤 `load_state_dict`로 가중치를 불러오고, 추론 중 다운로드하지 않는다. 전체 60분, 설치 10분 제한을 지킨다(evaluation.md).
- GitHub CI(`.github/workflows/contracts.yml`)는 Python 3.12에 `psutil`만 설치하고 `unittest discover -s tests`를 돌린다. numpy·pandas·torch·torchvision·cv2가 필요한 테스트는 파일 첫머리에서 없으면 `unittest.SkipTest`를 올린다(예: `tests/test_afda.py`의 `ML_MISSING`). 로컬 venv 통과를 CI 통과로 보지 않는다.
