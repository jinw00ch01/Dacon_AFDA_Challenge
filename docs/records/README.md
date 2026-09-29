# 원본 기록 모음

대회 기간(2026-09-23~09-28)에 두 PC의 Claude Code 에이전트와 운영 세션이 남긴 기록을, 대회가 끝난 뒤(9/29) 그대로 옮겨 둔 폴더입니다.

- 장치 이름과 사용자 경로만 가렸습니다.
- 대회 원본, 영상, 프레임, 가중치, 라벨 CSV, 토큰은 넣지 않았습니다.
- 사람이 읽기 좋게 줄인 이야기는 [../JOURNEY.md](../JOURNEY.md)에 있습니다.
- Stage별 실험 정리는 [../EXPERIMENTS.md](../EXPERIMENTS.md)에 있습니다.

## Ultra(GPU PC)

| 파일 | 내용 |
|---|---|
| [ultra_status_log.md](ultra_status_log.md) | Ultra 에이전트의 사이클별 작업 로그(원본 `docs/STATUS.md`). 사람이 넣은 지시("사람 입력")도 들어 있습니다. 위쪽이 최신입니다. |
| [packets_index.md](packets_index.md) | 두 PC가 주고받은 실험 패킷 158건의 목록(요청·검증·리뷰·결과·결정) |

## Pro(CPU PC)

| 파일 | 내용 |
|---|---|
| [README_pro.md](README_pro.md) | Pro 기록의 자세한 목차 |
| [pro_status_log.md](pro_status_log.md) | Pro 에이전트의 작업 로그(원본 `docs/STATUS.md`) |
| [pro_cycle_log.md](pro_cycle_log.md) | Pro 사이클 84회의 시각, 깨운 이유, 비용, 요약 |
| [pro_operator_notes.md](pro_operator_notes.md) | Pro 운영 세션 메모(일시정지·재개, 리더보드 기록) |
| [pro_human_actions.md](pro_human_actions.md) | 에이전트가 사람에게 요청한 작업 목록 |
| [pro_notes/](pro_notes/) | main에 없던 분석 메모(S23 육안 확인, 게이트 역검증, Nexar 분류 프롬프트) |
| [pro_tools/](pro_tools/) | Pro가 검증에 쓴 분석 스크립트와 목록 |

## 이 기록을 읽는 요령

- **결정의 근거:** 사람이 내린 큰 결정 13건은 저장소 최상위의 [CLAUDE.md](../../CLAUDE.md)에 있습니다.
- **ID로 찾기:** 로그에 나오는 8자리 ID(예: `34d5f003`)는 패킷 ID입니다. [packets_index.md](packets_index.md)에서 검색하면 제목과 날짜를 찾을 수 있습니다.
- **수치의 출처:** "자체 검증" 수치는 우리가 만든 검증셋에서 잰 값입니다. "리더보드" 수치는 DACON 공개 리더보드 값입니다. 두 값은 자주 어긋났습니다([../JOURNEY.md](../JOURNEY.md) 참고).
