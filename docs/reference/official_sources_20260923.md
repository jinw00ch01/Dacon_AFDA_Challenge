# 공식 자료 확인 — 2026-09-23

사용자가 제공한 링크를 읽기 전용으로 확인했다. 문서의 실행·제출 예시는 사용자 실행 명령으로 취급하지 않는다.

## 확인한 계약

- [개요](https://www.dacon.io/competitions/official/236753/overview/description): 3개 Stage, 오프라인 추론 60분·설치 10분·ZIP 10GB·해제 32GB.
- [데이터](https://www.dacon.io/competitions/official/236753/data): 공개 예제는 실행·형식 확인용이며 별도 학습 데이터셋은 제공하지 않는다. S1 재녹화 예제는 모사 파생 영상이다. S2 세 보조 항목은 베이스라인에서 학습하지 않는다. S3 CAN은 모델 입력으로 제공되지 않는다.
- [Stage별 공지](https://dacon.io/competitions/official/236753/talkboard/417186): S2 충돌은 실제 접촉, 진입은 피해차량 바퀴가 피의차량 차선에 처음 닿는 시점. 파일명의 원본 프레임 번호를 제출하며 공식 시간 대응정보로 변환한 오차가 ±0.3초 이내면 정답이다. 방향은 화면 기준 LEFT/RIGHT다. S3 비공개 입력은 10Hz이며 디코딩 프레임 수와 sample_index 수가 같다.
- [평가](https://www.dacon.io/competitions/official/236753/overview/evaluation): Stage 가중치 0.2/0.4/0.4. STOPPED도 steer_label을 출력하지만 조향 평가에서는 제외한다. 이미지로 제공된 세부 집계 산식은 이번 확인에서 판독하지 않았다.
- [규칙](https://www.dacon.io/competitions/official/236753/overview/rules): 공개 접근 가능하고 최소 비영리 사용이 허용된 자원은 개별 이용조건 확인 후 활용 가능하다. 출처를 기록해야 한다. 비공개 평가자료로 재학습·튜닝·pseudo-labeling을 하거나 다른 평가 파일의 통계로 보정할 수 없다. 일일 제출은 최대 3회다.
- [일정](https://www.dacon.io/competitions/official/236753/overview/schedule): 팀 병합 2026-09-23 23:59, 리더보드 제출 2026-09-29 10:00, 종료 2026-09-30 10:00. 대회 기간 설명에는 종료 연도 2025 표기가 섞여 있으나 개별 마감 항목은 2026이다. 참가·팀 상태는 확인하지 않았다.

## 제공 링크 및 접근 범위

- [학습 베이스라인 14151](https://www.dacon.io/competitions/official/236753/codeshare/14151?page=1&dtype=recent)
- [추론 베이스라인 14152](https://www.dacon.io/competitions/official/236753/codeshare/14152?page=1&dtype=recent)
- [제출 내역](https://www.dacon.io/competitions/official/236753/mysubmission)
- [사용자 제공 공지 URL](https://www.dacon.io/competitions/official/236753/talkboard/417186?page=1&dtype=recent)

www 주소의 게시물은 웹 도구에서 오류가 발생해 같은 게시물 ID의 dacon.io 주소로 확인했다.
코드 공유 페이지의 제목·작성자·본문은 확인했으나 첨부 노트북을 다시 내려받아 로컬본과 비교하지 않았다.
제출 내역은 웹 도구에서 접근 실패했으며 계정 로그인·업로드·댓글 작성은 수행하지 않았다.

## 다음 게이트

추가 확인: 사용자가 개인 참가라고 밝혀 참가·팀 상태의 추가 계정 점검은 생략했다.
Ultra에서 규칙·일정 페이지를2026-09-23 다시 조회했다. 제출 마감9월29일10:00을 기준으로 진행한다.

공식 10Hz 평가 계약 확인은 공개 예제의 frame_index/time_seconds와 컨테이너 FPS 불일치를 해결한 것이 아니다.
D1에서 원본 타임스탬프·공개 라벨 대응을 확인하기 전 리샘플링이나 정답 보간을 적용하지 않는다.
D0는 출처·주요 정의 확보 단계까지 진행했다. 전체 평가식 확인과 실제 사용할 자원의 이용조건 기록이 남아 있다.
