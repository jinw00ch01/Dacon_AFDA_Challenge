# 외부 데이터·사전학습 모델 이용조건

확인일: 2026-09-24. 확인 근거와 사용 결정을 기록하며 포괄적 권리 보증으로 해석하지 않는다.
[대회 규칙](https://www.dacon.io/competitions/official/236753/overview/rules)은 누구나 접근 가능한 공개 자원,
최소 비영리 사용 허용, 각 조건 준수와 출처 명시를 요구한다.
코드 라이선스와 영상·가중치 조건은 구분한다. 평가 데이터의 학습/튜닝/의사라벨링과 파일 간 정보 공유는 금지다.

| 자원 | 근거·조건 | 결정 |
|---|---|---|
| comma2k19 | [작성자 GitHub](https://github.com/commaai/comma2k19), [공식 데이터 카드](https://huggingface.co/datasets/commaai/comma2k19/blob/main/README.md)의 MIT 표기. 저작권·허가문 유지 | 서로 다른 날짜24개 영상·센서를 S1/S3로 선정. 실제 결과는 DATA_ACQUISITION_RESULT.json. 학습 미실시 |
| Nexar Collision Prediction | [공식 데이터](https://huggingface.co/datasets/nexar-ai/nexar_collision_prediction), [Nexar Open Data License](https://huggingface.co/datasets/nexar-ai/nexar_collision_prediction/blob/main/LICENSE). 출처·저작권/조건 보존, 영리 재판매·재식별·유해/부당한 보험 활용 등 금지 | 사용자 계정 접근 신청·OAuth 연결 완료. train 양성80/정상24를 S2 후보로 선정. S1 변형/재촬영에는 배정하지 않음. 양성은 collision+near-miss 혼합 |
| DoTA | [저장소](https://github.com/MoonBlvd/Detection-of-Traffic-Anomaly) MIT LICENSE, 작성자의 원 채널 공유 권한 확보 설명 | 주석 확보. 영상의 대회 사용/재배포/보고서 첨부 범위 확인 후 학습 사용 |
| CCD | [저장소](https://github.com/Cogito2012/CarCrashDataset) MIT LICENSE, YouTube 수집 영상 | 문서만 확보. 소프트웨어 MIT만으로 모든 영상 권리 확정 불가. 영상 조건 확인 전 학습 보류 |
| KITTI raw | [공식 사이트](https://www.cvlibs.net/datasets/kitti/) CC BY-NC-SA3.0. 저작자 표시·비상업·동일조건 | 로그인 필요, 후순위. 파생물/대회 보고서 조건 확인 필요. yaw를 조향각 정답으로 단정하지 않음 |
| 직접 촬영/합성 | 권리가 있거나 파생 허용된 원본만 사용, 원본 조건 승계 | 계획만 수립, 아직 생성 안 함 |

## 사전학습 후보

**우선 확보 후보: DINOv2 ViT-S/14 (일반 이미지 backbone).**
[Meta 공식 저장소](https://github.com/facebookresearch/dinov2#license)와
[MODEL_CARD](https://github.com/facebookresearch/dinov2/blob/main/MODEL_CARD.md)가 코드와 가중치의 Apache2.0을 명시한다.
공식 ViT-S/14 가중치88,283,115바이트를 다운로드하고 `weights_only=True` 역직렬화를 확인했다.
README/LICENSE/MODEL_CARD와 전체 SHA-256을 보관했으며 `docs/MODEL_REGISTRY.json`에 공개 출처 장부를 저장했다.
Apache2.0의 라이선스·저작권 고지 유지, 변경 사항 표시 및 해당되는 NOTICE 보존 조건을 따른다.
XRay-DINO/Cell-DINO 등 별도 조건의 다른 모델로 이 허가를 확대하지 않는다.
학습 데이터는 LVD-142M이며 모델 가중치 사용 허가가 원 학습 영상/이미지의 재배포 권한을 뜻하지 않는다.
S1/S2/S3 프레임 특징을 고정 추출하고 작은 시계열 head를 학습하는 비교 후보로 선정했다.
아직 모델 구조의 로컬 패키징·영상 forward·대회용 미세조정은 하지 않았다. 서명된 배포자 weight 해시 검증이 아니라 HTTPS 수집+관측 SHA 기록이다.

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

파일별 revision·해시는 `data/external/pilot_manifest.json`과 각 추가 데이터의 manifest.json에, LICENSE/README 원문은 외부 데이터 폴더에 보관한다.
공개 Git에는 외부 원본 대신 출처와 수집 코드를 제공한다.
comma2k19: Schafer et al., *A Commute in Data: The comma2k19 Dataset*, 2018, arXiv:1812.05752.
DoTA: Yao et al., *DoTA: Unsupervised Detection of Traffic Anomaly in Driving Videos*, IEEE TPAMI, 2022.
CCD 최종 사용 시 작성자 저장소의 논문 인용 표기를 보고서에 포함한다.

Nexar 라이선스 지정 인용: Moura, Daniel C., and Zvitia, Orly. "Nexar Collison Dataset." Hugging Face, 2025.
https://huggingface.co/datasets/nexar-ai/nexar_collision_prediction
관련 논문: Moura, Zhu, Zvitia, *Nexar Dashcam Collision Prediction Dataset and Challenge*, CVPR Workshops2025, https://arxiv.org/abs/2503.03848.
