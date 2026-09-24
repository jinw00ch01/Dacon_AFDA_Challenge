# 공개 저장소와 두 노트북 협업

저장소: https://github.com/jinw00ch01/Dacon_AFDA_Challenge
AFDA = Accident Fraud Detection AI. 사용자가 공개 저장소로 지정했다.

코드·검증기·설정·출처 문서만 Git으로 공유한다. `.gitignore`가 영상·모델·실행 기록·개인 장치 정보·공식 배포 원본을 제외한다.
데이터는 [자동 교환](AUTO_EXCHANGE.md)의 Syncthing 경로를 우선하고 ZIP은 오프라인 대안으로 사용한다. venv를 복사하거나 GPU lock을 CPU PC에 설치하지 않는다.

자동 수신기는 main, 지정된 origin, 작업 트리가 깨끗한 경우에만 5분 간격으로 fetch 및 fast-forward를 수행한다.
코드 수정 중이면 건너뛴다. commit/push는 자동 수행하지 않으며 아래 개발 브랜치 절차를 따른다.

## Pro 360 최초 연결

기존 반환 폴더를 덮어쓰지 않고 새 형제 폴더에 clone한다.

```powershell
git clone https://github.com/jinw00ch01/Dacon_AFDA_Challenge.git Dacon_AFDA_Challenge_git
cd Dacon_AFDA_Challenge_git
git status
```

기존 Baseline과 원본 참조 문서는 로컬 자료로 복사할 수 있다. 새 위치에는 새 venv를 생성한다.
기존 venv가 잘 동작하는 기존 폴더는 그대로 보관해도 된다.
개인 이메일 공개를 원하지 않으면 각 PC의 이 저장소에 GitHub noreply 이메일을 `git config --local user.email`로 설정한다.
push 인증은 Git Credential Manager의 정상 브라우저 로그인으로 수행하고 토큰을 파일에 쓰지 않는다.

## 일상 작업

```powershell
git switch main
git pull --ff-only
git switch -c pro/data-review-001
# 담당 파일 수정 및 검사
git add docs/DATA_ACQUISITION.md
git diff --cached
git commit -m "Refine dataset review plan"
git push -u origin pro/data-review-001
```

Ultra의 모델 코드는 `ultra/...`, Pro의 조사·라벨 검수는 `pro/...` 브랜치로 나눈다.
main에 합친 후 반대 PC에서 pull한다. 같은 파일 동시 편집·강제 push를 피하고 충돌은 내용을 비교해 해결한다.
변경 전 `git status`, 업로드 전 `git diff --cached`로 파일과 민감정보를 확인한다.
외부 데이터가 필요하면 파일 본문 대신 다운로드 스크립트·해시·버전·출처를 공유한다.
