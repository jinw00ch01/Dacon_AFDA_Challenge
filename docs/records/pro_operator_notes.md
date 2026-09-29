# Pro 운영 메모(운영자 세션)

> Pro 360(CPU 노트북)의 로컬 기록을 GitHub용으로 옮긴 것이다. 사용자 경로·장치 이름·계정 같은 개인 정보는 `<USER_HOME>`, `<pro-host>`, `<email>` 등으로 가렸다. 대회 원본·영상·가중치·토큰은 넣지 않았다.

운영자 Claude 세션이 일시정지·재개, 리더보드 기록, 사람 작업을 적어 둔 메모다.

---

# 재개 메모

> **9/28 20:56 일시정지(사용자: 장소 이동).** 사용자 지시로 Pro를 pause했다. 돌던 사이클 d6e808f271e6(20:53 시작, 결정 13 도메인 대응 0-1)은 끝나게 두었고 job은 없었다. Ultra 운영에도 pause를 요청했다.
> - 재개 방법: `python -m agent_bridge resume`. 재개 후에는 Ultra에도 알린다.
> - 멈춘 시점의 계획은 CLAUDE.md 결정 13(main d751fe7)에 있다. 00:00 제출은 최고 조합 e767d310에 rule3을 더한 zip이고, Ultra가 23:30까지 보고할 예정이었다. 오전 프로브는 S1 e004(공식 형식 Nexar 쌍), S2 자막 점검, S3 symyaw이고, Ultra가 06:00까지 보고할 예정이었다.
> - 00:00 zip이 준비되지 않으면 이미 만들어 둔 e767d310(예상 0.4711)이 대안이다.
> - Stage별 최고는 S1 e001 0.5650, S2 시점 규칙 0.3056, S3 e005+yaw 0.5897이다.

> **v002_s2rule 리더보드(9/27 20:29 제출, 9/28 13:52 전달)**: S1 0.5650 / S2 0.3056 / S3 0.5885, 종합 약 0.4707(현재 최고). v002에서 S2 시점만 결정 12-A 움직임 규칙(진입 = 충돌 − 8)으로 바꿨다. 12-A 채택 확정, 이후 프로브는 s2rule 기준. Pro는 9/27 21:05~9/28 13:49 일시정지 후 재개했다.
>
> **v002 리더보드(9/27 00:08 제출)**: S1 0.5650 / S2 0.2060 / S3 0.5885, 종합 약 0.431(v001 대비 +0.049). S3 e005 유지. 9/27 제출 1회 사용. Pro의 e005 재계산(review e0b15976)은 수치를 모두 재현했다. 자체 진단 S3는 LB보다 약 0.22~0.24 낮지만 방향과 크기가 일치한다. e001·e005 모두 DECELERATING을 예측하지 않는 것이 다음 S3 개선 지점이다.
>
> **2026-09-27 13:19 KST Pro 재개함.** 12:58 부팅 후 교환·루프가 자동으로 올라와 일시정지 상태로 대기했다. 재개 직후 사이클 e75aaa035004가 밤사이 패킷 3개(decision fe3b9e1b·2fbcd9ce, e005 result 91abe1ad)를 처리 중. Ultra 운영에 재개를 알렸다(SendMessage). 아래는 일시정지 당시 기록이다.

## 2026-09-26 23:33 KST 일시정지 — 사용자 이동, 오늘 밤 마무리

- 사용자 지시(Ultra 세션 경유 request 090ceceb): 오늘 밤은 Ultra의 S3 e005 판정과 submit_v002 생성 여부까지만 한다. Pro 에이전트는 마무리 점검(job 0, 미전송 0, pro/* push 완료, main 깨끗 88548d3)을 마치고 "종료 준비 완료" qa e426fe15를 보냈다(Ultra ACK 23:33:06).
- 운영 세션이 23:33에 `agent_bridge pause`. 진행 중인 사이클·job 없음, 미확인 패킷 없음. 교환 서비스는 켜져 있다. 일시정지는 재부팅 후에도 유지된다.
- 리더보드: v001 S1 0.5650 / S2 0.2060 / S3 0.4656(약 0.382). v001b S2 0.1625로 상수 시점 기각 → 결정 11. 다음 제출은 Stage별 최고 조합.
- 오늘 추가: 사람 S23 48개(release s1-s23-real-v1-20260926), S2 사람 검수 22건(release s2-labels-v7-20260926), 교환·루프 상호 자동 복구(e3f728c, 시험 통과).
- **재개**: Pro `.\.venv-pro360\Scripts\python.exe -m agent_bridge resume`(운영 세션에 "재개"라고 해도 됨), Ultra는 Ultra 세션 또는 시작 메뉴 PowerShell에서 `resume`. Pro 에이전트의 다음 할 일은 `docs/STATUS.md`의 "다음 재개 때 할 일"(S3 e005 → v002 diff → S23 e001 → S1 혼합 → 데이터 확장).
- 마감: 9/29 10:00 KST. 하루 3회 제출.
- **Ultra 마무리(9/27 00:06, Ultra 운영 메시지)**: S3 e005가 사전 등록 6조건 게이트를 통과했다(자체 진단 official_s3 0.3512, STOPPED 정밀도 0.9932·재현율 0.5568). `submit_v002.zip`을 만들었다(Ultra `C:\Dacon\Dacon_AFDA_Challenge\work\submit_v002.zip`, SHA f2b158a8effcb170031d5ec1bcf3aaac22316eeaed56ba65c3f712ac9e9bcc41). 구성: S1 e001, S2 v001 모델 시점(상수 아님), S3 e005. validate_zip와 e2e 3-Stage 검사를 통과했다. Ultra 루프도 일시정지했다. 사용자가 9/27에 업로드한다. LB S3가 0.4656보다 낮으면 다음 zip은 S3 e001로 되돌린다.
- Pro 재개 시 처리 대기: result 91abe1ad(e005 독립 재계산 요청, 9/27 00:03 도착).

## 이전: 2026-09-26 17:26 KST 재개 — v001 점수 수신

- v001 리더보드(9/26 16:54 제출): **S1 0.5650, S2 0.2060, S3 0.4656**, 종합 약 0.382, 실행 15분 29초.
- 공식 채점식을 확인해 CLAUDE.md **결정 10**에 기록했다(main d232a2f). S2 = 0.35·충돌 Acc@0.3초 + 0.35·진입 Acc@0.3초 + 0.15·방향 F1 + 0.15·회피 F1. S3 = 0.7·가감속 + 0.3·조향. S1은 Baseline 게이트를 없애고 리더보드로 판단한다.
- Ultra에 피드백 request 35c2b243을 보냄(17:26 ACK). Pro는 재개해 사이클 진행 중. **Ultra는 사용자가 시작 메뉴 PowerShell에서 `resume`해야 움직인다.**
- 목표: v002 9/27 12:00, v003 9/28 12:00, 동결 9/28 22:00. 하루 3회 제출(9/26은 1회 사용).

## 이전: 2026-09-26 16:07 KST 일시중지 — DACON 제출 후 점수 대기

- 사용자가 **submit001.zip을 DACON에 업로드**했다. 업로드는 완료, 점수는 대기 중이다. 사용자가 Pro·Ultra 모두 작업을 멈추게 했다(Ultra는 사용자가 직접 중지).
- Pro: `agent_bridge pause`로 새 사이클을 멈췄다. 교환 서비스는 계속 돈다. CPU job `s1-synth-v1c-codec`(6dfdef7d0601, 결정 9의 코덱 동일 쌍 96개)은 Claude 사용량을 쓰지 않아 끝나도록 두었다(16:20경 완료 예상). 재개하면 에이전트가 QA하고 qa 패킷을 보낸다.
- **제출한 v001 구성**(Ultra 패킷 기준): 세 Stage 모두 첫 학습(e001) 가중치로 만든 안전망이다. 제출 전 package/preflight 정적 검사와 Baseline 예제 종단 추론 검사를 거쳤다.
  - S1 e001(합성 v1 학습): 공식 예제 10개를 전부 RERECORDED로 예측(acc 0.5, macro-F1 0.333).
  - S2 e001(best.pt SHA ecb0c05b): 공식 예제 5개 MAE 1.06초로, 상수 예측 0.78초보다 나쁨.
  - S3: proxy 자체 진단에서 e001 가감속 F1 0.18, 조향 0.41. v001에 e001과 e002 중 어느 쪽이 실렸는지는 Ultra 기록을 확인한다.
  - 목적은 서버 설치·실행 검증이다. 점수 자체는 낮을 것으로 예상한다.

### 점수가 나오면

| 결과 | 할 일 |
|---|---|
| 점수 표시 | 점수(가능하면 Stage별)를 기록하고 Pro·Ultra 둘 다 `resume`. Ultra에 점수를 전달한다(운영 세션이 request 패킷으로 보냄). v002 트랙 진행: S1 결정 9, S2 e003(10Hz·50프레임), S3 개선, 데이터 확장 |
| 설치 오류 | 제출 횟수에 포함되지 않는다. requirements·zip 구조 문제다. DACON 오류 문구를 Ultra에 전달해 수정 → 재제출 |
| 제출(실행) 오류 | 제출 횟수(하루 최대 3회)에 포함된다. DACON 실행 로그·오류 문구를 Ultra에 전달해 원인 수정 → Baseline 예제 종단 추론 재확인 → 재제출 |

재개 명령: Pro `.\.venv-pro360\Scripts\python.exe -m agent_bridge resume`, Ultra(시작 메뉴 PowerShell) `.\.venv-ultra5060\Scripts\python.exe -m agent_bridge resume`. 재개 직후 결정을 반영하게 하려면 `... agent_bridge wake --reason "<내용>"`.

Pro 쪽 대기 중인 일: Ultra 병합 대기 `pro/s1-v1c-codec` 5b1b574(request 7ee18d9b), 코덱 동일 쌍 QA와 qa 발송, Ultra의 S1 v1c 재학습·S2 e003 결과 검토, 확장 데이터(Nexar 640px, comma 클립) 수신 후 라벨·합성.

---

## 이전: 2026-09-25 15:02 KST 일시중지

> **2026-09-26 15:12 KST Pro 재개함.** Pro는 14:58에 재부팅된 뒤 루프·교환 서비스가 자동으로 다시 올라왔고, 일시중지 상태를 유지하다가 `resume`으로 재개했다. 재개 시점에 Ultra는 9/25 15:03 이후 패킷·커밋이 없었다(Ultra 루프 확인 필요). 아래는 일시중지 당시 기록이다.

사용자 이동으로 **Pro 루프를 일시중지**했다(`agent_bridge pause`). 교환 서비스(Syncthing)는 계속 돈다. Ultra는 이 메모 작성 시점에 계속 작동 중이다.
마감: 제출 **9/29 10:00 KST**. 안전망 v001 목표 **9/26 12:00**. 확장 데이터 재학습 **9/28 18:00**. 최종 동결 **9/28 22:00**.

## 1. 재개 방법

Pro(이 PC): 시작 메뉴의 Windows PowerShell에서 실행한다(Claude 세션에 "재개"라고 해도 된다).

```powershell
cd C:\Dacon\Dacon_AFDA_Challenge_git
.\.venv-pro360\Scripts\python.exe -m agent_bridge resume
.\.venv-pro360\Scripts\python.exe -m agent_bridge status
```

Ultra를 멈춰야 할 때(Ultra도 옮기거나 끌 때만): Ultra의 시작 메뉴 Windows PowerShell에서 실행한다. Claude 앱 안에서 실행하면 샌드박스 때문에 전달되지 않는다.

```powershell
cd C:\Dacon\Dacon_AFDA_Challenge
.\.venv-ultra5060\Scripts\python.exe -m agent_bridge pause     # 재개: ... resume
```

재개 후 확인할 것:
- `status`의 heartbeat가 최근 시각인지, `usage_limit_until_utc`가 없는지
- `sent_unacked`가 비어 있는지. Ultra가 켜져 있으면 1~2분 안에 ACK가 온다.

## 2. 멈춘 시점의 상태

| 영역 | 상태 |
|---|---|
| S2 라벨 | 104개 완료(v6). 에이전트 충돌 프레임과 Nexar 사건 시각의 오차 중앙값 0.09초 |
| S1 합성 | v1 120개. Ultra 채택(release `s1-synth-v1`) |
| S3 기준 | 규칙 v1b, 조향 부호(양수 = LEFT) 채택 |
| S3 학습 | e001: 가감속 F1 0.18(CONSTANT로 붕괴), 조향 0.41. **e002 채택**(가감속을 속도 회귀 + v1b 규칙으로 계산). Pro가 계산 순서 정정 요청을 보냄: np.gradient 후 평활 |
| S2 학습 | e001: 지표는 재현됐지만 상수 시점 사전분포보다 11배 나쁨. **e002 채택**(무작위 시간 crop, 상수 사전분포 기준 병기) |
| S1 학습 | e001: val macro-F1 1.0(synthetic). 너무 쉬워 지름길 의심. **Pro가 검토하던 중에 멈춤**(사이클 `e3fdeb296b51`) |
| 제출물 | Ultra가 안전망 e2e preflight(`a950b51`)와 Windows DataLoader 수정(`fa51e4d`)을 올림. v001 조립 중 |
| 데이터 확장 | 결정 8 승인, Ultra ACK. 순서는 v001 먼저, 그다음 Nexar 640px 사본과 S1 클립 handoff. Pro는 확장 라벨 기록 지원을 `pro/s2-ext-labels`(72c7258)로 병합 요청함 |
| 운영 | Pro 오늘 17사이클 모두 성공(추정 $49, Max 한도 차감). 추가 사용량 끔 |

## 3. 재개 후 할 일

사람:
1. Pro `resume`. Ultra도 멈췄다면 Ultra도 `resume`.
2. v001 알림(`work/agent/HUMAN_ACTIONS.md`)이 오면 DACON에 업로드한다. 서버 설치·실행을 조기에 검증하는 목적이다. 설치 오류는 제출 횟수에서 차감되지 않는다. 하루 제출은 최대 3회다.
3. (선택, 효과 큼) S23 실촬영 12~16회 → `data/captures/s23/`. S1이 합성에서 1.0이라 실제 재촬영 검증이 가장 필요하다.
4. (선택) S2 사람 검수 22건(Pro `docs/STATUS.md`의 Blocked 목록).

에이전트(재개하면 자동):
- Pro: S1 e001 검토 마무리 → 확장 Nexar 640px 사본이 오면 접촉 확인과 끼어들기 사례 상세 라벨(약 150개까지) → 새 comma 클립으로 S1 합성 확대 → S3·S2 e002 결과 검토
- Ultra: v001 조립·preflight·보고 → S3 e002, S2 e002 → comma 약 200구간·Nexar 약 300개 다운로드와 전처리 → handoff → 확장 데이터 재학습

운영 세션(Claude)이 확인할 것:
- `pro/s2-ext-labels`가 병합됐는지
- 재개 직후 사이클이 백오프(실패 재시도)에 걸렸는지. 덮개를 닫아 도중에 끊긴 사이클은 실패로 한 번 기록될 수 있다.
- guard 오탐이 남았는지(Pro `docs/STATUS.md`의 가드 제약 항목은 322ed7c에서 이미 수정됨)

## 4. 위험

- S1: 합성 데이터만 있어 실제 재촬영에서 성능이 크게 떨어질 수 있다.
- S2: 모델이 아직 상수 사전분포보다 나쁘다. e002와 확장 데이터가 핵심이다.
- Linux·L40S 서버 호환성은 검증하지 못했다. v001을 일찍 업로드하는 것으로 대신한다.
- Max 한도에 걸리면 두 PC가 초기화 시각까지 쉰다. 라벨링을 늘리면 한도 소모도 늘어난다.
