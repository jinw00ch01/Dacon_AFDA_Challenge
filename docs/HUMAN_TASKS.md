# 사람이 하는 작업: S23 실촬영과 S2 검수

작성: 2026-09-26. 두 작업 모두 **Pro 노트북**에서 한다. 프로젝트 폴더는 `C:\Dacon\Dacon_AFDA_Challenge_git`이다.
결과를 아래의 정해진 위치에 두면 끝이다. Pro 에이전트가 1~2분 안에 감지해 QA하고, 교환 서비스가 Ultra로 자동 전달한다.
[PRO360_STEPS.md](PRO360_STEPS.md) 6장의 ZIP·USB 전달은 예전 방식이라 쓰지 않는다.
[DATA_START_HERE.md](DATA_START_HERE.md)에 적힌 `C:\Dacon\Dacon_AFDA_Challenge\...` 경로는 Ultra 기준이다.

추천 순서: S23 실촬영을 먼저 한다(다른 방법으로는 얻을 수 없는 실제 재촬영 데이터). S2 검수는 그다음에 한다.

## 1. S23 Ultra 실촬영 (Stage 1)

DACON [Stage별 공지](https://dacon.io/competitions/official/236753/talkboard/417186)의 재녹화 정의는 "원본 영상을 별도의 화면에서 재생한 후 다른 기기로 다시 촬영한 영상"이다. 공지가 드는 특징은 화면 테두리·재생 화면 일부 노출, 화면 주사 패턴, 반사광과 주변 환경, 밝기·색상·명암 변화, 추가 압축, 촬영 기기의 움직임·원근 변화, 해상도·화면 비율 변화다. 공개 예시 클립은 공지에서 밝힌 대로 시뮬레이션이다. 그래서 S23 실촬영이 실제 평가 데이터에 가장 가까운 자료다. **모든 테이크를 손으로 들고 찍고, 반사가 생겨도 된다**(기기 움직임과 반사는 공식 특징이다). 영상 내용이 보이기만 하면 된다.

참고: [LABELING_AND_S23_PLAN.md](LABELING_AND_S23_PLAN.md)는 삼각대 고정·반사 회피·프로 동영상 설정을 전제로 쓴 예전 계획이다. 촬영 방식은 아래 순서를 따른다.

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

1. S23 기본 카메라 앱의 **동영상** 모드를 쓴다. 후면 1×(줌 없음), 가로, FHD 1920×1080 30fps로 두고 나머지는 기본(자동) 설정 그대로 둔다. 프로 동영상 설정은 필요 없다. 촬영 전에 노트북 화면을 한 번 눌러 초점을 맞춘다.
2. 휴대폰은 **손으로 들고** 찍는다. 두 손으로 잡고 팔꿈치를 책상이나 몸에 붙이면 크게 흔들리지 않는다. 자연스러운 흔들림, 실내 조명 반사, 화면 테두리나 주변이 조금 보이는 것은 모두 괜찮다.
   - 정면 조건(C1·C3): 화면 정면에서 영상이 휴대폰 화면 가로의 대부분을 채우게 잡는다.
   - 약 20° 조건(C2·C4): 화면 정면에서 옆으로 비껴 서서 찍는다. 방향(좌/우)을 기억한다.
3. 노트북 밝기를 조건대로 맞추고(70% 또는 40%, 자동 밝기 끔) 1배속으로 재생한다. 전체 화면이 좋지만 재생 창 일부가 보여도 된다.
4. 녹화 시작 → 2초 뒤 재생 → 클립(10초)이 끝나고 2초 뒤 녹화 종료. 테이크 하나는 약 14초다.
5. 찍은 뒤 휴대폰에서 바로 확인한다. **반사나 흔들림 때문에 차량·도로를 거의 알아볼 수 없는 테이크만** 다시 찍는다(`take02`). 약한 모아레·줄무늬·깜빡임은 재촬영의 실제 특징이니 그대로 둔다.
6. 전송: USB 케이블로 연결 → 휴대폰 잠금 해제 → "파일 전송" 선택 → `DCIM\Camera`에서 복사한다. 카카오톡으로 보내지 않는다(압축됨). 휴대폰 원본은 지우지 않는다.
7. 복사한 파일의 이름을 위 표의 "저장 파일 이름"으로 바꿔 `C:\Dacon\Dacon_AFDA_Challenge_git\data\captures\s23\`에 넣는다. 다시 찍은 것은 `take02`로 한다.
8. (선택) 촬영표에 휴대폰 원래 파일명(`phone_original_filename`)과 메모(`notes`: 각도 방향, 반사 정도, 손떨림 정도)를 적는다. Excel로 저장할 때는 반드시 "CSV UTF-8(쉼표로 분리)"을 고른다.

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

**positive인데 접촉이 없는 영상(near-miss)**: Nexar의 positive는 "충돌했거나 충돌이 임박했던 사건"이라 near-miss가 섞여 있다(Nexar 데이터셋 정의이며, 우리는 train/positive에서 파일명 순으로 80개를 받았다). 이때 `actual_contact=no`로 두고, `collision_frame`과 `evasion_space`는 비운다(회피 공간은 "충돌 당시" 기준이라 정의되지 않음). 끼어들기가 분명히 보이면 `entry_frame`, `entry_side`를 적고 `lane_entry_suitable=yes`로 둔다(진입 학습 예시로 쓰인다). 끼어들기가 없거나 애매하면 비우고 `lane_entry_suitable=no`로 둔다. 작업표의 `nexar_event_frame`은 Nexar가 기록한 사건 시각이라 장면을 찾는 데 쓴다. `uncertain`(접촉이 가려 안 보임)도 같게 한다.

**같은 차로 추돌**(상대 차량이 영상 처음부터 촬영차량 차선에 있었음): 진입이 없으니 `entry_frame`, `entry_side`는 비우고 `lane_entry_suitable=no`로 둔다. `actual_contact`, `collision_frame`은 그대로 적고, `evasion_space`는 판단되면 적는다.
**예외: 끼어든 뒤 급정거해서 들이받은 경우**는 진입이 있는 사례다. 영상 안에서 끼어드는 장면이 보이면 그 순간을 `entry_frame`에, 들어온 화면 쪽을 `entry_side`에 적고 `lane_entry_suitable=yes`로 둔다.
제출 파일에서는 모든 영상에 네 항목을 채워야 하지만, 그건 모델이 맡는다. 검수에서는 정의되지 않는 값을 만들지 않는다.
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
