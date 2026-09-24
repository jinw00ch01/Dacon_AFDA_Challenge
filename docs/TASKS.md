# 실행 대기열

| ID | 담당 | 작업 | 선행 | 완료 증거 |
|---|---|---|---|---|
| H0 | Ultra | 하네스 설치·분석·로컬 검증 | 없음 | STATUS.md 및 runs |
| H1 완료 | Pro / Ultra | Pro 실물 검증·반환 ZIP 무결성·수정 병합·Ultra 재검증 완료 | H0 | STATUS.md의 왕복 검증 기록 |
| H2 완료 | Ultra | 공개 GitHub origin 연결·README·코드 게시 | H0 | jinw00ch01/Dacon_AFDA_Challenge |
| H3 완료 | Pro / Ultra | 새 clone·CPU 환경·실물 CPU 검증 | H2 | 2026-09-24 수신 result와 로컬 STATUS.md |
| H4 실제 왕복 완료 | 양쪽 | Syncthing 자동 전송, 허용 CPU 작업 큐 | H2 | Pro import·미리보기·contract tests 결과; Codex 자동 판단은 별도 |
| A0 명세 완료 | Ultra | PC별 Codex 역할, 실험 파일 규약, 데이터 게이트 | H4 | AGENT_OPERATING_DECISION.md 및 연결 문서 |
| A1 구현 대기 | Ultra 구현 / Pro 검증 | 실험 패킷·ACK·장부·고정 commit 실행·중단 복구 | A0 | EXPERIMENT_PROTOCOL.md의 구현 목록과 왕복 검사 |
| A2 연결 대기 | 각 PC | 로컬 Codex wake·새 결과당 한 번 검토·예산 제한 | A1 및 데이터 게이트 | 재시작/중복/변경 없음 검사; 현재 활성화하지 않음 |
| D4 계획 완료 | 사용자 촬영·검수 | 기본390분 + 선별30~45분, S23 Ultra 24원본×2회 | 허용된 영상 확보 | DATA_PREPARATION_SPEC.md; 실제 촬영·라벨은 대기 |
| L1 안내 완료 | 사용자 관리자 설치 / Ultra 검증 | WSL2 Ubuntu24.04 + CUDA 연산 | Windows 관리자 권한/재부팅 | WSL2_GPU_STEPS.md; 설치와 GPU Linux 실측은 대기 |
| D0 | Pro 조사 / 사용자 자료 | 공식 데이터 설명·출처 기록 확보; 세부 평가식·자원별 이용조건 보완 | 없음 | data_description.md 및 docs/reference/official_sources_20260923.md |
| D1 | Pro 조사 / Ultra 검증 | S3 시간축 원본 및 10Hz 대응 확인 | D0 | timebase 매핑·경계 테스트 |
| D2 | Pro | S2 진입·회피·방향 라벨 가이드와 파일럿 | D0 | 미라벨 mask 포함 labels v1 |
| D3 | Pro | 원본·파생·같은 주행 묶음 split manifest | D0 | train/val 그룹 교집합0 |
| M0 | Ultra | streaming decoder와 safe CLI, AMP 작은 학습 | D1/D3 | RAM/VRAM/backward/checkpoint 검증 |
| M1 | Ultra | S2 features cache + temporal multihead | D2/D3 | 분할별 지표/오류 사례 |
| M2 | Ultra | S3 시간구간 학습·STOPPED 제외 조향 평가 | D1/D3 | 10Hz coverage 및 클래스별 지표 |
| M3 | Ultra | S1 재촬영 데이터 개선 및 sampling 일치 | D3 | 원본 그룹 외부 검증 |
| E0 | Ultra | 실제 가중치로 3-Stage end-to-end | M1/M2/M3 | 예측 CSV 계약 + 재실행 |
| L0 CPU 완료 | Ultra | QEMU CPU Linux 오프라인18개 테스트 통과; CUDA 컨테이너 정의 작성 | H0 | environment/README.md 및 로컬 실행 로그 |
| S0 | 사용자 GPU Linux 활성화 / Ultra | 실제 모델 Linux 오프라인 최종 재현 | E0/L0 | 전체 시간·메모리·네트워크 검증 |

작업 상태의 현재 사실은 STATUS.md에 기록한다. H0가 H1이나 S0 완료를 의미하지 않는다.

데이터 파일럿 완료: comma2k19 영상1,200프레임 디코드·10Hz599행 센서 정렬,
DoTA 검수 후보2,682개 생성. 최초 파일럿은 주행1개였으며 이후 아래 자료를 추가했다. D3 전체 완료에는 Nexar 사건 그룹과 라벨 검수가 여전히 필요하다.

2026-09-24 추가 확보: comma의 서로 다른 날짜24개 주행(16/4/4 분할)과 Nexar train104개 실제 영상을 수집했다.
S1 원본 부족은 해소했고 실제 휴대폰 촬영은 대기다. S2는 Nexar 실제 접촉 여부·진입 적합성·중복 사건·정답 검수가 남았다.
구체적인 원본/파생 경로와 결과는 DATA_SOURCING_EXECUTION.md 및 DATA_ACQUISITION_RESULT.json을 따른다.
