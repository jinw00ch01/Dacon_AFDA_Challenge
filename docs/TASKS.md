# 실행 대기열

| ID | 담당 | 작업 | 선행 | 완료 증거 |
|---|---|---|---|---|
| H0 | Ultra | 하네스 설치·분석·로컬 검증 | 없음 | STATUS.md 및 runs |
| H1 완료 | Pro / Ultra | Pro 실물 검증·반환 ZIP 무결성·수정 병합·Ultra 재검증 완료 | H0 | STATUS.md의 왕복 검증 기록 |
| H2 완료 | Ultra | 공개 GitHub origin 연결·README·코드 게시 | H0 | jinw00ch01/Dacon_AFDA_Challenge |
| H3 준비 완료 | Pro 실행 / Ultra 안내 | 새 clone·CPU 환경·검수 세션·반환 명령 | H2 | PRO360_STEPS.md; 새 clone의 Pro 실물 실행은 대기 |
| D4 계획 완료 | 사용자 촬영·검수 | 1인6시간30분, S23 Ultra 24원본×2회 촬영 | 허용된 영상 확보 | LABELING_AND_S23_PLAN.md 및 docs/templates/s23_capture_plan.csv |
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
DoTA 검수 후보2,682개 생성. 독립 주행1개라 D3 그룹 분리 학습셋은 아직 미완성이다.
