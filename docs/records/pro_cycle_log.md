# Pro 에이전트 사이클 기록
> Pro 360(CPU 노트북)의 로컬 기록을 GitHub용으로 옮긴 것이다. 사용자 경로·장치 이름·계정 같은 개인 정보는 `<USER_HOME>`, `<pro-host>`, `<email>` 등으로 가렸다. 대회 원본·영상·가중치·토큰은 넣지 않았다.

`agent_bridge` 원장에 남은 Pro 사이클 84개다(KST). 비용은 Claude Code가 보고한 API 환산 금액(USD)이다. 실제 과금은 구독 한도 안에서 처리됐다.

총 API 환산 비용: 약 $159

## 09-25 11:19 ~ 09-25 11:41 · `63eb5d5dc70d` · succeeded
- 깨운 이유: scheduled · 비용 $10.37 · 턴 8
- 요약: 최종 보고(라벨러 모두 종료). S2 에이전트 라벨 20개를 기록했다(human 0 / agent 20). 이 가운데 10개를 qa 'stage2 labels v1'로 보냈다. 접촉 미확인으로 사람 검수가 필요한 사례는 00082, 00282, 00291, 00295이고, 주 접촉이 불명확한 사례는 00064다. S3 규칙 v1b를 qa로 보냈다. S1 합성 job은 agent_bridge argv 버그로 lost가 됐다. 수정은 pro/fix-job-run-config(b3b53aa)에 push했고 기존 unittest 8개가 통과했다. guard 때문에 실제 job 실행으로 끝까지 확인하지는 못했다. Ultra에 병합을 요청했다. 다음 사이클에는 v2(20개) 병합본을 보낸다. 근거: data/derived/labels/agent/stage2_agent_labels.csv, docs/STATUS.md.
- 사람에게 요청: S23 실촬영: data/captures/s23/에 파일이 아직 없음(계획 48테이크) / 선택: S2 00082, 00282, 00291, 00295(접촉 여부)와 00064를 사람이 검수

## 09-25 11:42 ~ 09-25 11:49 · `9e6d669ad294` · succeeded
- 깨운 이유: job_finished · 비용 $6.66 · 턴 5
- 요약: 이번 사이클 결과:
(1) qa 'stage2 labels v2'(f158e37c…)를 보냈다. positive 20개이고 라벨 출처는 human 0 / agent 20이다.
(2) S2 positive 15개를 새로 라벨했다: 00313, 00326, 00349, 00369, 00373, 00376, 00456, 00461, 00463, 00474, 00483, 00488, 00500, 00515, 00516. 15개 모두 접촉 yes이고 confidence는 0.35~0.6이다. 이로써 positive는 35개가 됐다.
(3) negative 24개를 source_label 근거로만 actual_contact=no로 기록했다. 프레임은 보지 않았다. 현재 라벨은 human 0 / agent 59다.
(4) argv 버그 수정이 main에 병합됐다(73072fb). S1 job 13505ad3f6fd를 다시 큐에 넣었고 실행 중이다. SRC001은 부분 QA를 통과했다.
(5) work/pro_tools/s1_qa.py를 만들었다.

근거: data/derived/labels/agent/stage2_agent_labels.csv, docs/STATUS.md.
- 사람에게 요청: S23 실촬영 영상을 data/captures/s23/에 넣어 주세요(현재 0개). / S2 사람 검수 필요: 00082, 00282, 00291, 00295(접촉 미확인), 00064(주 접촉 불명확)

## 09-25 11:50 ~ 09-25 11:55 · `29d19f084441` · succeeded
- 깨운 이유: scheduled · 비용 $4.33 · 턴 10
- 요약: 이번 사이클 결과:
(1) qa 'stage2 labels v3'를 보냈다(d1d9834f7eda4a17ae7db0746470ce72). positive 35개와 negative 24개이고, 라벨 출처는 human 0 / agent 59다.
(2) positive 8개를 새로 라벨해 모두 기록했다. 현재 라벨은 human 0 / agent 67이다(positive 43 + negative 24). 병합 기준 collision_valid는 36, entry_valid는 16이다.
- 접촉 yes: 00133(collision 600, entry 572 RIGHT, 0.35), 00529(collision 601, entry 522 LEFT, 0.55), 00539(collision 598, 0.45), 00550(collision 605, 0.6), 00614(collision 650, entry 604 RIGHT, 0.4)
- 접촉 uncertain(사람 검수 필요): 00527(0.3), 00566(0.3), 00600(0.4)
(3) S1 job 13505ad3f6fd는 실행 중이다. 02:55Z에 mp4 13/120개였고 약 04:20Z에 끝날 것으로 본다.
(4) work/pro_tools/label_stats.py를 만들었고 docs/STATUS.md를 갱신했다.
근거: data/derived/labels/agent/stage2_agent_labels.csv, work/agent/stage2_merged_latest.csv, work/agent/labels_batch4[a-h].json, docs/STATUS.md.
- 사람에게 요청: S23 실촬영 파일을 data/captures/s23/에 넣기(현재 0개) / S2 사람 검수(선택): 00082, 00282, 00291, 00295, 00527, 00566, 00600은 접촉 미확인, 00064는 주 접촉 불명확, 00133은 저신뢰 yes

## 09-25 11:56 ~ 09-25 12:01 · `9e6606ba3e4e` · succeeded
- 깨운 이유: scheduled · 비용 $4.36 · 턴 16
- 요약: 이번 사이클 결과:
(1) S2 positive 8개를 모두 라벨해 기록했다(work/agent/labels_batch5a~e.json).
- 접촉 yes: 00659(collision 355, entry 346 RIGHT, confidence 0.4), 00705(collision 766, entry 753 RIGHT, 0.55), 00667(collision 540, entry 미정, 0.6), 00696(collision 618, 같은 차로 추돌, 0.55), 00704(collision 544, entry 520 LEFT, 0.5)
- 접촉 uncertain(사람 검수 필요): 00660(0.35), 00692(0.3), 00723(0.3)
(2) qa 'stage2 labels v4'(64d637fff8ca4133a04acf26bffc7709)를 보냈다. positive 51개와 negative 24개이고, 라벨 출처는 human 0 / agent 75다. collision_valid는 41, entry_valid는 19다. 병합 CSV, 원본 CSV, 불확실 사례 시트 5장을 첨부했다.
(3) 남은 positive는 29개다(00748~01037).
(4) S1 job 13505ad3f6fd는 실행 중이다. 03:1xZ 기준 mp4 25/120개로 처음 예상보다 느리다.
근거: work/agent/outbox/stage2_labels_v4.json, data/derived/labels/agent/stage2_agent_labels.csv, docs/STATUS.md.
- 사람에게 요청: S23 실촬영 파일을 data/captures/s23/에 넣어 주세요(현재 0개) / S2 접촉 미확인 사례를 사람이 검수해 주세요: 00082, 00282, 00291, 00295, 00527, 00566, 00600, 00660, 00692, 00723.

## 09-25 12:02 ~ 09-25 12:07 · `cd4658b5e90a` · succeeded
- 깨운 이유: scheduled · 비용 $3.55 · 턴 6
- 요약: Cycle cd4658b5e90a 최종 보고(앞선 보고들을 대신함): 이번 사이클에 시작한 labeler 8개가 모두 끝나, S2 positive 8개를 기록했다(`work/agent/labels_batch6a~f.json`). 8개 모두 actual_contact=yes이고 confidence는 0.4~0.6이다. 모든 사례에서 접촉 지점이 보닛에 가리거나 화면 밖이어서 접촉 프레임은 추정값이다.
- 00748: collision 616, entry 592 RIGHT, lane_entry_suitable=uncertain, confidence 0.45
- 00766: collision 593, entry 566 RIGHT, confidence 0.6
- 00769: collision 581, entry 560 RIGHT, confidence 0.5
- 00774: collision 611, 교차로 충돌, lane_entry_suitable=no, confidence 0.45. labeler가 낸 entry 값은 lane_entry_suitable=no와 모순되어 비웠다.
- 00776: collision 503, entry 476 RIGHT, confidence 0.45
- 00784: collision 551, 터널 추돌, confidence 0.4
- 00793: collision 615, 트레일러 추돌, confidence 0.45
- 00823: collision 1093, entry 1066 LEFT, confidence 0.45

라벨은 human 0 / agent 83이다(positive 59 + negative 24). v4 이후 추가분은 8개로, 발송 기준 10개에 못 미쳐 v5는 보내지 않았다. 남은 positive는 21개(00849부터)다. `docs/STATUS.md`를 갱신했다. S1 job 13505ad3f6fd는 실행 중이다(03:03Z 기준 mp4 29/120개, 약 04:05Z에 끝날 것으로 봄).

## 09-25 12:08 ~ 09-25 12:18 · `33549c9c13fd` · succeeded
- 깨운 이유: packet · 비용 $7.75 · 턴 16
- 요약: 사이클 33549c9c13fd 최종 보고(앞선 보고들을 모두 대신함).
(1) 패킷 2개를 읽었다. decision 7fe237e0은 S3 v1b 채택이고, request 4b9de16d는 S2 v4 동결과 job-run 수정이 main에 반영됐다는 내용이다. Pro main은 이미 90ef9c7이다.
(2) S2 positive 13개를 기록했다(work/agent/labels_batch7a~j.json).
- 접촉 yes 6개: 00874, 00872, 00880, 00961, 00891, 00949
- 접촉 uncertain 5개(사람 검수 필요): 00849, 00860, 00867, 00887, 00947
- 접촉 no(near-miss) 2개: 00861, 00902
(3) qa 'stage2 labels v5'(8f91defc65c14471aaa3ab54cb21058b)를 보냈다. positive 72개와 negative 24개이고, 라벨 출처는 human 0 / agent 96이다. collision_valid는 55, entry_valid는 26이다. 남은 positive는 8개다.
(4) S3 steering 부호 review(517ecb9b23c44ad6bad7d474f7dfccd9)를 보냈다. 결론은 steering_angle_deg 양수가 좌회전이라는 것이다. comma hevc 영상에서 지평선 띠의 수평 이동(phase correlation)과 CAN steering의 상관을 쟀고, 23/23 source 모두 양의 상관이었다(0.006~0.891, 중앙값 약 0.60, n=12,904). 합성 테스트로 dx>0이 영상 내용의 오른쪽 이동이라는 것도 확인했다. 한계: |steer|>20도 구간은 데이터에 없어 검증하지 못했고, 핸들각인지 바퀴각인지는 판단하지 못했다. v1b 규칙은 바꿀 필요가 없다.
(5) S1 job 13505ad3f6fd는 실행 중이다. 03:17Z 기준 mp4 41/120개이고, 약 04:25Z에 끝날 것으로 본다.
(6) docs/STATUS.md를 갱신했다.
근거: work/agent/outbox/stage2_labels_v5.json, work/agent/outbox/s3_steer_sign_v1.json, work/s3_steer/, data/derived/labels/agent/stage2_agent_labels.csv.
- 사람에게 요청: S23 실촬영: data/captures/s23/에 실촬영 파일이 없다. 사람이 촬영해야 한다. / S2 사람 검수: 접촉이 확인되지 않은 사례 00082, 00282, 00291, 00295, 00527, 00566, 00600, 00660, 00692, 00723, 00849, 00860, 00867, 00887, 00947을 검수해 주세요. 00064는 주 접촉이 불명확하고, 00861과 00902는 near-miss로 판단한 것을 확인해 주세요.

## 09-25 12:19 ~ 09-25 12:24 · `6330f850f8c7` · succeeded
- 깨운 이유: scheduled · 비용 $3.82 · 턴 8
- 요약: 사이클 6330f850f8c7 최종 보고(앞선 중간 보고들을 대신함).
(1) S2 positive 마지막 8개를 라벨해 기록했다(work/agent/labels_batch8a~g.json).
- 접촉 yes: 00979(collision 603, 같은 차로 추돌, confidence 0.7), 00998(collision 574, 비스듬한 추돌, 0.6), 00985(collision 769, entry 740 LEFT, 교차로 측면 충돌, 0.6), 00976(collision 540, entry 488 LEFT, 교차로 회전 중 접촉, 0.4)
- 접촉 uncertain(사람 검수 필요): 00989(0.3, 사건 시각이 클립 끝 직후), 00996(0.3), 01037(0.35), 01028(0.2)
(2) qa 'stage2 labels v6'(최종, 8d1ee506b7ff4248bcdaf462f76e7fa5)를 보냈다. positive 80개(yes 59, uncertain 19, no 2)와 negative 24개이고, 라벨 출처는 human 0 / agent 104다. collision_valid 59, entry_valid 26이다. 이로써 positive 라벨은 모두 끝났다.
(3) S1 job 13505ad3f6fd는 실행 중이다. 03:23Z 기준 mp4 59/120개이고, 약 04:05~04:25Z에 끝날 것으로 본다.
(4) docs/STATUS.md를 갱신했다.
근거: work/agent/outbox/stage2_labels_v6.json, work/agent/outbox/stage2_labels_v6_files/stage2_merged_v6.csv, data/derived/labels/agent/stage2_agent_labels.csv.
- 사람에게 요청: S23 실촬영 파일을 data/captures/s23/에 넣어 주세요. 현재 0개입니다. / S2 접촉 여부를 에이전트가 판단하지 못한 사례를 사람이 검수해 주세요: 00082, 00282, 00291, 00295, 00527, 00566, 00600, 00660, 00692, 00723, 00849, 00860, 00867, 00887, 00947, 00989, 00996, 01028, 01037. near-miss로 판단한 00861과 00902도 확인이 필요합니다.

## 09-25 12:30 ~ 09-25 12:30 · `17a8dab19011` · succeeded
- 깨운 이유: packet · 비용 $0.35 · 턴 7
- 요약: 사이클 17a8dab19011 결과:
(1) decision 79e03f92(S3 steering 부호 review 517ecb9b 채택)를 읽었다. 결정은 양수=LEFT 유지이고 s3_proxy_rule_v1b는 바뀌지 않는다. Pro가 따로 할 일은 없다. 남은 한계는 |steer|>20도 구간 미검증, 핸들각인지 바퀴각인지 미구분이다.
(2) S1 합성 job 13505ad3f6fd는 실행 중이다. 03:30Z 기준 mp4 72/120개, 243MB이고, 약 04:00Z에 끝날 것으로 본다.
(3) S2 positive 라벨(v6 최종)과 S3 규칙은 모두 끝났다. 새로 할 우선순위 작업은 S1 QA와 발송뿐이다.
(4) docs/STATUS.md를 갱신했다.
근거: data/derived/experiment_packets/inbox/79e03f9261794995924be681c79fe610/decision.json, data/derived/s1_synthetic_v1/, docs/STATUS.md.
- 사람에게 요청: S23 실촬영 파일을 data/captures/s23/에 넣어야 한다(현재 0개). / S2 에이전트 라벨 중 불확실한 22건(STATUS의 Blocked 목록)은 사람 검수가 필요하다.

## 09-25 12:36 ~ 09-25 12:37 · `33557b751a3d` · succeeded
- 깨운 이유: packet · 비용 $0.42 · 턴 11
- 요약: 사이클 33557b751a3d 결과:
(1) decision 39f66ffc(S3 steering 부호 채택, exp-b1a03043…)를 읽었다. 앞서 받은 79e03f92와 결론이 같다. 양수=LEFT를 유지하고 s3_proxy_rule_v1b는 바뀌지 않으므로 Pro가 할 일은 없다. 이 규약은 S2 entry_side에도 그대로 적용되며, 이미 받은 라벨과 어긋나지 않는다.
(2) S1 합성 job 13505ad3f6fd는 실행 중이다. 03:37Z 기준 mp4 82/120개, 266MB이고, 약 04:05Z에 끝날 것으로 본다.
(3) 부분 출력으로 s1_qa.py를 미리 돌려 스크립트가 정상인지 확인했다. manifest 80행(train 16 source)은 모두 300프레임으로 디코드됐고, 최대 파일은 10.8MB로 512MiB 한도보다 훨씬 작다. 문제 2건은 SRC017이 아직 만들어지는 중이고 SRC017~024가 아직 없다는 것뿐이며, 둘 다 job이 진행 중이라 생긴 것이다. 임시 결과 파일은 지웠다.
(4) docs/STATUS.md를 갱신했다. main checkout은 깨끗하다.
근거: data/derived/experiment_packets/inbox/39f66ffc41774b5c935033c8cb5f1e88/decision.json, data/derived/s1_synthetic_v1/manifest.csv, docs/STATUS.md.
- 사람에게 요청: S23 실촬영 파일을 data/captures/s23/에 넣어야 한다(현재 0개). / S2 에이전트 라벨 중 접촉이 불확실하거나 near-miss인 22건은 사람이 검수해야 한다(목록: docs/STATUS.md의 Blocked).

## 09-25 13:03 ~ 09-25 13:07 · `5445f531ec31` · succeeded
- 깨운 이유: job_finished · 비용 $1.12 · 턴 32
- 요약: S1 합성 job 13505ad3f6fd가 성공해 QA를 돌렸고 통과했다(문제 0건). 24 source에서 ORIG와 SYN0~3으로 mp4 120개를 만들었다. 모두 300프레임, 30fps, 960x540이고 합계 384MB다. split은 train 16 / val 4 / test 4다. qa 's1 synthetic v1'(b1494b0e)은 synthetic 표시로 보냈다. 생성·QA 스크립트는 pro/s1-synth(3a81448)에 올리고 request(16babe65)로 병합을 요청했다. 13:06에 main의 agent_bridge/runner.py와 tests가 수정됐는데, 이 사이클이 만든 변경이 아니어서 건드리지 않았다. 근거: data/derived/s1_synthetic_v1/s1_qa_report.json, docs/STATUS.md.
- 사람에게 요청: S23로 S1 재촬영 영상을 촬영해 data/captures/s23/에 넣기(실촬영이 있으면 검증 split에 우선 사용) / S2 에이전트 라벨 중 uncertain/near-miss 사례(00082, 00282, 00291, 00295, 00527, 00566, 00600, 00660, 00692, 00723, 00849, 00860, 00867, 00887, 00947, 00989, 00996, 01028, 01037, 00861, 00902, 00064)를 사람 CSV에서 검수 / Pro main checkout의 미커밋 수정(agent_bridge/runner.py, tests/test_agent_bridge.py, 13:06 KST)이 의도한 작업인지 확인하고 정리

## 09-25 13:15 ~ 09-25 13:17 · `933814494ead` · succeeded
- 깨운 이유: packet · 비용 $0.83 · 턴 21
- 요약: decision 9f432038을 확인했다. 내용은 S1 synthetic v1 채택(release s1-synth-v1-20260925)과 pro/s1-synth의 main 441e8cc 병합이며, Pro가 할 일은 없다. S3 result를 검토할 도구 work/pro_tools/s3_review.py를 만들었고 자체 시험을 통과했다(oracle 1.0, 손상 CSV는 fail로 잡음). 확인 결과 train_stage3.evaluate()는 조향 F1에 STOPPED 행을 포함하고(evaluation.md와 불일치, validation STOPPED 264/2396) 샘플별 예측을 저장하지 않는다. 그래서 request cc85c058을 보내 예측 CSV 첨부와 STOPPED 제외 조향 F1을 요청했다. 근거: docs/STATUS.md, work/s3_review_selftest/.
- 사람에게 요청: S23 실촬영 파일을 data/captures/s23/에 넣기(아직 0개) / S2 불확실 사례의 사람 검수(STATUS.md Blocked 목록 22건)

## 09-25 13:22 ~ 09-25 13:24 · `1a1ef90398d5` · succeeded
- 깨운 이유: packet · 비용 $0.64 · 턴 18
- 요약: Ultra request 6c2eff09(cc85c058에 대한 회신)를 확인했다. origin/main 20161cf 트레이너가 이제 val_predictions.csv를 저장하고 조향 F1을 STOPPED 제외로 계산한다. 재학습 job은 c51ef23b8092다. 이 요청으로 Pro가 따로 할 일은 없다. work/pro_tools/s3_review.py에 트레이너 *_true 열과 다시 계산한 GT의 일치 검사(trainer_label_check)를 넣었다. 자체 시험 5건은 모두 예상대로 나왔고, 불일치 7건도 fail로 잡았다. docs/STATUS.md를 갱신했다. 근거: work/s3_review_selftest/*.report.json.

## 09-25 13:56 ~ 09-25 13:59 · `e6fd49a3b6f0` · succeeded
- 깨운 이유: packet · 비용 $1.04 · 턴 25
- 요약: Ultra result e96d05bb(S3 e001)를 검토하고 review a354ad90을 보냈다. 첨부된 val_predictions.csv로 CPU에서 다시 계산해 4개 지표가 끝자리까지 일치했다(accel 0.1815, steer official 0.4082, mean 0.2948). 2,396행이고 누락·중복·split 혼입·라벨 불일치는 0이다. 수치는 proxy v1b 기준이며 공식 GT가 아니다. 가장 큰 문제는 accel이다. 예측의 89%가 CONSTANT이고 STOPPED는 한 번도 예측하지 않았으며, DEC를 ACC로 틀린 것이 159건이다. 모두 CONSTANT로 찍었을 때(0.147)보다 조금 높을 뿐이다. 제안은 하나로, speed_mps 회귀 헤드를 두고 예측 속도에 v1b 규칙을 적용해 accel 클래스를 정하는 것이다. 근거: work/s3_review_e001/, docs/STATUS.md.

## 09-25 14:04 ~ 09-25 14:07 · `8d19ac92dc84` · succeeded
- 깨운 이유: packet · 비용 $0.78 · 턴 18
- 요약: decision 2a905805(S3 e001 accept, e002=speed 회귀+v1b)를 확인했다. Pro가 할 일은 없다. GPU 학습 전에 CPU로 점검해 보니 acceleration_mps2_proxy는 np.gradient(speed,t)와 정확히 같았다. gradient→평활→classify 순서면 v1b를 100% 재현하지만, 계획 문구(평활 speed의 차분)대로면 val F1이 0.990, train이 0.971이다. 잡음 민감도(낙관적 시뮬레이션)는 MAE 0.4일 때 0.574, 1.6일 때 0.419다. 상수 예측 MAE가 9.46이라 decision의 MAE 기각 기준은 너무 약하다. request 824b3122로 후처리 정정과 speed_pred 열 추가를 요청했다. 근거: work/s3_e002_precheck/report.json, docs/STATUS.md
- 사람에게 요청: S23 실촬영 파일을 data/captures/s23/에 넣어야 한다(현재 0개). / S2 불확실 사례(STATUS Blocked 목록 22건)를 사람이 검수해야 한다(현재 reviewed 0건).

## 09-25 14:15 ~ 09-25 14:16 · `cbc52b4e61ea` · succeeded
- 깨운 이유: packet · 비용 $0.63 · 턴 15
- 요약: decision 82aed150(request 824b3122 accept)을 확인했다. Ultra가 e002의 accel 후처리 헬퍼를 origin/main 21da08c에 넣었고, Pro가 할 일은 없다. 이 헬퍼를 CPU에서 따로 검증했다. 정답 speed를 넣으면 elapsed_seconds가 있을 때와 없을 때(추론 경로, 0.1s 간격) 모두 train/val/test 정확도 1.0이고, 행 순서를 섞어도 1.0이다. 클립을 잘라 적용하면 경계 효과로 val 정확도가 0.994(50행)~0.999(200행)로 조금 내려가며, 무시할 수준이다. 새로 보낼 내용이 없어 패킷은 보내지 않았다. 근거: work/s3_e002_helper_check/report.json, docs/STATUS.md

## 09-25 14:43 ~ 09-25 14:46 · `2a4e0e3b0f2a` · succeeded
- 깨운 이유: packet · 비용 $1.21 · 턴 32
- 요약: Ultra의 S2 e001 result(57d5574c)를 검토해 review 5c2ac03f를 보냈다. split을 그대로 재현했고 지표 4개가 끝자리까지 일치했다(collision 5.736s, entry 9.071s, evasion 0.833, side 0.375). 무결성 문제는 0건이며, 라벨 출처는 human 0 / agent 104다. 가장 큰 문제는 train 라벨로 만든 '영상 길이×중앙 비율' 상수 예측이 같은 val에서 0.667s라는 점이다. 모델(7.40s)은 이보다 약 11배 나쁘고, evasion과 side도 다수 클래스만 찍은 것보다 낮다. 제안은 하나로, 사건 위치를 무작위로 바꾸는 시간 crop으로 학습하고 상수 예측과 비교해 체크포인트를 고르는 것이다. 근거: work/s2_review_e001/report.json, docs/STATUS.md.

## 09-25 14:47 ~ 09-25 14:53 · `5765f2c1238d` · succeeded
- 깨운 이유: packet · 비용 $1.32 · 턴 34
- 요약: Ultra request 418597dd는 결정 8 수신 확인이고, v001을 먼저 한 뒤 handoff한다는 내용이라 Pro가 할 일은 없었다. 준비 중 stage2_agent_label.py add가 사람 CSV의 104개 ID만 받아 확장 Nexar 약 300개를 기록할 수 없다는 것을 찾았다. pro/s2-ext-labels 72c7258에서 --meta 옵션, nexar_event·contact_unverified 병합, collision_frame_source 열을 추가했다. 테스트 5개가 통과했고, 실제 v6 회귀 비교에서 차이는 0건이다. request 7c8a6eeb로 병합을 요청하고 handoff metadata 형식을 제안했다. 근거: work/s2_merge_regress/report.json, docs/STATUS.md

## 09-25 14:54 ~ 09-26 14:59 · `e3fdeb296b51` · interrupted_by_loop_restart
- 깨운 이유: packet · 비용 $0.00 · 턴 -

## 09-26 15:12 ~ 09-26 15:16 · `a5816c950dec` · succeeded
- 깨운 이유: packet · 비용 $1.63 · 턴 42
- 요약: 중단된 사이클이 남긴 패킷 3개를 처리했다. decision 823680cb와 request be223d55(pro/s2-ext-labels 병합 완료)는 Pro가 할 일이 없었다. S1 e001 result(3df51096)는 지표가 재현됐고(20/20, sha 일치) 무결성도 통과했다. 다만 합성 v1의 단서는 Baseline 공식 재촬영 5쌍과 방향이 반대다. 공식 쌍은 픽셀이 정렬돼 있고 HF ×1.24, MPEG-4→x264이며, 실제 예제에 단일 특징 규칙을 적용하면 acc 0.4~0.5다. review 37dc31b4로 v1c 디지털 재촬영과 Baseline 10개 게이트를 제안했다. 생성기 pro/s1-synth-v1c 31842e3을 push하고 request 031048f1로 병합을 요청했다. 96개 생성 job fbcb58b4a92e가 실행 중이다. 근거: work/s1_review_e001/, docs/STATUS.md
- 사람에게 요청: S23으로 S1 실촬영을 하고 data/captures/s23/에 넣어 주세요(공식 재촬영 성능을 확인할 유일한 실제 데이터). / DACON 업로드는 Ultra가 검증된 zip을 보고한 뒤 사람이 진행해 주세요.

## 09-26 15:17 ~ 09-26 15:18 · `c3e15c6017ae` · succeeded
- 깨운 이유: packet · 비용 $0.57 · 턴 11
- 요약: decision 4dcc8017을 확인했다. Ultra가 S1 e001 review를 수용했다. e001은 Baseline 공식 10예제를 전부 RERECORDED로 예측했고 acc 0.5, macro-F1 0.333이며, 이 값을 기준값으로 고정했다. 채택 게이트는 Baseline 10예제로 바꿨고, v1c 재학습(exp-b1463eb2)은 v002 후보다. Pro가 할 일은 v1c qa 패킷이며, variant별 파라미터는 manifest params 열에 이미 기록되고 있다. 생성 job fbcb58b4a92e는 96개 중 38개까지 만들었고 아직 실행 중이다. 이번 사이클에 보낸 패킷은 없다. 근거: docs/STATUS.md, data/derived/s1_synthetic_v1c/manifest.csv

## 09-26 15:21 ~ 09-26 15:35 · `348b7dd35543` · succeeded
- 깨운 이유: packet · 비용 $1.46 · 턴 40
- 요약: decision ee032b7a는 v1c 병합 완료 통보다. v1c 1차 96개는 구조 QA를 통과했다. 그러나 DIG 48개 중 HF 비율 목표(1.1~1.45)에 든 것이 10개뿐이고, 29개는 ORIG보다 파일이 작아 qa로 보내지 않았다. 원인은 x264가 약한 grain을 지워 sigma와 HF의 관계가 계단형인데 보정을 1회만 한 것이다. pro/s1-v1c-calib 0741ddd에서 반복 보정(최대 8회, 구간 secant, sigma 상한 12)으로 고쳤다. 테스트 6개가 통과했고, 최악 source 6개로 시험한 DIG 12개도 모두 ±0.04 안이었다. 재생성 job 6588dc8ba27e가 실행 중이며, request bf437818로 병합을 요청했다. 근거: work/s1_qa_v1c/, docs/STATUS.md

## 09-26 15:36 ~ 09-26 15:49 · `f5a5120cfefe` · succeeded
- 깨운 이유: job_finished, packet · 비용 $2.13 · 턴 53
- 요약: S2 e002 result 1cbca34d를 검토해 review f62cad3f를 보냈다. const_baseline은 1.1874s로 끝자리까지 재현됐다. 모델 지표는 예측 CSV가 없어 재계산하지 못했다(metrics_reproduced=null). 반증 시험은 제안한 crop 평가가 아니라 전체 클립 기준으로 수행됐다. 가장 큰 문제는 형식 불일치다. 공식 S2 예제는 10fps 50프레임이고 충돌 프레임이 30~41인데, 학습은 30fps 약 1,200프레임으로 했다. 제안: 특징을 10Hz로 재샘플링하고 50프레임 창으로 학습·평가하며, 공식 5예제로 게이트를 둔다. S1 v1c r2 job은 성공했고 QA도 통과했다(96개, calib_ok 46/48, 바이트 비율 1 미만 0개). qa 3992576b로 보냈고 r1은 삭제했다. 근거: work/s2_review_e002/, work/s1_qa_v1c/r2_report.json

## 09-26 15:50 ~ 09-26 15:51 · `a447a73fdb3f` · succeeded
- 깨운 이유: job_finished, packet · 비용 $0.57 · 턴 13
- 요약: decision faeb4411을 확인했다. pro/s1-v1c-calib가 main c1f7495에 병합됐고 accept됐다. Ultra는 r2 qa를 받은 뒤 v1c release와 재학습을 진행한다. r2 qa 3992576b는 이미 보냈고 job 6588dc8ba27e도 직전 사이클에서 처리했으므로 새로 보낸 패킷은 없다. 병합이 끝난 pro/* worktree 5개는 모두 깨끗한 상태여서 로컬에서 제거했다. 원격 브랜치는 남겨 두었고 디스크 여유는 22GB다. 이제 S2 e002 decision, S1 v1c result, Nexar 640px handoff, comma 클립을 기다린다. 근거: docs/STATUS.md

## 09-26 15:54 ~ 09-26 16:03 · `cdb56980a5db` · succeeded
- 깨운 이유: scheduled · 비용 $1.71 · 턴 31
- 요약: 결정 9에 따라 v1c 코덱 동일 쌍 생성을 시작했다. 방식은 창마다 ORIGX와 DIGM0를 추가하는 것이다. ORIGX는 x264 원본이고 DIG0와 바이트를 맞췄다. DIGM0는 mp4v 재촬영이고 ORIG와 바이트를 맞췄으며 HF를 다시 보정했다. 그러면 창마다 4쌍 중 2쌍이 코덱 동일(50%)이 되고, 파일 단위로는 코덱·비트레이트가 라벨 정보를 갖지 않는다. 코드는 pro/s1-v1c-codec 5b1b574다. 테스트 8개가 통과했고 DIG0 회귀 sha도 일치했다. 시험 4창에서 바이트 비율은 0.94~1.03, calib_ok는 4/4였다. 48창 생성 job 6dfdef7d0601이 실행 중이다. 병합은 request 7ee18d9b로 요청했다. 근거: docs/STATUS.md

## 09-26 16:04 ~ 09-26 16:06 · `e4d49246509b` · succeeded
- 깨운 이유: packet · 비용 $0.79 · 턴 15
- 요약: decision 63bd009c(S2 e002 review 수용)를 확인했다. 공식 5예제 실측 MAE는 e001 1.06s, e002 1.18s로 상수 0.78s보다 나쁘다. 첨부 예측으로 두 값을 재계산해 일치를 확인했다. Ultra는 e003(10Hz·50프레임)을 진행 중이다. Pro가 할 일은 없고 보낸 패킷도 없다. 코덱 동일 쌍 job 6dfdef7d0601은 96개 중 30개까지 진행됐다. 완료 후 바로 돌릴 QA 도구 work/pro_tools/s1_qa_cm.py를 준비했고, 부분 출력에서 파일 검사까지 오류 없이 돌았다. 근거: docs/STATUS.md

## 09-26 17:26 ~ 09-26 17:32 · `24e618073083` · succeeded
- 깨운 이유: job_finished · 비용 $1.95 · 턴 40
- 요약: 코덱 동일 쌍 job 6dfdef7d0601 결과 96개가 QA를 통과했다. 50% 동일 코덱이고 calib_ok는 47/48이다. 처음 걸린 96건은 cv2 FOURCC 도구 버그였고 ffprobe 비교로 고쳤다. qa f977044a로 보냈다. 결정 10의 1-1로 S2 상수 시점 기준선을 계산해 qa ce085743으로 보냈다. 공식 5예제에서는 충돌 30~33이 Acc@0.3 0.8이다. toe−3초 창 가설에서는 충돌 30이 0.85, 진입 22가 0.42~0.47이다. 10fps에서 3프레임 차이 47쌍 중 22쌍은 부동소수점 때문에 0.3초 판정에서 빠진다. 근거: work/s1_qa_v1c/cm_report.json, work/s2_const_acc03/report.json

## 09-26 17:42 ~ 09-26 17:46 · `931cd1e37ac9` · succeeded
- 깨운 이유: packet · 비용 $1.74 · 턴 36
- 요약: decision affe7365(v1c-codec 병합, release 192개 동결, metrics.py)을 확인하고 병합된 worktree를 정리했다. S2 e003 result를 검토해 review 61eea74c를 보냈다. 10Hz 상수 기준값과 창 center MAE는 끝자리까지 재현됐다. 공식 5예제 Acc@0.3초는 e001 0.0, e003 0.4, 상수 30 0.8이다. 따라서 미채택 결론은 맞지만, MAE 게이트가 매긴 e001·e003 순서는 공식 식과 반대다. 가장 큰 문제는 학습·평가 창에서 충돌 위치가 균등 분포라는 점이다(공식 범위 30~41에 드는 비율 25%). 제안: 충돌이 창의 25~41에 오도록 창을 두고, prior+잔차 헤드를 쓰고, metrics.py S2로 체크포인트를 선택한다. 근거: work/s2_review_e003/report.json

## 09-26 17:52 ~ 09-26 17:56 · `ce489c171964` · succeeded
- 깨운 이유: input_changed · 비용 $0.83 · 턴 14
- 요약: input_changed(data/captures/s23)를 확인했다. 사람이 폴더만 만들었고 촬영 파일은 아직 0개다. 파일이 오면 바로 쓸 S23 QA 도구 work/pro_tools/s23_qa.py를 만들었다. 이 도구는 이름과 촬영표 split 연결, 512MiB 한도, sha, ffprobe, 디코드 프레임 수, 과노출을 검사한다. 또 밝기 시계열을 교차상관해 원본 일치와 시작 시각을 구하고, 다른 23개 source와 비교해 이름이 잘못 붙은 파일을 찾는다. 셀프 테스트에서 가짜 촬영본은 ncc 0.82, 시작 2.03초로 맞게 찾았다. 이름을 잘못 붙인 파일도 걸렸다. 보낸 패킷은 없다. 근거: work/s23_qa_selftest/out/, docs/STATUS.md
- 사람에게 요청: S23 촬영 파일을 docs/HUMAN_TASKS.md 표의 이름(예: SRC017_C1_take01.mp4)으로 C:\Dacon\Dacon_AFDA_Challenge_git\data\captures\s23\에 넣기. 검증·시험용 16테이크를 먼저 넣는다

## 09-26 18:05 ~ 09-26 18:08 · `d4b1cc7f0090` · succeeded
- 깨운 이유: packet · 비용 $1.13 · 턴 29
- 요약: Ultra가 보낸 v001b result 4f4c9dfc(S2 충돌 인덱스30·진입 인덱스22 상수, 나머지는 v001 그대로)를 검토했고 review 29cc0d37을 보냈다. 판정은 무결성·재현·비교 가능 모두 통과다. v001 코드와 비교하면 바뀐 곳은 S2 시점 두 줄뿐이다. 공식 5예제의 충돌 Acc@0.3초를 따로 계산해 보니 0.8로 같았다. 진입은 공식 정답이 모두 -1이라 잴 수 없었다. zip은 첨부되지 않아 sha를 대조하지 못했고, Ultra의 3-stage 종단 검증은 아직 진행 중이다. 제안: 리더보드 S2 변화량(0.35·충돌 + 0.35·진입)으로 결과를 해석할 기준표를 미리 정한다. 근거: work/s2_review_v001b/report.json
- 사람에게 요청: Ultra가 v001b zip(work/submit_v001b.zip, sha 56d6c4b2…)의 3-stage 종단 검증 통과를 보고하면 DACON에 업로드하기

## 09-26 18:14 ~ 09-26 18:16 · `d2d5f750bce6` · succeeded
- 깨운 이유: packet · 비용 $0.95 · 턴 16
- 요약: decision 18ac3d3b(v001b 제출 확정, zip sha 56d6c4b2)와 a41f4f79(v002 S2 = e004, 공식 배치 창)는 모두 accept라 답신하지 않았다. e004 게이트용 기준을 미리 계산했다. val 충돌 12개(사람 라벨 0, 에이전트 라벨 104) 기준이다. 충돌 위치를 25~41에 균등 배치하면 상수 30의 Acc@0.3은 0.412다. 공식 5배치(32,30,31,41,30)에서는 상수 30이 0.8, 진입 상수 22가 0.40이다. 창을 무작위로 뽑으면 std가 0.063이다. 따라서 균등 창에서 상수를 이겨도 실제 상수 수준(0.8)을 넘는다는 보장은 없다. 공식 5배치 창을 게이트 기준으로 쓰자고 제안하는 qa dac74659를 보냈다. 근거: work/s2_e004_gate_prep/report.json
- 사람에게 요청: DACON에 v001b zip(work/submit_v001b.zip, sha 56d6c4b2…, Ultra PC)을 오늘 자정(KST) 전에 업로드하고, Stage별 점수를 Ultra에 알려 주세요. / S23 실촬영 파일을 data/captures/s23/에 넣어 주세요(현재 0개).

## 09-26 18:24 ~ 09-26 18:27 · `710343b4787c` · succeeded
- 깨운 이유: packet · 비용 $1.20 · 턴 27
- 요약: decision 4a206d6f(S2 e004 게이트 FAIL, accept)를 확인했다. 우리 qa dac74659가 수용됐으므로 답신은 보내지 않았다. v002 S2 시점은 상수 30/22로 동결되고, 남은 개선은 S3 e002와 S1 v1+v1c 혼합 학습이다. S1 혼합 result 검토 도구 work/pro_tools/s1_mixed_review.py를 만들었다. 이 도구는 v1·v1c·min 점수, 코덱별 S1 게이트, 쌍 순위 정확도, 무결성을 계산한다. 셀프 테스트에서 oracle은 1.0이었다. 코덱만 보는 가짜 모델은 v1c 0.5, 코덱 내부 0.333으로 FAIL이 났다. 근거: work/s1_mixed_review_selftest/report.json, docs/STATUS.md

## 09-26 19:30 ~ 09-26 19:36 · `1c8c5fd8ab28` · succeeded
- 깨운 이유: packet · 비용 $2.26 · 턴 36
- 요약: S3 e002 result 182256b5를 검토해 review ae25318b를 보냈다. official 값을 성분으로 다시 계산했고, steer가 모두 STRAIGHT로 붕괴한 것(0.30729)도 재현됐다. val_predictions가 첨부되지 않아 accel은 재현하지 못했다(reproduced=null). e001 accel은 같은 예측 분포로 무작위로 찍은 수준(0.179)이다. e002는 그보다 +0.083 높다. 가장 큰 문제는 두 모델 모두 STOPPED를 한 번도 예측하지 않는 것이다(accel 상한 0.75). 제안: 예측 속도용 STOPPED 임계값을 source 단위 LOSO로 보정한다(GPU 불필요). v1b 규칙은 공식 50행 분포와 가장 가깝고(TV 0.045) 치우친 것은 val split이다. 근거: work/s3_review_e002/report.json

## 09-26 19:41 ~ 09-26 19:43 · `68a023d84ff9` · succeeded
- 깨운 이유: packet · 비용 $0.89 · 턴 14
- 요약: decision 85a39239(S3 e002 검토 수용)에 첨부된 e002 예측으로 v_stop_pred LOSO를 돌렸다. 무결성은 2396행 1:1 조인, 정답과 v0.5 파생 결과 100% 일치다. 요청 격자 0.5~5.0에서 Δaccel 0.0, STOPPED F1 0이 나와 반증 조건을 충족했다. 그래서 후처리는 폐기한다. 예측 속도 최솟값이 4.74 m/s이고 실제 정지 행의 예측 중앙값은 13.98 m/s다. AUROC 0.878이라 순위 정보는 있지만, 저속 구간 예측이 평균 쪽으로 수축한다. 격자를 25까지 넓혀도 Δ는 +0.010이다. STOPPED 이진 헤드로 가자고 권고하는 qa 13cad578을 보냈다. 근거: work/s3_vstop_e002/

## 09-26 19:51 ~ 09-26 19:56 · `77c4afbe135c` · succeeded
- 깨운 이유: packet · 비용 $1.15 · 턴 19
- 요약: decision 4fb9418c(v_stop_pred 후처리 폐기, STOPPED 이진 헤드 e004 구현)는 우리 qa를 받아들인 것이라 답신하지 않았다. e004 검토 도구 work/pro_tools/s3_stopped_gate.py를 만들었다. e002 예측으로 돌려 official 0.29843을 끝자리까지 재현했고 셀프 테스트도 통과했다. 한계: val의 STOPPED 행은 SRC017·SRC020 두 source에만 있어 임계값 LOSO의 근거가 약하다. request 918be48a를 보냈다: accel_pred_raw 열과 base run 예측을 첨부해 달라는 내용이다. 디스크 여유는 15GB다.

## 09-26 22:35 ~ 09-26 22:37 · `da8b18df6dd2` · succeeded
- 깨운 이유: heartbeat · 비용 $0.89 · 턴 14
- 요약: heartbeat 사이클에서 S23 실촬영 48개(24 source × 2 조건, 746MB)가 들어온 것을 확인했다. 파일 이름은 촬영표 48행과 모두 맞는다. 코덱은 HEVC 1080p 약 30fps이고, 길이는 7.0~9.9초로 모든 파일이 10초 클립보다 짧다. 이 점은 경고로만 다룬다. QA job 09f2ce90089a(s23_qa.py → work/s23_qa_b1/)를 큐에 넣었고, 원본 일치 ncc, 프레임 수, sha를 확인한다. 영상은 exchange_bridge가 Ultra로 자동 반환하므로 qa 패킷에는 manifest, report, 시트만 첨부할 예정이다. 이번 사이클에 보낸 패킷은 없다. 근거: docs/STATUS.md

## 09-26 22:38 ~ 09-26 22:45 · `6b0ebfd53189` · succeeded
- 깨운 이유: input_changed · 비용 $2.02 · 턴 59
- 요약: S23 QA job 09f2ce90089a가 성공했다. 48개 모두 사용 가능하다. ncc 의심 19개는 원본 대조 시트로 눈으로 확인했고 모두 이름과 일치했다. HEVC 30fps와 h264 20fps의 코덱 지름길을 경고하는 qa 2cae1c61을 보냈다. 사람이 S2 22개를 reviewed로 확정해 병합본 v7을 만들었다(human 22, agent 82, collision_valid 59→68). 에이전트와 비교한 결과와 nexar_event와 사람 충돌 프레임 비교(중앙값 0.30초, 5/10이 0.3초 이내)를 qa 8bd9776b로 보냈다. 근거: work/s23_qa_b1/, work/s2_human_vs_agent/, docs/STATUS.md

## 09-26 22:47 ~ 09-26 22:49 · `5aaab7995b67` · succeeded
- 깨운 이유: job_finished, packet · 비용 $0.99 · 턴 17
- 요약: decision cfafb2ad(accept)를 받았다. e004 base는 e001 argmax로 정해졌고 accel_pred_raw 열이 추가됐으며 e004 학습이 시작됐다. 첨부된 e001 base 예측을 독립 도구로 재현했다: official 0.249515, 무결성 통과. STOPPED override 상한을 계산했다. oracle이면 0.433이고, iid 모의에서 recall 0.75·FP 5%이면 0.376이다. recall 0.25·FP 10%도 base를 넘으므로 'official > base' 게이트는 약한 기준이라는 qa 42f09b04를 보냈다. s23 QA job 완료는 직전 사이클에서 이미 처리했다. 근거: work/s3_stopped_gate_e001_base/, work/s3_stopped_ceiling_e001/

## 09-26 22:52 ~ 09-26 22:59 · `1f7186a02665` · succeeded
- 깨운 이유: packet · 비용 $1.41 · 턴 33
- 요약: decision e0851f4c(S23 수용)와 e3f279c0(S2 v7 동결)은 accept라 답신하지 않았다. S23 match_start_s는 48개 모두 0 이하라 원본 시작은 -match_start_s이고, 그대로 쓰면 원본 구간이 어긋난다. SRC018_C3(val)의 lag 4.06초는 틀려서 시트를 눈으로 보고 0.6초로 고쳤다. 나머지 val/test 15개도 눈으로 일치를 확인했다. 정렬표와 시트를 qa e1114881로 보냈다. e3f279c0은 상수 시점이 LB에서 기각(ΔS2 -0.0435)됐다고 하면서도 zip을 v001b로 유지한다고 해 모순된다. 그래서 다음 zip의 S2 시점을 v001로 되돌려 달라는 request edf1ff7f를 보냈다. 근거: work/s23_align_b1/

## 09-26 23:00 ~ 09-26 23:02 · `204d7eaad4ac` · succeeded
- 깨운 이유: packet · 비용 $0.79 · 턴 14
- 요약: decision 844c6074(e004 강화 게이트 사전 등록, accept)와 request 6f49ae3a(결정 11: 상수 시점 폐기, 다음 zip의 S2 시점은 v001 모델)를 받았다. 둘 다 우리 제안을 받아들인 것이라 답신하지 않았다. s3_stopped_gate.py에 refined_gate를 추가했다. 검사 항목은 precision ≥0.8, recall ≥0.5, margin +0.05, 다른 source 발화 0, 상한 0.433 대비 위치, base 보존이다. 셀프 테스트는 통과했고, e001을 자기 자신과 비교한 점검도 정상이었다(work/s3_stopped_gate_e001_self/). 근거는 docs/STATUS.md에 있다.

## 09-26 23:05 ~ 09-26 23:07 · `2b8bed93dabb` · succeeded
- 깨운 이유: packet · 비용 $0.80 · 턴 13
- 요약: decision 2개를 받았고 둘 다 accept라 답신하지 않았다. c85dd4a7은 S23 release s1-s23-real-v1-20260926(48쌍) 동결이다. Ultra가 기록한 정렬표 sha 3764c0f7…는 우리가 보낸 CSV와 같다. e11993ec은 다음 zip의 S2 시점을 v001 경로로 한다는 결정이다. S23 result 검토 도구 work/pro_tools/s23_eval_review.py를 만들었다. 무결성, S1을 all_rows와 unique_orig로 따로 계산, 조건별 recall, 쌍 순위, 1개 오류 변동폭을 본다. 셀프 테스트는 통과했다(work/s23_eval_review_selftest/). 근거는 docs/STATUS.md에 있다.

## 09-26 23:26 ~ 09-26 23:29 · `fe798a58f365` · succeeded
- 깨운 이유: packet · 비용 $1.14 · 턴 24
- 요약: S3 e004 result c0b9154e를 독립 도구로 재계산했다. 수치가 모두 재현됐다(official 0.35631, STOPPED precision 1.0, recall 0.4508, 다른 source FP 0). 게이트 FAIL 판정과 비승격에 동의한다. accel_pred_raw와 e001 argmax의 일치율은 86%라 e004는 재학습된 모델이다. 향상분은 raw argmax가 +0.099, override 헤드가 +0.0075다. e004 raw 기준 oracle 상한은 0.4265다. e005 result에 3단 분해를 넣고, 비STOPPED accel이 e001보다 떨어지지 않았는지 보는 7번째 조건을 더하자고 제안했다(review ac218d17). 근거: work/s3_stopped_gate_e004/report.json, docs/STATUS.md

## 09-26 23:31 ~ 09-26 23:32 · `01a07e26b08d` · succeeded
- 깨운 이유: packet · 비용 $0.70 · 턴 12
- 요약: request 090ceceb(오늘 밤 마무리 후 두 PC 종료)에 맞춰 Pro를 종료할 수 있는 상태인지 점검했다. 실행 중·대기 중인 job은 0개이고 보내지 않은 결과도 없다(최근 발송 패킷은 모두 ack됨). pro/* 브랜치 6개는 모두 push되어 있고 main 작업 트리는 깨끗하다(88548d3). 디스크 여유는 24GB다. 새 장시간 작업은 시작하지 않았다. docs/STATUS.md에 '다음 재개 때 할 일'을 순서대로 적었다: S3 e005 → v002 diff → S23 e001 → S1 혼합 → 데이터 확장. 종료 준비 완료 qa e426fe15를 Ultra에 보냈다.
- 사람에게 요청: Pro는 지금 종료해도 된다. 실행 중인 job이 없다. agent_bridge 루프를 일시정지한 뒤 PC를 끄면 된다.

## 09-27 13:19 ~ 09-27 13:24 · `e75aaa035004` · succeeded
- 깨운 이유: packet · 비용 $1.69 · 턴 27
- 요약: decision fe3b9e1b는 2fbcd9ce로 대체됐다(승격은 6조건, 7번째 조건은 진단용). 둘 다 accept라 답신하지 않았다. S3 e005 result 91abe1ad를 독립 재계산했다. official 0.35116, STOPPED precision 0.993, recall 0.557, 다른 source FP 0이 모두 재현돼 PASS에 동의한다(review e0b15976). 다만 e005와 e001 모두 DEC를 예측하지 못하고, ACC 예측의 52%는 정답이 DEC다. 속도 맥락 지름길로 보여 LB S3 위험을 적었다. 제안은 e006 val_predictions에 4클래스 확률을 넣고 ACC-vs-DEC AUROC를 진단하는 것이다. 근거: work/s3_stopped_gate_e005/
- 사람에게 요청: Ultra가 보고한 v002 zip(work/submit_v002.zip, sha f2b158a8…)을 DACON에 업로드할지 판단한다. S3 e005는 proxy에서 향상됐지만 DEC를 한 번도 예측하지 않아 LB S3가 e001(0.4656)보다 낮아질 수 있다. 낮아지면 결정 10에 따라 e001로 되돌린다.

## 09-27 13:28 ~ 09-27 13:33 · `5f0782584917` · succeeded
- 깨운 이유: packet · 비용 $1.69 · 턴 39
- 요약: result 8a06d93a(S23 e001)를 독립 재계산해 review d999b155를 보냈다. split별 Macro-F1 0.333이 모두 재현됐고 무결성도 통과했다. 분리도는 없다(AUROC 0.513, 쌍 승률 0.52). 다만 평가 ORIGINAL은 1280x962·20fps·h264, 촬영본은 1920x1080·HEVC이고, 학습한 v1은 960x540·mp4v다. 그래서 형식 이탈과 판별력 부족을 가를 수 없다. 두 클래스를 1280x720·10fps·50프레임, 같은 인코더로 맞춘 쌍으로 다시 채점하자고 제안했다. 그 쌍을 만드는 job cdafe0a7f2de가 실행 중이다. 근거는 work/s23_e001_review/report.json이다.

## 09-27 13:37 ~ 09-27 13:41 · `0750de3923eb` · succeeded
- 깨운 이유: job_finished · 비용 $1.38 · 턴 28
- 요약: job cdafe0a7f2de(형식 맞춤 S23 쌍)가 성공했다. 192클립 QA를 통과했다: 모두 50프레임·1280x720·10fps이고 sha도 일치한다. 트랙별 fourcc는 하나씩이고, 시트로 시점이 맞는 것도 확인했다. 이 쌍을 qa 3ab82c65로 Ultra에 보내 트랙별 재채점을 요청했다. 같은 인코더인데도 촬영본 파일이 더 커서 크기 단서가 남는다(AUROC mp4v 0.84, x264 0.64). 그래서 x264 트랙을 우선 기준으로 하자고 적었다. 결과 검토 도구 s23_fm_review.py를 만들었고 셀프 테스트를 통과했다. 근거: work/s23_format_matched_qa/, docs/STATUS.md

## 09-27 14:41 ~ 09-27 14:46 · `379d884b1079` · succeeded
- 깨운 이유: packet · 비용 $1.57 · 턴 25
- 요약: decision 8111e544(형식 맞춤 S23 채택)와 c6903fd5(e006 ACC-vs-DEC AUROC 필수 진단, 21시 S3는 e005 유지)는 둘 다 accept라 답하지 않았다. 진단 도구 s3_accdec_auroc.py를 만들었고 셀프 테스트를 통과했다. 분석 결과 원인은 속도 지름길이 아니다. train에서 속도의 AUROC는 0.446이고, e005 raw 경판정은 0.288, 속도층화해도 0.267이다. 같은 속도 구간 안에서도 부호가 뒤집혀 있고, GT 부호는 정상이다. qa cc3a4dc1로 train 추론과 시간 반전 val 추론으로 원인을 가르자고 제안하고, 속도 균형 가중치도 첨부했다. 근거: work/s3_accdec_data/, docs/STATUS.md

## 09-27 14:47 ~ 09-27 15:01 · `0f9d8fb8cf4f` · succeeded
- 깨운 이유: packet · 비용 $1.41 · 턴 30
- 요약: result 62005ef1(S23 형식 맞춤 e001)을 독립 재계산해 review 3ffe9542를 보냈다. 첨부 지표는 모두 재현됐다(x264 val_test 0.375, mp4v 0.434, no_signal). 다만 본문의 x264 overall·validation·test 값은 잘못 옮겨졌다. 추가로, 224 입력 기준 고주파(HF)를 비교했더니 v1 합성 재촬영본은 원본의 0.55배다(HF 단독 AUROC 0.23, 역방향). 반면 S23 실촬영본은 원본의 2.5배다(HF 단독 AUROC 0.92). 제안은 HF 방향 게이트와 v1s 재렌더다. 근거: work/s1_hf_probe_e001/

## 09-27 15:02 ~ 09-27 15:16 · `e8c72a9435b5` · succeeded
- 깨운 이유: packet · 비용 $2.33 · 턴 45
- 요약: result de511b18(S3 e005 확률 진단)을 독립 재계산해 review 199182ff를 보냈다. 첨부 CSV 3개는 무결성을 통과했고 AUROC(train 0.983, val 0.195, 역전 0.217, source별 값)가 모두 재현됐다. job 9377615f5421로 video.hevc 23개를 다시 디코드했다. 흐름 확장 비율이 0.91~1.0이라 모든 split이 정방향 재생이다. 따라서 val 전역 역전은 배제했다. 다만 val의 ACC/DEC는 에피소드 17개뿐이다. 에피소드 AUROC는 0.26(95% CI 0.01~0.57, p=0.11)이라 '강한 부호 반전'은 통계적으로 약하다. 제안: 게이트 7을 에피소드 CI로 판정한다. LB S3는 0.5885(e005)다. 근거: work/s3_order_audit_e005/, work/s3_order_audit_lag/

## 09-27 15:17 ~ 09-27 15:34 · `60d4943debca` · succeeded
- 깨운 이유: job_finished, packet · 비용 $2.30 · 턴 45
- 요약: decision 9f59432f(v1s 승인)를 받아 v1s 재렌더 job e2c7decb79a9(24 source×4변형, 3프로세스)를 시작했다. 코드는 pro/s1-synth-v1s(ea301c1, push함)에 있다. 시험 3 source에서 224 HF SYN/ORIG 중앙값은 1.50, 6쌍 모두 SYN이 높았고 AUROC는 0.89로 게이트를 통과했다. result b00984f5(S2 e005 FAIL)는 재현됐다. 다만 v7 val 21개 중 16개가 e001 학습 영상이었다. 오염되지 않은 7개에서는 e001도 상수 수준(0.40/0.33)이다. 그래서 5-fold out-of-fold 평가를 제안하는 review bfb29738을 보냈다. 근거: work/s2_scene_gate_e005_review/, work/s1_v1s_trial/hf.json

## 09-27 15:36 ~ 09-27 15:38 · `97195c257bb3` · succeeded
- 깨운 이유: packet · 비용 $0.81 · 턴 14
- 요약: decision df308177(게이트 7을 에피소드 AUROC와 CI로 판정)은 accept라 답신하지 않았다. e006 검토용으로 work/pro_tools/s3_gate7.py를 만들었다. 이 도구는 행 AUROC, 에피소드 AUROC, bootstrap CI, 순열 p를 계산하고, 판정 규칙(hold/pass/fail)과 하드 게이트 여부까지 낸다. e005 val로 기준선을 재현했다: 에피소드 0.2639, 양측 p 0.1118, 판정 hold. 셀프 테스트도 통과했다. v1s job e2c7decb79a9는 실행 중이다(mp4 27/120개). 근거: work/s3_gate7_e005/gate7.json, docs/STATUS.md

## 09-27 15:39 ~ 09-27 15:41 · `a09e7b1bcd70` · succeeded
- 깨운 이유: packet · 비용 $0.96 · 턴 15
- 요약: decision 9bb29d60(S2 scene 게이트를 5-fold OOF로 전환)은 accept여서 답신하지 않았다. 항목 6에 쓸 독립 재계산 도구 work/pro_tools/s2_scene_oof.py를 만들었고, 셀프 테스트를 통과했다. 테스트 중 문제를 하나 발견했다. 기준을 상수 하한(회피 0.394, 방향 0.346)만으로 두면 무작위 예측(0.594/0.627)도 통과한다. 그래서 qa 33fd2744를 보내 순열 p<0.05 조건을 더하자고 제안했다. 이 조건이면 OOF Macro-F1이 약 0.63~0.65를 넘어야 통과한다. v1s job e2c7decb79a9은 아직 실행 중이다(mp4 40/120). 근거: work/s2_scene_oof_selftest/selftest.json, docs/STATUS.md

## 09-27 15:43 ~ 09-27 15:44 · `41e9994961a0` · succeeded
- 깨운 이유: packet · 비용 $0.59 · 턴 10
- 요약: decision 8c33234b(accept, 9bb29d60 대체)를 받았다. S2 scene 게이트는 4조건 AND로 확정됐다: CI 하한 > 상수 하한, 최빈 예측 비율 ≤ 0.9, 순열 p < 0.05, integrity. accept라서 답신하지 않았다. 독립 재계산 도구 work/pro_tools/s2_scene_oof.py의 판정에 integrity 조건을 넣었다(실패 시 integrity_fail). 0.15·F1 기여도 출력도 추가했다. 셀프 테스트 7개 check가 모두 통과했다(work/s2_scene_oof_selftest/selftest.json). v1s job e2c7decb79a9는 실행 중이다(mp4 52/120개, 약 07:05Z 완료 예상).

## 09-27 15:54 ~ 09-27 16:07 · `bdac73471393` · succeeded
- 깨운 이유: packet · 비용 $10.92 · 턴 87
- 요약: Nexar v2 request 8361901d·6badf0be(300개)를 받았다. 모두 parity_ok이고, 80개는 기존 v1 라벨 영상과 겹쳐 새 영상은 220개다. 220개 모두 triage 시트를 만들었고, 110개는 접촉 분류를 기록했다(yes 50, uncertain 54, no 6). 차선 진입 9개는 frame-labeler로 상세 라벨했다. 충돌−nexar 차이는 9개 중 7개가 ±9프레임 안이고, 00260과 00387만 벗어난다. qa 05788212로 병합본(324개, collision_valid 118)과 상태 CSV를 보냈다. v1s job e2c7decb79a9는 성공했지만 QA는 아직 못 했다. 근거: work/nexar_v2/, docs/STATUS.md

## 09-27 16:08 ~ 09-27 16:17 · `ef807a53aefb` · succeeded
- 깨운 이유: job_finished · 비용 $5.41 · 턴 14
- 요약: v1s job e2c7decb79a9는 QA를 통과했다(120클립, 300프레임, sha 일치, split이 v1과 같음). HF 게이트도 통과했다(SYN/ORIG 중앙값 1.54, AUROC 0.749). 결과는 qa 74d1a9e7로 보냈고 pro/s1-synth-v1s 병합을 요청했다. 크기 AUROC 1.0은 caveat로 적었다. 이전 보고와 달리 Nexar 남은 110개 triage 결과가 모두 도착했다(yes 25, no 34, uncertain 51). 결과는 work/nexar_v2/triage_results/group_10~19.json에 저장했지만 라벨 CSV에는 아직 기록하지 않았다. 다음 사이클에 record_triage로 기록한 뒤 상세 라벨을 이어서 한다.

## 09-27 16:19 ~ 09-27 16:22 · `351e24a462dc` · usage_limit
- 깨운 이유: packet · 비용 $3.07 · 턴 1
- 오류: You've hit your session limit · resets 6:10pm (Asia/Seoul)

## 09-27 18:29 ~ 09-27 18:40 · `e85ad7be76b5` · succeeded
- 깨운 이유: packet · 비용 $7.25 · 턴 83
- 요약: 패킷 5개를 처리했다. S2 scene CV(decision ab6a3c03): FAIL을 독립 재현했다. side 헤드는 찬스보다 유의하게 반전돼 있었다(AUROC 0.233, 순열 p=0.0006). 원인을 가를 대조 실험을 제안했다(review 1610e119). S1 e002: 수치는 모두 재현됐다. 실촬영 AUROC 0.621의 CI는 [0.49, 0.80]이고, 형식을 맞춘 쌍에서는 0.48~0.51이라 형식 차이 때문일 가능성이 있다. e003은 형식 맞춤 train split으로 학습하자고 제안했다(review 33ba8afc). Nexar 상세 라벨 20개를 추가해 qa dc2cf9f2로 v2 병합본을 보냈다(collision_valid 139, side 77). 남은 상세 대기열은 158개다. 근거: work/s2_scene_oof_e006cv/, work/s23_e002_review/, docs/STATUS.md

## 09-27 18:41 ~ 09-27 19:15 · `9ad0466d9530` · succeeded
- 깨운 이유: scheduled · 비용 $3.93 · 턴 73
- 요약: 결정 12의 A·D를 착수해 qa 2개를 보냈다. A: 창 안의 움직임만 보는 충돌 규칙 z(div_drop)+z(jerk_y), lag -2를 FIT에서만 골랐다. 무작위 위치 창 HELD 57개 영상에서 Acc@0.3초는 0.636(무작위 0.135)이다. 사람 라벨 10개에서는 0.375로 낮고, 급제동에 먼저 반응한다. qa 04a6895b와 e001 비교 request 056da1af를 보냈다(pro/s2-motion-rule f45bf27). D: 10Hz 흐름 특징의 ACC/DEC 판별은 방향은 맞지만 약하다. val 에피소드 AUROC 0.694, val+test 0.609로 게이트 7 hold다(e005 0.264). qa a3f4f990을 보냈다. 디스크 여유는 6.5GB로 기준(12GB)보다 낮다. 근거: work/s2_motion_rule_r1/, work/s3_motion_gate_r2/, docs/STATUS.md
- 사람에게 요청: Pro PC 디스크 여유가 6.5GB로 기준(12GB)보다 낮습니다. <USER_HOME>\AppData\Local\Temp(4.3GB)를 정리하거나, inbox와 중복된 C:\Dacon\AFDA_Exchange\ultra_to_pro의 Nexar 사본(4.6GB)을 지워도 되는지 확인해 주세요

## 09-27 19:16 ~ 09-27 19:33 · `1645e4c0d453` · succeeded
- 깨운 이유: packet · 비용 $2.30 · 턴 38
- 요약: 패킷 3개를 처리했다. decision 2개(1956a442, 2a7dae58)는 accept라 답신하지 않았고, request c6c16500은 정보성이다. 결정 12-C(S2 방향·회피 규칙)를 qa 20597985로 보냈다. 규칙 A와 같은 창과 split을 썼고 충돌 위치는 규칙 A 예측을 썼다. 회피(pre_mag≤1.72)는 HELD 32개 영상에서 0.697(CI 0.54~0.83, p 0.002)로 4조건을 통과했다. 사람 라벨 10개 정확도는 0.55다. 방향(잔차 가로 흐름 부호)은 HELD 0.641(p 0.021), 71개 전체 0.597(p 0.034)로 통과했다. 다만 사전 FIT 절차가 고른 diff_lr은 HELD에서 실패했고, obj_u는 HELD 특징표를 본 뒤 채택했으므로 새 라벨로 재검증해야 한다. 코드는 pro/s2-scene-rule d0f8f5c(테스트 3개 통과, 평가 예측과 556/556 일치)다. 근거: work/s2_scene_rule_r1/, docs/STATUS.md

## 09-27 19:34 ~ 09-27 19:57 · `7b09aa3eb6cd` · succeeded
- 깨운 이유: packet · 비용 $3.42 · 턴 62
- 요약: decision 1a07c3d2는 accept라 답신하지 않았다. S3 조향 규칙: 원경 가로 흐름(yaw_far)만으로 train에서 임계값을 정했다. 부호는 23개 source 모두 규약(양수 = LEFT)과 맞는다. val 조향 Macro-F1은 0.719(e005 0.324), test는 0.725다. e005 조향만 바꾸면 val S3가 0.351에서 0.470이 된다(Δ CI 0.05~0.17). 공식 예제 5개(참고 지표)에서는 0.495다. qa 2df80d3a로 보냈다(브랜치 pro/s3-yaw-steer 7dfcb67, 테스트 3개 통과). S2 방향 규칙은 쓰지 않은 영상 80개로 한 사전 등록 검정에서 실패했다(0.529, p 0.28). 그래서 side는 v001을 유지하자고 qa 4e7143af로 알렸다. 충돌 r2 탐색은 CV에서 r1보다 낮아 채택하지 않았다.

## 09-27 19:58 ~ 09-27 20:29 · `a125b110ab85` · succeeded
- 깨운 이유: packet · 비용 $2.34 · 턴 44
- 요약: 패킷 3개를 처리했다. decision 024d6e8a와 37c252d7에는 답신하지 않았다. result c60576a3(side 반전)에는 review 17e62e0b를 보냈다. 좌우 처리에는 오류가 없다(RIGHT=1 일관, flip 없음, 사람·에이전트 3/3 일치). 원인은 ResNet18 GAP 특징이 거의 좌우 대칭이라는 점이다. 선형 탐침에서도 반전이 재현되지만(LOVO 0.247) 셔플 200회 기준 p는 0.025~0.10으로 경계다. flip 증강을 넣으면 반전이 사라진다. 반대칭 탐침은 새 영상 80개 확인 검증에서 FAIL이다(AUROC 0.58, p 0.105). 제안은 부호를 뒤집지 않고 v001을 유지하는 것이다. 근거: work/s2_side_flip_audit/, work/s2_side_antisym_confirm/

## 09-27 20:30 ~ 09-27 20:41 · `e9106d48e0e8` · succeeded
- 깨운 이유: job_finished, packet · 비용 $2.71 · 턴 41
- 요약: decision 92483f83(S3 yaw 조향 수용)과 34d5f003(S2 충돌·진입 규칙 graft)은 accept라 답신하지 않았다. qa 55c7cdc5: 비공개 S3 입력은 10Hz이고 디코드 프레임 수가 sample_index 수와 같다. 그래서 yaw는 연속 프레임을 그대로 쓰고 컨테이너 fps(약 480)로 정규화하면 안 된다. yaw 흐름 계산은 1200프레임에 약 12초다. 가감속 속도 proxy 개선 시도 2건(지면 확대 탐색, 차체 pitch)은 실패해 e005를 유지한다. qa 6f778d85: 진입 후보 2(가로 움직임 시작)는 CV 0.546으로 충돌−8(0.577)보다 낮아 채택하지 않았다. 근거: work/s2_entry_onset_r1/, docs/STATUS.md

## 09-27 20:43 ~ 09-27 20:43 · `bef5ca242dd4` · succeeded
- 깨운 이유: packet · 비용 $0.62 · 턴 8
- 요약: decision 118eea8e는 side 반전 진단 review 17e62e0b를 수용했다. 독립 재현이 일치했고, side 부호를 뒤집지 않고 v001을 유지하기로 확정했다. Ultra는 result c60576a3의 implications 1을 철회했다. accept라 답신하지 않았다. v003에서 side를 다시 학습하려면 hflip+라벨 교환, 반대칭 추론, 사전 등록 확인 검증 p<0.05를 모두 갖춰야 한다(우선순위 낮음). 그 밖에 받은 것은 qa 2개의 ack뿐이다. 남은 Pro 작업은 Ultra의 e001 evasion·side 창 출력과 preflight·LB result를 기다리고 있다. 디스크 여유는 22GB다. 근거: docs/STATUS.md

## 09-27 20:46 ~ 09-27 20:58 · `4fec7572684f` · succeeded
- 깨운 이유: packet · 비용 $1.09 · 턴 17
- 요약: decision 3660bebadf(S3 yaw 조향 graft 25a7047)는 accept라 답신하지 않았다. 대신 graft를 독립 확인했다. 인라인 로직은 Pro 모듈과 같다(공개 예제 gray[::2]에서 50/50 일치, 0.495). 확인 중 qa 55c7cdc5의 설명 하나가 틀린 것을 찾았다. 공개 예제는 한 디코드 프레임이 한 10Hz 행이 아니라 20Hz 디코드다(frame_index=2·sample_index). 그래서 graft를 공개 예제에 그대로 돌리면 전부 STRAIGHT이고 Macro-F1은 0.289다. 비공개 입력이 공지대로 10Hz면 graft는 맞다. 정정 qa 23a9759a(supersedes 55c7cdc5)를 보냈고, graft는 유지하고 LB S3 프로브로 판정하자고 제안했다. 근거: work/s3_graft_check/

## 09-27 20:59 ~ 09-27 21:02 · `c409853d0e11` · succeeded
- 깨운 이유: packet · 비용 $0.88 · 턴 19
- 요약: decision 9f501859(12-B 진입 후보 2 reject, 진입=충돌−8 유지)와 d71aa7dd(12-C 회피 규칙 graft 048d261, accept)에는 답신하지 않았다. 9f501859는 우리 qa와 결론이 같다. 048d261을 독립 확인했다. 인라인 회피 규칙은 공개 예제 5개의 모든 c에서 모듈과 250/250 일치한다. 공개 예제 5개는 특징값이 0.53~1.57로 임계값 1.72보다 낮아 모두 class 1이다. 공개 예제에는 회피 정답이 없다. e001도 class 1이 98%라서, 예측이 한쪽으로 몰려도 e001과 비슷한 수준이다. 근거: work/s2_evasion_graft_check/, docs/STATUS.md

## 09-28 13:49 ~ 09-28 14:01 · `352b255b5be6` · succeeded
- 깨운 이유: scheduled · 비용 $2.70 · 턴 54
- 요약: 밤사이 받은 패킷은 없었다. main의 b589db7은 중간판 LB 결과(S2 0.2060→0.3056, 종합 약 0.471)로, 12-A 충돌 규칙이 리더보드에서도 이겼다. 새 작업으로 S3 STOPPED 움직임 규칙을 만들었다. div_far와 mag_all이 모두 작으면 STOPPED로 본다(train에서만 선택, yaw와 같은 흐름장이라 추가 흐름 계산 없음). 같은 val 행에서 e005에 OR로 붙이면 STOPPED F1 0.714→0.857, S3 0.470→0.496이다(블록 CI [0.007, 0.057], source CI는 0 포함). test 오탐은 0이다. qa cc49dc89와 pro/s3-stopped-flow accbb0c를 보냈다. 근거: work/s3_stopped_flow_r3/

## 09-28 14:26 ~ 09-28 14:32 · `495033cb3f49` · succeeded
- 깨운 이유: packet · 비용 $0.72 · 턴 11
- 요약: decision 0f9c82bb(S3 STOPPED 움직임 규칙 채택, graft b1eaa28)는 accept라 답신하지 않았다. graft를 독립 확인했다. 인라인 `_s3_motion_series`와 `_s3_stopped_mask`는 공개 예제 gray[::2]에서 Pro 참고 결과와 50/50 일치한다(TP 3, FP 1). 한 흐름장에서 뽑은 yaw 열로 만든 조향도 기존 `_s3_predict_steer`와 같다. Pro venv에서 S3 unittest 8개가 통과했다. 최종 판정은 2차 S3 단일 변경 LB 프로브로 한다. 근거는 work/s3_stopped_graft_check/와 docs/STATUS.md에 있다.

## 09-28 16:02 ~ 09-28 16:08 · `9359d6ffad41` · succeeded
- 깨운 이유: heartbeat · 비용 $0.88 · 턴 14
- 요약: heartbeat 사이클이다. 받은 패킷은 없었다. main의 새 커밋 72bcf5f(S3 Farneback 스레드 병렬화)를 독립 확인했다. 공개 예제 5개 모두에서 worker 8의 흐름 결과가 직렬 결과와 byte 단위로 같았다(np.array_equal 5/5, motion·yaw 둘 다). Pro CPU에서 영상당 흐름 시간은 약 26초에서 약 3.8초로 줄었다(약 6.9배). qa 439bf508을 보내 2차 제출에 써도 된다고 알리고, LB 실행 시간을 result에 적어 달라고 했다. 1차 프로브의 LB 점수는 아직 받지 못했다. 근거: work/s3_parallel_check/report.json, docs/STATUS.md

## 09-28 16:11 ~ 09-28 16:12 · `a1e47eee6c2e` · succeeded
- 깨운 이유: packet · 비용 $0.69 · 턴 10
- 요약: Ultra result 96fb7763에 review 83b0b0c6을 보냈다. 이 result는 72bcf5f 병렬화가 오프라인 3-Stage e2e를 통과했고(288초) 2차 keep zip이 ae22a715라는 내용이다. 판정은 integrity_pass true이고, 재계산할 지표가 없어 metrics_reproduced는 null이다. main inference에서 STOPPED 마스크는 같은 흐름 열을 쓰므로 흐름 계산이 늘지 않는다. 제안은 2차 zip을 keep zip에 STOPPED(b1eaa28)만 더한 S3 단일 변경으로 만들자는 것이다. 1차 LB의 Stage별 점수와 실행 시간(50분 34초)도 보내 달라고 했다. 근거: docs/STATUS.md, work/agent/outbox/review_96fb7763.json

## 09-28 16:22 ~ 09-28 16:25 · `2844f249d9c6` · succeeded
- 깨운 이유: packet · 비용 $1.02 · 턴 14
- 요약: decision 9b660eec는 review 83b0b0c6 수용이라 답신하지 않았다. 2차 zip은 e990d3e8(keep+STOPPED)이다. 동봉된 probe1 LB를 공식 식으로 다시 계산했더니 종합 0.4570으로 같았다. S1 −0.068, S2 −0.0015(회피 F1 약 −0.01), S3 +0.0012였다. yaw는 val +0.40이었으나 LB 조향은 약 +0.004로 거의 옮겨 가지 않았다. 같은 흐름장을 쓰는 STOPPED 규칙은 흐름 크기가 0.33~1.25배로 바뀌어도 val S3가 +0.019~+0.026으로 유지된다. qa df3b44b3을 보내 2차 계획을 지지했다. 근거: work/s3_stopped_scale/
- 사람에게 요청: 21~22시 2차 제출: Ultra의 work/submit_v002_s2rule_s3yawstopped_par.zip(sha256 e990d3e8…)을 DACON에 업로드하고, Stage별 점수와 실행 시간을 Ultra에 전달

## 09-28 16:27 ~ 09-28 16:27 · `cdc7495093c6` · succeeded
- 깨운 이유: packet · 비용 $0.51 · 턴 7
- 요약: decision bc91a099는 qa df3b44b3을 수용한다는 accept라서 답신하지 않았다. 확정 사항은 세 가지다. 2차 제출(21~22시)은 e990d3e8(keep 조합에 STOPPED 추가)이다. LB S3가 0.5897보다 낮으면 9/29 오전에 STOPPED만 뺀 keep zip(ae22a715)으로 되돌린다. STOPPED가 유지되거나 오르면 그 조합을 최종 후보로 하고 1회는 오류 대응용으로 남긴다. 새로 보낸 패킷은 없다. docs/STATUS.md를 갱신했고 main checkout은 깨끗하다.

## 09-28 16:43 ~ 09-28 16:54 · `3707f7ef870e` · succeeded
- 깨운 이유: scheduled · 비용 $1.22 · 턴 27
- 요약: 운영자 요청을 처리했다. 병렬화 전 main 72bcf5f의 inference 사본으로 S2 규칙 기준 출력을 저장했다(공개 예제 5개와 Nexar 10Hz 창 60개, 두 번 실행해 같은 결과). 그 뒤 Ultra 커밋 5b6887a(S2 디코드·Farneback 병렬화)가 main에 들어와 같은 폴더에서 비교했다. gray·collision·entry·프레임 번호·evasion·div/dy/score가 65/65 byte 단위로 같았다. Pro 시간은 읽기 49초→8.1초, 흐름 25초→4.6초이고, S2 unittest 5개가 통과했다. qa 9e469e43을 보냈다. 근거: work/s2_parallel_check/, docs/STATUS.md

## 09-28 17:00 ~ 09-28 17:01 · `27f38444f60f` · succeeded
- 깨운 이유: packet · 비용 $0.57 · 턴 6
- 요약: Ultra result 171d1f26에 review 7897f57e를 보냈다. 이 result는 Pro qa 9e469e43을 수용했고, 2차 후보를 5b6887a로 다시 만든 90f86223(keep+STOPPED+S2 병렬)이라고 밝혔다. 판정은 integrity_pass true이고, 재계산할 지표가 없어 metrics_reproduced는 null이다. S2 병렬화는 출력이 byte 단위로 같아서 2차에서 바뀌는 Stage 출력은 S3 STOPPED 하나다. zip은 Pro에 없어서 직접 확인하지 못했다. 제안은 9/29 되돌림 대상을 ae22a715에서 e767d310으로 바꿔 기록하자는 것이다. 근거: docs/STATUS.md, work/agent/outbox/review_171d1f26.json
- 사람에게 요청: 2차 제출(21~22시)로 work/submit_v002_s2rule_s3yawstopped_s2par.zip(sha 90f86223, Ultra PC)을 DACON에 업로드하기

## 09-28 17:07 ~ 09-28 17:08 · `bac7fb620890` · succeeded
- 깨운 이유: packet · 비용 $0.49 · 턴 7
- 요약: decision 75d9e17c는 review 7897f57e를 수용한 accept 결정이라 답신하지 않았다. 확정 사항: 9/29 되돌림 기준 zip이 ae22a715에서 e767d310(5b6887a 기반 keep 조합에 S2 병렬화를 더하고 STOPPED를 뺀 것)으로 바뀌었다. 2차 제출 zip은 90f86223(keep 조합에 STOPPED와 S2 병렬화 추가), 최고 점수 폴백은 41ec5395다. 새로 보낸 패킷은 없다. docs/STATUS.md를 갱신했고 main checkout은 깨끗하다. 2차 LB 결과가 오면 공식 식으로 STOPPED 효과를 다시 계산한다.

## 09-28 18:38 ~ 09-28 18:39 · `964e9fb8615d` · succeeded
- 깨운 이유: heartbeat · 비용 $0.59 · 턴 5
- 요약: heartbeat 사이클이다. 받은 패킷, 미처리 job, 미확인 발송 패킷이 모두 없었다. main에 Ultra 커밋 db24e6a(S1 e003, 형식 맞춤 실촬영 train split)가 들어왔지만 관련 result는 아직 없다. 2차 제출(90f86223, 21~22시)의 LB result를 기다린다. result가 오면 공식 식으로 STOPPED 단독 효과를 다시 계산한다(기준 probe1 S3 0.5897). 이번에는 새 패킷을 보내지 않았다. docs/STATUS.md를 갱신했고 main checkout은 깨끗하다.

## 09-28 18:45 ~ 09-28 18:48 · `1ecace19a035` · succeeded
- 깨운 이유: packet · 비용 $0.99 · 턴 18
- 요약: result 27809272(S1 e003)에 review 15afc64c를 보냈다. 판정은 integrity_pass와 metrics_reproduced 모두 true다. Pro 도구로 형식 맞춤 S23 게이트를 다시 채점했더니 x264·mp4v의 val/test가 모두 Macro-F1·AUROC 1.0으로 Ultra 값과 같았다. 합성 4종과 S23 train에는 S23 val/test의 source·origin_group이 없어 누수도 없다. 다만 같은 촬영 세팅의 source 8개뿐이라 LB에서도 같은 성능이 나온다고 보장할 수 없다. 제안: 2차 LB의 S3가 0.5897 이상이면 3차 zip을 90f86223 기반으로 다시 만들자. 근거는 work/s1_e003_review/, docs/STATUS.md다.

## 09-28 18:50 ~ 09-28 18:51 · `b3c90ee15396` · succeeded
- 깨운 이유: packet · 비용 $0.51 · 턴 6
- 요약: decision 671d9c12는 review 15afc64c를 수용한 accept 결정이라 답신하지 않았다. 2차 LB(90f86223)의 S3는 0.5892로 probe1의 0.5897보다 0.0005 낮다. 그래서 STOPPED를 되돌리기로 확정했다. val에서 얻은 이득은 비공개 평가로 이어지지 않았고, 이번 차이는 잡음 수준이다. 전제가 맞지 않아 조건부 재빌드는 하지 않는다. 3차 최종 후보는 49496bbd(e767d310에서 S1만 e003으로 바꾼 zip)이고, 폴백은 e767d310이다. 3차 LB의 S1이 0.565보다 낮으면 9/29 오전에 e001로 되돌린다. 새로 보낸 패킷은 없다. docs/STATUS.md를 갱신했고 main checkout은 깨끗하다.

## 09-28 19:52 ~ 09-28 20:04 · `635c7157ede2` · succeeded
- 깨운 이유: scheduled · 비용 $2.77 · 턴 50
- 요약: 결정 13에 따라 9/28 LB 결과 5건으로 로컬 게이트를 역검증했다. LB 방향을 맞힌 게이트는 S2 시점 HELD 창 하나뿐이다. 이 게이트만 공식 정의와 같은 정답(실제 접촉)을 쓴다. 틀린 4건은 모두 우리가 정의한 라벨로 쟀다. S3 후보는 yaw 조향 T_LO를 −0.303에서 −0.198로 대칭화하는 상수 1개 변경이다. 공식 47행 조향 F1은 0.495에서 0.610으로 오르지만, 바뀌는 행이 1개뿐이라 근거가 얇다. comma val은 +0.023, test는 −0.017이다. S1은 게이트가 없어 e001을 유지한다. qa 4aaeee72를 보냈다. 근거: work/s3_open_steer_def/

## 09-28 20:05 ~ 09-28 20:19 · `963713d62967` · succeeded
- 깨운 이유: packet · 비용 $2.01 · 턴 33
- 요약: request 4362cffd(S3 가감속 움직임 특징 게이트7)에 qa a06d48f0으로 답했다. 추론과 같은 흐름 채널에서 train LOGO로 div_far_lr30을 골랐다. 고정 val 에피소드 AUROC는 0.736이지만 CI가 0.43~0.97이라 게이트7을 통과하지 못했다(hold). test는 0.398로 반대 방향이다. 23개 source 중첩 LOGO는 0.629(CI 0.525~0.728)로 신호가 약하다. e005는 val에서 DEC를 한 번도 예측하지 않는다. 규칙을 더하면 val accel F1이 0.363에서 0.511로 오르지만, test에서 규칙만 쓰면 0.301로 모두 CONSTANT로 찍는 0.274와 비슷하다. 제안은 S3 e767d310 유지와 GPU 학습 생략이다. 근거는 work/s3_motion_gate_r3/에 있다.

## 09-28 20:20 ~ 09-28 20:21 · `8fba0690ac7c` · succeeded
- 깨운 이유: packet · 비용 $0.68 · 턴 9
- 요약: decision a0cf3ce7(qa 4aaeee72 처리)를 받았고 답신하지 않았다. 게이트 역검증, S1 e001 유지, S2 시점 규칙 유지는 수용됐다. S3 조향 대칭화(T_LO=-T_HI)만 00:00 zip에서 빠지고 오전 조건부 프로브 s3-symyaw로 등록됐다(채택 조건 LB S3>0.5897). 00:00 zip은 e767d310 그대로다. 공개 행 중 바뀌는 행이 1개뿐이고 comma test가 0.725에서 0.708로 떨어진다는 근거가 타당해 반박하지 않았다. 가감속 움직임 특징은 이미 qa a06d48f0에서 hold였다. 그래서 오전 S3 실질 후보는 symyaw뿐이다. docs/STATUS.md를 갱신했고 main은 깨끗하다.

## 09-28 20:23 ~ 09-28 20:28 · `a5bb4d9db15c` · succeeded
- 깨운 이유: packet · 비용 $1.24 · 턴 23
- 요약: decision 3dcccfb3은 accept라 답신하지 않았다. 등록된 오전 프로브 s3-accel-rule3는 decision에 '통합비용 0'으로 적혀 있지만 실제로는 그렇지 않다. 임계값이 원값 div_far가 아니라 lr30(평활 후 ±30행 log 비)에 맞춘 값이기 때문이다. 원값에 같은 임계값을 쓰면 공개 행의 87%가 ACCELERATING이 되고 3클래스 F1이 0.515에서 0.097로 떨어진다. 그래서 numpy 참조 구현을 만들었다. Pro 도구와 비교하면 comma 23개 source에서 차이가 8.9e-16, 공개 5개에서 0이다. qa aba4ee31로 참조 코드와 공개 50행 기대값을 보냈다. 근거: work/s3_accel_rule3_ref/

## 09-28 20:30 ~ 09-28 20:31 · `7a440e7229c6` · succeeded
- 깨운 이유: packet · 비용 $0.51 · 턴 5
- 요약: decision 67463d90은 qa aba4ee31을 수용한 accept 결정이라 답신하지 않았다. Ultra가 s3-accel-rule3 정의를 정정했다. 임계값은 원값 div_far가 아니라 lr30(평활 후 ±30행 log 비)에 적용하고, 비공개 입력은 10Hz 그대로 쓴다. 00:00 제출 zip은 e767d310 그대로다. 프로브 선행 조건도 바뀌지 않았다: LB S3가 0.5897 이상이고, e005의 공개 50행 점수가 0.579보다 낮아야 한다. 이번 사이클에는 새 작업이나 패킷이 없고, docs/STATUS.md만 갱신했다. main checkout은 깨끗하다.

## 09-28 20:41 ~ 09-28 20:52 · `628a2c2b9ccf` · succeeded
- 깨운 이유: scheduled · 비용 $2.32 · 턴 39
- 요약: 운영 지시를 STATUS 맨 위에 적었다. rule3 graft 대조 도구 s3_rule3_graft_check.py를 만들었고, 자체 테스트에서 정상 graft는 MATCH, 임계값을 바꾸면 CHECK가 나왔다. S2 진입 오프셋은 k 선택 절차의 중첩 CV가 0.410으로, k=8 고정(0.4225)을 이기지 못해 새 후보가 아니다(human 20창·agent 167창). S3 DEC-only 변형은 val 0.451로 rule3(0.511)보다 약해 권하지 않는다. S2 방향·회피와 S1은 공식 정의 정답 게이트가 없어 새 후보가 없다. qa f084666d를 보냈다. 근거: work/s2_entry_k_cv/, work/s3_rule3_graft_check_selftest/

## 09-28 20:53 ~ 09-29 13:24 · `d6e808f271e6` · interrupted_by_loop_restart
- 깨운 이유: scheduled · 비용 $0.00 · 턴 -

## 09-29 14:28 ~ 09-29 14:29 · `36b12341ae21` · succeeded
- 깨운 이유: scheduled · 비용 $0.81 · 턴 12
- 요약: 마감(9/29 10:00 KST)이 4.5시간 지나 이번 사이클에서는 새 작업을 만들지 않았다. Pro는 9/28 20:56부터 일시정지였다. 예약 사유인 결정 13 0-1((a) S1 공식 형식 쌍 23:30, (b) S2 자막 점검 01:00)은 기한과 제출 창이 모두 지나 쓸 곳이 없다. 받은 패킷, 미처리 패킷, job은 없다. Ultra의 마지막 패킷은 9/28 20:51이고 최종 LB 결과는 아직 받지 않았다. 9/28 시험본 work/s1_nexar_fmt_trial/(22MB)은 QA하지 않은 상태로 둔다. docs/STATUS.md를 갱신했고 main은 깨끗하다.
- 사람에게 요청: 대회 이후 분석이 필요하면 9/29 00:00·오전 제출의 LB Stage별 점수를 Ultra result로 보내 주세요. 받으면 Pro가 공식 식으로 다시 계산합니다. / 더 할 작업이 없으면 Pro 루프를 멈춰 주세요(python -m agent_bridge pause).
