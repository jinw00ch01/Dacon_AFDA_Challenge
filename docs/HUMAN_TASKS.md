# 사람이 하는 작업: S23 실촬영과 S2 검수

작성: 2026-09-26. 두 작업 모두 **Pro 노트북**에서 한다. 프로젝트 폴더는 `C:\Dacon\Dacon_AFDA_Challenge_git`이다.
결과를 아래의 정해진 위치에 두면 끝이다. Pro 에이전트가 1~2분 안에 감지해 QA하고, 교환 서비스가 Ultra로 자동 전달한다.
[PRO360_STEPS.md](PRO360_STEPS.md) 6장의 ZIP·USB 전달은 예전 방식이라 쓰지 않는다.
[DATA_START_HERE.md](DATA_START_HERE.md)에 적힌 `C:\Dacon\Dacon_AFDA_Challenge\...` 경로는 Ultra 기준이다.

추천 순서: S23 실촬영을 먼저 한다(다른 방법으로는 얻을 수 없는 실제 재촬영 데이터). S2 검수는 그다음에 한다.

## 1. S23 Ultra 실촬영 (Stage 1)

자세한 설정과 품질 기준: [LABELING_AND_S23_PLAN.md](LABELING_AND_S23_PLAN.md)의 "촬영 공간과 화면", "S23 Ultra 설정", "촬영 순서와 품질 판정".

| 무엇 | 정확한 위치 |
|---|---|
| **촬영 파일을 넣을 곳** | `C:\Dacon\Dacon_AFDA_Challenge_git\data\captures\s23\` (아직 없다. `data` 폴더 안에 `captures`, 그 안에 `s23`을 새로 만든다. 이름은 소문자 그대로) |
| Pro 화면에서 재생할 클립(C1·C2) | `C:\Dacon\Dacon_AFDA_Challenge_git\data\derived\comma_subset_v1\s1_playback\SRC0xx_ORIGINAL.mp4` |
| Ultra 화면에서 재생할 클립(C3·C4) | Ultra의 `C:\Dacon\Dacon_AFDA_Challenge\data\derived\comma_subset_v1\s1_playback\SRC0xx_ORIGINAL.mp4` (없으면 Pro의 같은 파일을 USB로 복사) |
| 촬영표(48행, 조건·파일명) | `C:\Dacon\Dacon_AFDA_Challenge_git\data\derived\comma_subset_v1\s23_capture_ready.csv` |

### 우선 촬영할 16테이크 (검증·시험용)

결정 9·10에 따라 S1에서 가장 우선하는 검증 기준이 된다. 시간이 남으면 나머지 32테이크(학습용)도 같은 방식으로 찍는다.

| 원본 클립 | 조건 | 재생 화면 | 밝기 | 각도 | 저장 파일 이름 |
|---|---|---|---:|---:|---|
| SRC017 | C1 | Pro | 70% | 정면 | `SRC017_C1_take01.mp4` |
| SRC017 | C4 | Ultra | 40% | 약 20° | `SRC017_C4_take01.mp4` |
| SRC018 | C2 | Pro | 40% | 약 20° | `SRC018_C2_take01.mp4` |
| SRC018 | C3 | Ultra | 70% | 정면 | `SRC018_C3_take01.mp4` |
| SRC019 | C1 | Pro | 70% | 정면 | `SRC019_C1_take01.mp4` |
| SRC019 | C4 | Ultra | 40% | 약 20° | `SRC019_C4_take01.mp4` |
| SRC020 | C2 | Pro | 40% | 약 20° | `SRC020_C2_take01.mp4` |
| SRC020 | C3 | Ultra | 70% | 정면 | `SRC020_C3_take01.mp4` |
| SRC021 | C1 | Pro | 70% | 정면 | `SRC021_C1_take01.mp4` |
| SRC021 | C4 | Ultra | 40% | 약 20° | `SRC021_C4_take01.mp4` |
| SRC022 | C2 | Pro | 40% | 약 20° | `SRC022_C2_take01.mp4` |
| SRC022 | C3 | Ultra | 70% | 정면 | `SRC022_C3_take01.mp4` |
| SRC023 | C1 | Pro | 70% | 정면 | `SRC023_C1_take01.mp4` |
| SRC023 | C4 | Ultra | 40% | 약 20° | `SRC023_C4_take01.mp4` |
| SRC024 | C2 | Pro | 40% | 약 20° | `SRC024_C2_take01.mp4` |
| SRC024 | C3 | Ultra | 70% | 정면 | `SRC024_C3_take01.mp4` |

### 순서

1. S23: 카메라 → 더보기 → **프로 동영상**. 후면 1×, 가로, FHD 1920×1080 30fps, 셔터 1/60, ISO 100(50~400에서 조정 후 고정), WB 약 5000K, 초점 고정. HDR·Auto FPS·흔들림 보정은 끈다. 가능하면 H.264로 저장한다.
2. 휴대폰을 삼각대나 받침에 고정하고 렌즈를 화면 중앙 높이에 맞춘다. 25~45cm에서 시작해 영상이 화면 가로의 70~90%를 채우게 한다. 직사광과 반사를 피한다.
3. 노트북 밝기를 조건대로 맞추고(자동 밝기 끔), 클립을 전체 화면·1배속으로 재생한다. 마우스 커서와 알림은 치운다. 약 20° 조건은 화면 정면에서 옆으로 비껴 찍고, 방향(좌/우)을 기억한다.
4. 녹화 시작 → 2초 뒤 재생 → 클립(10초)이 끝나고 2초 뒤 녹화 종료. 테이크 하나는 약 14초다.
5. 처음 3개는 시험 촬영으로 확인한다. 화면을 가리는 검은 띠, 반사, 초점 이탈이 있으면 설정을 고쳐 다시 찍는다. 약한 모아레나 줄무늬는 재촬영의 실제 특징이니 그대로 둔다.
6. 전송: USB 케이블로 연결 → 휴대폰 잠금 해제 → "파일 전송" 선택 → `DCIM\Camera`에서 복사한다. 카카오톡으로 보내지 않는다(압축됨). 휴대폰 원본은 지우지 않는다.
7. 복사한 파일의 이름을 위 표의 "저장 파일 이름"으로 바꿔 `C:\Dacon\Dacon_AFDA_Challenge_git\data\captures\s23\`에 넣는다. 다시 찍은 것은 `take02`로 한다.
8. (선택) 촬영표에 휴대폰 원래 파일명(`phone_original_filename`), 실제 ISO·WB·거리, 각도 방향(`notes`)을 적는다. Excel로 저장할 때는 반드시 "CSV UTF-8(쉼표로 분리)"을 고른다.

넣고 나면 Pro 에이전트가 해시·디코드·원본 매칭을 검사하고 Ultra에 알린다. 파일은 교환 서비스가 Ultra로도 복사한다(파일당 512MiB 이하).

## 2. S2 불확실 사례 22건 검수 (Stage 2)

라벨 정의 원문: [DATA_PREPARATION_SPEC.md](DATA_PREPARATION_SPEC.md) 5장.

| 무엇 | 정확한 위치 |
|---|---|
| **검수 작업표(여기에 입력)** | `C:\Dacon\Dacon_AFDA_Challenge_git\work\s2_human_review\s2_review_sheet.csv` |
| 영상별 프레임 번호 시트 | `C:\Dacon\Dacon_AFDA_Challenge_git\work\s2_human_review\sheets\<video_id>_event.jpg` |
| 원본 영상(읽기 전용) | `C:\Dacon\Dacon_AFDA_Challenge_git\data\external\nexar_subset_v1\train\positive\<video_id>.mp4` |
| 최종 반영 대상(**직접 편집하지 않음**) | `C:\Dacon\Dacon_AFDA_Challenge_git\data\derived\nexar_subset_v1\stage2_review_with_metadata.csv` |

작업표에는 22건의 영상 경로, Nexar 사건 프레임, 에이전트 제안(`agent_*` 열과 메모)이 들어 있다. 사람 칸(`actual_contact`부터 `human_notes`까지)은 비어 있다.
대상 22건: 00082 00282 00291 00295 00527 00566 00600 00660 00692 00723 00849 00860 00867 00887 00947 00989 00996 01028 01037(접촉 미확인), 00861 00902(near-miss로 판정됨), 00064(주 접촉 불명확).

### 차량 이름 (DACON 공식 정의)

[Stage별 공지](https://dacon.io/competitions/official/236753/talkboard/417186)의 이름은 흔히 쓰는 "가해·피해"와 반대로 느껴질 수 있다. 공지 그대로 따른다.

- **피의차량**: 블랙박스가 설치된 차량, 즉 촬영차량이다.
- **피해차량**: 피의차량(촬영차량)의 차선에 진입해 피의차량과 충돌한 차량, 즉 화면 안에서 끼어드는 차량이다.

### 칸마다 쓰는 값

| 칸 | 값 |
|---|---|
| `actual_contact` | `yes`(실제로 닿음) / `no`(안 닿음, near-miss 포함) / `uncertain`(판단 불가). **이 칸이 비어 있으면 그 행은 반영되지 않는다** |
| `collision_frame` | 피의차량(촬영차량)과 피해차량이 실제로 충돌한 프레임 번호. `actual_contact=yes`일 때만 쓴다 |
| `entry_frame` | 피해차량이 촬영차량의 차선에 **처음 진입한** 프레임(바퀴가 차선에 처음 닿는 순간). 화면에 처음 보이는 순간이 아니다. 충돌보다 앞이어야 한다 |
| `entry_side` | **블랙박스 화면 기준**으로 피해차량이 들어온 쪽. 화면 왼쪽에서 들어오면 `LEFT`, 오른쪽에서 들어오면 `RIGHT`. 상대 차량 입장에서 뒤집어 보지 않는다 |
| `evasion_space` | 충돌 순간 **촬영차량(피의차량)이** 계속 진행하거나 피할 수 있는 공간이 있었으면 `1`, 없었으면 `0` |
| `lane_entry_suitable` | 다른 차량이 촬영차량 차선으로 끼어들어 충돌한 사례면 `yes`. 같은 차선 추돌처럼 진입이 없는 사례면 `no`, 애매하면 `uncertain` |
| `human_notes` | 판단 근거(자유롭게) |

확신이 없는 칸은 **비워 둔다.** 0이나 -1을 넣지 않는다.
프레임 번호는 0부터 센다. 이 영상들은 30fps라 **프레임 = 재생 시각(초) × 30**이다. 시트 이미지의 각 칸 왼쪽 위에 `#번호 시각`이 적혀 있다.

### 순서

1. 작업표를 Excel이나 메모장으로 연다. Excel이 video_id 앞의 0을 지워도 괜찮다(반영할 때 복구된다).
2. 영상을 플레이어로 보고, 시트 이미지에서 프레임 번호를 고른다. 더 촘촘히 보려면 PowerShell에서 실행한다(예: 00082의 540~600을 한 프레임씩).
   ```powershell
   cd C:\Dacon\Dacon_AFDA_Challenge_git
   .\.venv-pro360\Scripts\python.exe scripts\frame_sheet.py --video data/external/nexar_subset_v1/train/positive/00082.mp4 --start 540 --end 600 --step 2 --out work/s2_human_review/sheets/00082_540_600.jpg
   ```
3. 사람 칸을 채우고 저장한다(형식은 CSV 그대로). 22건을 한 번에 다 하지 않아도 된다.
4. 반영한다. 먼저 `--dry-run`으로 바뀔 내용을 확인한 뒤 실제로 반영한다.
   ```powershell
   cd C:\Dacon\Dacon_AFDA_Challenge_git
   .\.venv-pro360\Scripts\python.exe scripts\s2_human_review.py apply --dry-run
   .\.venv-pro360\Scripts\python.exe scripts\s2_human_review.py apply
   ```
   값이 잘못되면 아무것도 쓰지 않고 고칠 행을 알려 준다. 반영하면 원본 CSV에 `review_status=reviewed`로 기록되고, 백업은 `work\s2_human_review\backup\`에 남는다. 원본 CSV를 Excel로 열어 둔 상태면 실패하니 닫고 다시 실행한다.
5. 나중에 더 채웠다면 4번을 다시 실행한다. 이미 반영한 행도 같은 값으로 다시 쓰일 뿐이라 안전하다.

반영하면 사람 라벨이 에이전트 라벨보다 항상 우선한다. Pro 에이전트는 두 라벨의 차이를 Ultra에 보고한다.
