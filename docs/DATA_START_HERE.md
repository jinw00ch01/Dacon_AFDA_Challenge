# 확보한 실제 영상: 여기서 시작

2026-09-24에 새 원본128개를 실제 다운로드했다. 기존 Baseline20개와 최초 comma1분 파일럿은 별도다.
원본·센서·메타데이터 합계 약2.70GB이며, 공개 Git에는 영상이 포함되지 않는다.

| 준비된 자료 | 현재 수량 | 사용할 일 |
|---|---:|---|
| comma 일반 주행 원본 | 서로 다른 날짜24개, 약24분 | S1 원천 및 S3 보조 학습 |
| S23 촬영용 MP4 | 24개, 각 약10초,20fps | 노트북에서 재생하고 각2회 촬영 |
| Nexar 실제 블랙박스 영상 | 사고/near-miss 후보80개 + 정상24개, 약68분 | 실제 접촉·차선 진입 사례 선별 후 라벨링 |
| S3 연속 보조 타깃 | 23개 주행,13,776행 | 센서·영상 정렬 검수 후 클래스 매핑 |

Nexar104개는 공식 SHA-256 대조와 전체122,175프레임 디코딩을 통과했다.
comma 원본24개도 전체 디코딩을 확인했다. SRC014는 시간 정렬 오차 때문에 S3에서 제외했다.
S1 휴대폰 재촬영, S2 정답 작성, 모델 학습은 아직 하지 않았다.

## 1. S23 재촬영부터 시작하려면

일반 PowerShell에서 촬영용 영상 폴더를 연다.

```powershell
explorer.exe 'C:\Dacon\Dacon_AFDA_Challenge\data\derived\comma_subset_v1\s1_playback'
```

`SRC001_ORIGINAL.mp4`부터24개가 있다. 실제 원본 경로가 채워진 표는 다음 위치다.

`C:\Dacon\Dacon_AFDA_Challenge\data\derived\comma_subset_v1\s23_capture_ready.csv`

[S23 촬영 계획](LABELING_AND_S23_PLAN.md)을 따라 표의 C1~C4 조건으로48회 촬영한다.
표의 source_path는 프로젝트 루트 기준이며 SHA 칸은 앞으로 촬영할 휴대폰 파일용이다.
원본 재생본의 SHA는 같은 폴더의 report.json에 이미 기록되어 있다.

## 2. 실제 사고 후보를 보려면

```powershell
explorer.exe 'C:\Dacon\Dacon_AFDA_Challenge\data\external\nexar_subset_v1\train'
```

- `positive`에 사고/near-miss 후보80개가 있다. 모두 실제 접촉 사고라고 가정하지 않는다.
- `negative`에 정상 주행24개가 있다.
- 검수표: `C:\Dacon\Dacon_AFDA_Challenge\data\derived\nexar_subset_v1\stage2_review_with_metadata.csv`
- 사건 참고 시각, 밝기, 날씨, 장면, FPS, 프레임 수를 채웠다. DACON 정답 칸은 비어 있다.
- Excel로 편집한다면 video_id 열을 텍스트로 가져와 앞자리0을 유지하고 UTF-8 CSV로 저장한다.

먼저30~45분 동안 실제 접촉/near-miss/판단불가와 차선 진입 적합성을 선별한다.
이후 적합한30~50개를 기존250분 라벨링 예산으로 검수한다. 보고된 사건 시각을 충돌/진입 정답으로 복사하지 않는다.

## 3. S3 검수 파일

`C:\Dacon\Dacon_AFDA_Challenge\data\derived\comma_subset_v1\s3_auxiliary_10hz.csv`

원본 센서는 `data/external/comma2k19_subset_v1/segments/`에 있다.
동일 시각 중복 측정은 평균으로 합친 이력을 기록했고 원본은 보존했다.
속도/조향 연속값과 속도 미분 가속도 proxy이며 공식 분류 정답은 아니다. 최종 추론 입력은 영상만 사용한다.

## train/test 다운로드 위치에 대한 답

Nexar 웹사이트의 **Files and versions** 탭에 [train](https://huggingface.co/datasets/nexar-ai/nexar_collision_prediction/tree/main/train),
[test-public](https://huggingface.co/datasets/nexar-ai/nexar_collision_prediction/tree/main/test-public),
[test-private](https://huggingface.co/datasets/nexar-ai/nexar_collision_prediction/tree/main/test-private)가 있다.
이 test는 Nexar 대회의 자료다. DACON 비공개 평가 데이터가 아니며 이번에는 받지 않았다.
사용자가 웹 접근 신청과 PC 인증을 완료하여, train에서 필요한104개는 이미 다운로드했다. 다시 수동으로 받을 필요가 없다.

## 조건과 두 노트북 간 전달

comma는 공식 MIT 표기와 원문을 보관했다. Nexar는 별도 Nexar Open Data License를 보존했으며 사고 분석용으로 사용하고 S1 재촬영 원천으로는 쓰지 않는다.
Pro에는 위 경로들을 USB 등으로 프로젝트 루트 아래 같은 위치에 복사하고 LICENSE/README/manifest도 같이 보관한다. Git clone만으로 영상이 내려오지는 않는다.
자세한 출처·계정 설정·재현 명령은 [데이터 확보 실행안](DATA_SOURCING_EXECUTION.md), 수치 근거는 [확보 결과](DATA_ACQUISITION_RESULT.json)를 따른다.
