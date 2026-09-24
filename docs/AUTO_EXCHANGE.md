# Pro 360 ↔ Ultra 자동 교환

코드는 GitHub, 선택한 영상·검수 결과는 두 장치가 서로 등록한 Syncthing 연결로 교환한다.
두 PC의 Codex 대화 자체를 연결하는 기능은 아니다. 이 프로젝트의 파일과 허용된 CPU 작업을 연결한다.
최초 설치와 양방향 장치 등록 후에는 ZIP을 수동 전달하지 않아도 된다.

2026-09-24 실제 Pro 수신과 CPU 결과 왕복을 확인했다. 아래 최초 설치 절차는 새 설치용이다.
PC별 Codex 역할은 [운영 결정](AGENT_OPERATING_DECISION.md), 향후 실험 제어 파일은 [실험 규약](EXPERIMENT_PROTOCOL.md)을 따른다.
새 규약의 패킷·학습·LLM wake는 현 worker에 구현되지 않았다. 전송 성공을 상대 Codex 실행으로 해석하지 않는다.

## 전송 구조

| 경로 | 작성 장치 | 수신 장치에서 하는 일 |
|---|---|---|
| `C:\Dacon\AFDA_Exchange\ultra_to_pro` | Ultra | 해시 검증, 기존 파일과 충돌 검사 후 프로젝트로 복사 |
| `C:\Dacon\AFDA_Exchange\pro_to_ultra` | Pro | 작업 결과·상태 수신, 검수본을 별도 버전 폴더에 보관 |

작성 쪽은 send-only, 수신 쪽은 receive-only이다. 작업은 공유 폴더가 아닌 각 프로젝트 폴더에서 한다.
원본 프로젝트 데이터와 전송용 스냅샷은 별도이므로 각각 디스크를 차지한다.
양쪽 PC가 켜져 있고 로그인된 상태에서 동작한다. 꺼짐/절전/인터넷 단절 중에는 대기하며 연결 뒤 이어진다.
대용량 최초 전송은 같은 Wi-Fi에서 권장한다. 휴대폰 핫스팟 사용 시 통신 데이터가 소비될 수 있다.

## Pro 최초 설치

기존 폴더를 보존하고 다음 새 형제 폴더를 사용한다. Git과 Python3.12 x64가 필요하다.
기존 Pro venv가 있으면 기반 Python을 자동으로 찾아 **새 CPU venv**를 만든다. 설치 시간이 걸릴 수 있다.
`<Ultra 장치 ID>`는 Ultra 설치 결과의 실제 ID로 바꾼다. 비밀번호나 HF 토큰은 필요 없다.

```powershell
git clone https://github.com/jinw00ch01/Dacon_AFDA_Challenge.git C:\Dacon\Dacon_AFDA_Challenge_git
Set-Location C:\Dacon\Dacon_AFDA_Challenge_git
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_exchange.ps1 -Role pro360 -PeerId '<Ultra 장치 ID>'
```

이미 새 clone이 있다면 origin과 `git status --porcelain`을 확인하고 깨끗한 main에서 `git pull --ff-only` 한다.
기존 변경이 있으면 그대로 보존하고 먼저 검토한다. 설치 후 출력된 Pro `device_id`를 Ultra에 한 번 등록한다.

```powershell
Set-Location C:\Dacon\Dacon_AFDA_Challenge
.\.venv-ultra5060\Scripts\python.exe -m exchange_bridge.transport pair --config configs/local-exchange.json --peer-id '<Pro 장치 ID>'
```

장치 ID는 공개키 식별자이며 비밀번호는 아니다. 프로젝트 공개 저장소에는 올리지 않는다.
각 PC 관리 화면은 [로컬 Syncthing](http://127.0.0.1:8385)이다. 등록되지 않은 장치를 자동 승인하지 않는다.
관리 API는 루프백으로만 접근하고 인증키/인증서는 사용자 LocalAppData에 둔다.
방화벽/공유기 설정을 자동 변경하지 않는다. 연결이 안 되면 앱 연결 상태와 네트워크부터 점검한다.

## 자동화되는 일

- 15초 간격: 수신 작업 확인, SHA-256 검증, 작업 결과와 상태 기록.
- 5분 간격: 지정 origin/main이며 수정 파일이 없을 때만 Git fast-forward. 강제 초기화나 자동 push는 하지 않는다.
- Pro 검수 CSV 수정 후 30초 이상 안정되면 자동 반환: `data/derived/nexar_subset_v1/stage2_review_with_metadata.csv`, `data/derived/comma_subset_v1/s23_capture_ready.csv`.
- Pro의 `data/captures/s23/` 아래 MP4/MOV도 안정된 파일을 자동 반환한다. 스마트폰에서 Pro로 옮기는 과정은 별도다.
- Ultra는 반환본을 `data/derived/peer_reviews/pro360/<job-id>/` 아래 보관한다. `latest.json`은 가장 최근 반환 묶음을 가리킨다. 여러 묶음의 라벨 통합은 별도 검토 단계다.

허용 작업: `ping`, `verify_bundle`, `import_bundle`, `prepare_review`, `run_contract_tests`, `return_reviews`.
`prepare_review`는 자료 가져오기와 첫 프레임 미리보기 생성이다. 사람의 사고 판정이나 라벨 정답 생성을 대신하지 않는다.
CPU 실행은 역할별 harness RAM 한도와 600초 제한을 사용한다. 임의 명령, 노트북 실행, GPU 학습은 큐로 실행할 수 없다.
실행 작업은 보내는 쪽과 받는 쪽의 Git commit이 같고 수신 코드가 깨끗할 때만 시작한다.
코드가 앞으로 갱신돼 이전 commit 작업이 대기하면 내용을 검토한 뒤 새 ID로 다시 보낸다. 과거 commit으로 자동 되돌리지 않는다.

## Ultra에서 보내기

설정 파일은 설치 시 자동 생성되며 Git에서 제외된다. 선택한 파일만 새 스냅샷으로 전송한다.
최초 데이터 등록은 한 번 필요하며 이후 Pro 검수본의 반환은 자동이다.

```powershell
$pythonPath = '.\.venv-ultra5060\Scripts\python.exe'
& $pythonPath -m exchange_bridge publish --config configs/local-exchange.json --operation ping
& $pythonPath -m exchange_bridge publish --config configs/local-exchange.json --operation prepare_review --path data/external/nexar_subset_v1 --path data/derived/nexar_subset_v1 --path data/external/comma2k19_subset_v1 --path data/derived/comma_subset_v1
& $pythonPath -m exchange_bridge publish --config configs/local-exchange.json --operation run_contract_tests
```

전송본에는 원본 라이선스/출처 파일도 포함한다. Nexar 파일의 사용 조건은 RESOURCE_LICENSES.md를 따른다.
영상·라벨·인증정보·장치 설정을 공개 Git에 넣지 않는다. HF 인증 캐시를 복사하지 않는다.
bundle 제한은 파일당512MiB, 전체8GiB/5,000파일이다. 대형 S23 영상은 계획한 짧은 클립으로 촬영한다.
가져오기 후 여유공간이 Pro20GiB/Ultra40GiB 아래로 내려가면 실패하고 원본을 보존한다.
전송 스냅샷과 수신 버전은 자동 삭제하지 않으므로 장기간 사용 시 용량을 확인한다.

## 상태 확인·중지

```powershell
.\.venv-pro360\Scripts\python.exe -m exchange_bridge.transport status --config configs/local-exchange.json
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop_exchange.ps1 -DisableAutoStart
```

상태 출력의 `peer_connected`와 양쪽 전송 폴더의 `status/`, `results/<job-id>/result.json`을 확인한다.
큐 파일이 먼저 도착하면 `waiting_for_files`, 코드 조건이 안 맞으면 `waiting_for_clean_matching_code`다.
기존 로컬 라벨과 내용이 다르면 실패하며 덮어쓰지 않는다. 중간 종료된 작업도 자동 중복 실행하지 않는다.
실패 원인을 해결한 뒤 새 작업을 발행한다. 서비스 로그/큐 실행 상태는 `%LOCALAPPDATA%\AFDA\<role>\`에 있다.
중지는 현재 CPU 작업이 끝난 뒤 적용된다. 다시 시작하려면 같은 setup 명령을 실행한다.
설치기는 현재 사용자 로그인 시작 항목 `AFDAExchange-<role>`을 등록한다. 관리자 권한과 재부팅은 필요 없다.

## 기술 출처와 검증 범위

Syncthing v2.1.5 Windows amd64 공식 ZIP의 게시된 SHA-256을 설치 시 확인한다.
[공식 릴리스](https://github.com/syncthing/syncthing/releases/tag/v2.1.5),
[폴더 동작](https://docs.syncthing.net/users/foldertypes.html),
[REST 설정](https://docs.syncthing.net/rest/config.html),
[시작 설정](https://docs.syncthing.net/users/autostart.html)을 따른다.
회귀 검사는 경로 탈출, 허용 작업, 해시 변조, 부분 수신, 중복/중단 실행, 파일 보존, 검수 자동 반환을 검증한다.
한 PC에서 두 장치를 모사한 검사는 실제 Pro의 설치·네트워크 연결·CPU 실행 검증과 구분한다.
