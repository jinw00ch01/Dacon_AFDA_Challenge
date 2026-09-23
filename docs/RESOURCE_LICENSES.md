# 외부 데이터·사전학습 모델 이용조건

확인일: 2026-09-23. 확인 근거와 사용 결정을 기록하며 포괄적 권리 보증으로 해석하지 않는다.
[대회 규칙](https://www.dacon.io/competitions/official/236753/overview/rules)은 누구나 접근 가능한 공개 자원,
최소 비영리 사용 허용, 각 조건 준수와 출처 명시를 요구한다.
코드 라이선스와 영상·가중치 조건은 구분한다. 평가 데이터의 학습/튜닝/의사라벨링과 파일 간 정보 공유는 금지다.

| 자원 | 근거·조건 | 결정 |
|---|---|---|
| comma2k19 | [작성자 GitHub](https://github.com/commaai/comma2k19), [공식 데이터 카드](https://huggingface.co/datasets/commaai/comma2k19/blob/main/README.md)의 MIT 표기. 저작권·허가문 유지 | 1분 영상·센서 파일럿 확보·정렬에 사용. 대규모 학습 미실시 |
| DoTA | [저장소](https://github.com/MoonBlvd/Detection-of-Traffic-Anomaly) MIT LICENSE, 작성자의 원 채널 공유 권한 확보 설명 | 주석 확보. 영상의 대회 사용/재배포/보고서 첨부 범위 확인 후 학습 사용 |
| CCD | [저장소](https://github.com/Cogito2012/CarCrashDataset) MIT LICENSE, YouTube 수집 영상 | 문서만 확보. 소프트웨어 MIT만으로 모든 영상 권리 확정 불가. 영상 조건 확인 전 학습 보류 |
| KITTI raw | [공식 사이트](https://www.cvlibs.net/datasets/kitti/) CC BY-NC-SA3.0. 저작자 표시·비상업·동일조건 | 로그인 필요, 후순위. 파생물/대회 보고서 조건 확인 필요. yaw를 조향각 정답으로 단정하지 않음 |
| 직접 촬영/합성 | 권리가 있거나 파생 허용된 원본만 사용, 원본 조건 승계 | 계획만 수립, 아직 생성 안 함 |

## 사전학습 후보

Torchvision0.23.0의 고정 enum을 기록하며 변동 가능한 DEFAULT를 사용하지 않는다.
[공식 안내](https://docs.pytorch.org/vision/stable/models.html)는 가중치에 학습 데이터 유래 별도 조건이 있을 수 있다고 명시한다.
[코드 BSD-3-Clause](https://github.com/pytorch/vision/blob/v0.23.0/LICENSE)를 모든 가중치 허가로 확대하지 않는다.

| 후보 | 출처·학습 데이터 | 우선순위·남은 확인 |
|---|---|---|
| ResNet18 IMAGENET1K_V1 | [문서](https://docs.pytorch.org/vision/0.23/models/generated/torchvision.models.resnet18.html), [공식 weight](https://download.pytorch.org/models/resnet18-f37072fd.pth), ImageNet-1K | S2 작은 특징 추출 첫 후보. ImageNet 유래 가중치 조건 확인 필요. 이번 다운로드/학습 안 함 |
| MobileNetV3 Small IMAGENET1K_V1 | [문서](https://docs.pytorch.org/vision/0.23/models/generated/torchvision.models.mobilenet_v3_small.html), ImageNet-1K | 8GB/CPU용 가벼운 비교 후보. 가중치 조건 확인 필요 |
| MViTv2-S KINETICS400_V1 | [문서](https://docs.pytorch.org/vision/0.23/models/generated/torchvision.models.video.mvit_v2_s.html), Kinetics-400 | 시계열 후보지만 메모리 비용 큼. 원 학습 자원 조건 확인 후 사용. 랜덤 초기화 smoke는 사전학습 확보가 아님 |
| weights=None 구조 | Torchvision BSD-3-Clause + 허용된 자체 학습셋 | 외부 가중치 없는 대안, 소량 데이터 성능 한계 있음 |

선정 후 enum/다운로드 URL/날짜/전체 SHA-256/학습 데이터/조건 근거/사용 Stage를 MODEL_REGISTRY에 기록한다.
고정 구조와 `torch.load(..., weights_only=True)`를 사용하고 추론 중 다운로드를 하지 않는다.

## 출처 보존

파일별 revision·해시는 `data/external/pilot_manifest.json`에, LICENSE/README 원문은 외부 데이터 폴더에 보관했다.
공개 Git에는 외부 원본 대신 출처와 수집 코드를 제공한다.
comma2k19: Schafer et al., *A Commute in Data: The comma2k19 Dataset*, 2018, arXiv:1812.05752.
DoTA: Yao et al., *DoTA: Unsupervised Detection of Traffic Anomaly in Driving Videos*, IEEE TPAMI, 2022.
CCD 최종 사용 시 작성자 저장소의 논문 인용 표기를 보고서에 포함한다.
