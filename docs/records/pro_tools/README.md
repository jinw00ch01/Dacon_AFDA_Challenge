# Pro 분석 도구(work/pro_tools)

> Pro 360(CPU 노트북)의 로컬 기록을 GitHub용으로 옮긴 것이다. 사용자 경로·장치 이름·계정 같은 개인 정보는 `<USER_HOME>`, `<pro-host>`, `<email>` 등으로 가렸다. 대회 원본·영상·가중치·토큰은 넣지 않았다.

Pro가 Ultra 결과를 독립 재계산·검증하려고 만든 1회용 분석 스크립트다. main의 제출 코드와는 별개다. 로컬 경로를 전제로 해서 그대로는 실행되지 않을 수 있다.

| 파일 | 첫 설명 줄 |
|---|---|
| `add_labels.py` | Feed frame-labeler JSON decisions (a JSON list file) into scripts/stage2_agent_label.py add. |
| `assemble_cycle_6b0e.py` | Collect attachments for the S23 batch-1 and S2 labels v7 qa packets and print summaries. |
| `crop_sheet.py` |  |
| `label_stats.py` | Summarize a merged Stage 2 CSV: contact / confidence distribution for agent rows, by source_label. |
| `make_negative_labels.py` | Write a JSON list of actual_contact=no decisions for the Nexar negatives (source_label=negative). |
| `nexar_v2_meta.py` | Build expansion meta CSV (stage2_agent_label.py --meta format) for Nexar v2 640px handoff batches. |
| `nexar_v2_pending.py` | List detail-queue videos without a detail result, in priority order. |
| `nexar_v2_qa_pack.py` | Merge Stage 2 labels with the Nexar v2 meta and write a qa attachment folder + summary JSON. |
| `nexar_v2_record_detail.py` | Record frame-labeler JSON decisions (work/nexar_v2/detail_results/<id>.json) as agent rows. |
| `nexar_v2_record_triage.py` | Record triage decisions as agent rows (append-only) and build the detail queue. |
| `nexar_v2_triage_sheets.py` | Render one triage sheet per new Nexar v2 video: event-116 .. event+29, step 5 (30 tiles, 213px). |
| `official_metrics.py` | Pro-side independent implementation of the official AFDA scoring (CLAUDE.md decision 10). |
| `patch_cm.py` | One-off: add the codec-matched mode to scripts/s1_synth_digital.py in the given checkout. |
| `patch_cm_tests.py` | One-off: add codec-matched helper tests to tests/test_s1_synth_digital.py in the given checkout. |
| `patch_job_run_argv.py` | One-off: fix agent_bridge job wrapper argv (--config must precede the job-run subcommand) in a worktree. |
| `phasecorr_sign_test.py` | Check cv2.phaseCorrelate sign: move image content RIGHT by 7 px and print the returned dx. |
| `s1_baseline_pairs.py` | Compare the paired Baseline stage1 examples (original/00000k vs rerecorded/00000k): |
| `s1_cm_probe.py` |  |
| `s1_e002_extra.py` | S1 e002 추가 진단: 실촬영 S23 val+test 합산 AUROC, 클래스별 prob 분위수, source 단위 bootstrap 95% CI. |
| `s1_e003_review.py` | Review result 27809272 (S1 e003): rescore the format-matched S23 predictions for e001/e002/e003 |
| `s1_hf_at_224.py` | How much of the Baseline rerecord cue (fine-grain noise) survives the S1 model |
| `s1_hf_params.py` | v1 합성 HF 비율(SYN/ORIG @224)과 생성 파라미터의 순위상관. |
| `s1_hf_probe.py` | S1 고주파(HF) 에너지 탐침: e001이 '흐림=RERECORDED'를 배웠는지 확인한다. |
| `s1_hf_probe_v1c.py` | v1c 계열 HF 비율과 S23 HF 단독 AUROC (s1_hf_probe.py 보조). |
| `s1_hf_v1s_check.py` | v1s HF 방향 게이트 확인: manifest 기반으로 224 Laplacian HF의 SYN/ORIG 비율, HF 단독 AUROC(RERECORDED=양성)를 낸다. |
| `s1_mixed_review.py` | Pro review of an Ultra S1 result trained on v1 (optical) + v1c (digital) synthetic recapture. |
| `s1_nexar_fmt.py` | S1 official-format pairs from Nexar (CLAUDE.md decision 13, 9/28 20:55). |
| `s1_nexar_fmt_inventory.py` | Inventory of Nexar clips available on Pro for the S1 official-format pairs (decision 13). |
| `s1_probe.py` | ffprobe stream/encoder info for S1 videos (read-only). usage: s1_probe.py <mp4>... |
| `s1_qa.py` | QA for an S1 synthetic recapture folder: count, duplicates, SHA-256, decode, size, split consistency. |
| `s1_qa_cm.py` | QA for the S1 v1c codec-matched set (ORIGX + DIGM0 per window) against its r2 base. |
| `s1_review.py` | Pro review of Ultra S1 e001: recompute metrics from val_predictions.csv, |
| `s1_synth_recapture.py` | Synthetic screen re-capture (S1) from comma s1_playback clips. CPU only, OpenCV only. |
| `s1_v1c_calib.py` | Calibrate a 'digital re-record' S1 variant (v1c) against the official Baseline pairs. |
| `s1_v1c_calib2.py` | v1c calibration with the official example pipeline: ORIG = OpenCV mp4v (MPEG-4 Simple, |
| `s1_v1c_sigma_curve.py` | HF ratio vs grain sigma for one v1c ORIG clip (debug calibration). Usage: <orig.mp4> [sigmas...] |
| `s1_v1c_trial_check.py` | Compare v1c trial pairs (ORIG vs DIG) with the Baseline stage1 pair statistics. |
| `s1_v1s_parallel.py` | v1s 렌더 병렬 드라이버: source를 N개 프로세스로 나눠 같은 out 폴더에 렌더하고 manifest를 source 순으로 합친다. |
| `s23_align.py` | S23 capture <-> playback-original alignment table + visual check sheets (Pro, read-only inputs). |
| `s23_align_thumb.py` | Cross-check S23 lag with 10Hz grayscale thumbnails (edge-based) instead of mean luma. usage: s23_align_thumb.py FILE... |
| `s23_e001_review.py` | Pro review of Ultra result 8a06d93a (S23 codec-aligned S1 eval, model e001). |
| `s23_eval_review.py` | Pro review of an Ultra S1 result scored on the S23 real re-capture release (s1-s23-real-v1-20260926). |
| `s23_fm_review.py` | Review an S1 prediction CSV on the format-matched S23 pairs (data/derived/s1_s23_format_matched_v1). |
| `s23_format_matched.py` | Format-matched S23 pairs: both classes in the official S1 clip shape, same encoder per track. |
| `s23_format_matched_qa.py` | QA for data/derived/s1_s23_format_matched_v1: manifest vs files, decoded frames/size/fps/fourcc, |
| `s23_identity_sheet.py` | Visual identity check for S23 captures flagged by s23_qa.py (weak/better match). |
| `s23_offset_compare.py` | Compare capture frames with original at several candidate offsets. usage: s23_offset_compare.py FILE OUT.jpg OFF1 OFF2 . |
| `s23_qa.py` | S23 real-recapture QA (Pro, read-only on data/captures/s23). |
| `s2_const_acc03.py` | S2 constant-position baseline under the official Acc@0.3s metric (CLAUDE.md decision 10, Pro 1-1). |
| `s2_e004_gate_prep.py` | Prep for the S2 e004 falsification gate (decision a41f4f79): how the val-window placement rule decides |
| `s2_entry_onset.py` | Decision 12-B candidate 2: entry frame = onset of the cutting-in car's lateral motion before the rule-A collision. |
| `s2_gate_clean_subset.py` | 게이트 배열을 영상에 매핑(cache manifest 순서 = v7 라벨 CSV 행 순서)하고, e001 학습 split(v6)에 있던 영상을 뺀 비오염 부분집합으로 재계산. |
| `s2_human_vs_agent.py` | Compare human `reviewed` S2 rows against the latest agent label per video (read-only). |
| `s2_merge_regress.py` | Regression: new stage2_agent_label.merge (staging copy) on real data vs existing v6 merged CSV. |
| `s2_motion_cache.py` | Decision 12-A: cache low-res grayscale frames around the labelled collision for the S2 motion rule. |
| `s2_motion_per_video.py` | Per-video summary of the S2 motion rule windows. Usage: s2_motion_per_video.py <windows_pair.csv> <out.csv> |
| `s2_motion_rule.py` | Decision 12-A: S2 collision-time rule from global motion, evaluated on official-format random windows. |
| `s2_motion_rule_pairs.py` | Decision 12-A follow-up: pairwise sums of per-window z-scored motion scores (FIT-selected), from r1 series.npz. |
| `s2_motion_rule_r2.py` | Decision 12-A r2: richer score families from r1 series.npz (same windows/splits), FIT-only selection. |
| `s2_parallel_check.py` | Operator request (cycle 3707f7ef870e): freeze main 72bcf5f S2 rule outputs, later compare Ultra's parallel S2 frame read |
| `s2_review.py` | Pro review of an Ultra S2 result: recompute metrics from val_predictions.csv, |
| `s2_review_e002.py` | Pro review of S2 e002: reproduce Ultra's const_baseline (train-median absolute |
| `s2_review_e003.py` | Pro review of S2 e003 (10Hz resample + 50-frame windows). |
| `s2_review_v001b.py` | Independent review of v001b (result 4f4c9dfc): const collision=30 / entry=22 on 50-frame 10Hz clips. |
| `s2_scene_flow.py` | Decision 12-C step 1: pooled optical-flow grids for the official-format windows of rule A (windows_pair.csv). |
| `s2_scene_gate_review.py` | S2 scene 게이트 result 독립 재계산: 첨부 true/pred 배열로 Macro-F1·acc, 1건 뒤집기 민감도, v7 val 라벨 출처 수. |
| `s2_scene_oof.py` | S2 scene 헤드 5-fold out-of-fold 독립 재계산 (decision 9bb29d60 항목 6). |
| `s2_scene_oof_diag.py` | S2 scene OOF 진단: 헤드별 fold 내 AUROC, fold별 정답/예측 비율, 반전 예측 F1, AUROC 순열 p. |
| `s2_scene_rule.py` | Decision 12-C: S2 entry-side and evasion-space rules from motion, gated on HELD with decision 8c33234b. |
| `s2_scene_rule_diag.py` | Decision 12-C diagnostic: per-feature window AUROC on FIT and HELD (both anchors) from s2_scene_rule features.csv. |
| `s2_scene_rule_equiv.py` | Check afda.s2_scene_rule (branch module) against the evaluation features.csv on all windows (pred anchor). |
| `s2_scene_rule_fixed.py` | Decision 12-C: gate for fixed (a-priori) rules on features.csv. Side: obj_u_L{L} > 0 -> LEFT (victim moves right on |
| `s2_scene_rule_pack.py` | Pack decision 12-C qa attachments: per-window predictions of the adopted rules + evaluation reports. |
| `s2_side_antisym_confirm.py` | Pre-registered confirm test of the flip-antisymmetric side probe (s2_side_flip_audit). |
| `s2_side_confirm.py` | Decision 12-C follow-up: confirmatory test of the FROZEN side rule (afda.s2_scene_rule, obj_u_L10 > 0 -> LEFT) |
| `s2_side_flip_audit.py` | S2 side left/right audit (result c60576a3 requests_to_pro #2). |
| `s2_side_flip_null.py` | Null distributions for s2_side_flip_audit probes (label shuffle), LOVO and 5-fold. |
| `s2_split_shift.py` | v6(e001 학습) vs v7(e005·게이트 val) split 재현: cache_s2_features.assign_splits와 같은 로직(seed 0, val_frac 0.2). |
| `s3_accdec_auroc.py` | S3 ACC-vs-DEC speed-shortcut diagnostic (decision c6903fd5: e006 mandatory diagnostic + gate 7). |
| `s3_accel_rule3_ref.py` | Graft reference for registered probe s3-accel-rule3 (decision 3dcccfb3). |
| `s3_class_rules.py` | S3 proxy class-rule candidates from s3_auxiliary_10hz.csv (train split only, SRC014 excluded). |
| `s3_confusion.py` | Confusion matrices, per-source breakdown and trivial-prior references for an S3 val_predictions.csv. |
| `s3_e005_decomp.py` | S3 e005 3-stage decomposition (decision fe3b9e1b / 2fbcd9ce): (a) e001 base, (b) e005 raw argmax, (c) e005 override. |
| `s3_e005_lagcorr.py` | e005 val: lag cross-correlation of score (p_ACC - p_DEC) with aux accel proxy / speed, and episode-level AUROC. |
| `s3_flow_probe.py` | Probe flow settings for a monotone speed proxy at 10 Hz (decision 12-D). usage: s3_flow_probe.py SRC... |
| `s3_gate7.py` | S3 gate 7 (ACC-vs-DEC) ruling per decision df308177: row AUROC + episode AUROC with bootstrap CI and perm p. |
| `s3_graft_check.py` | Pro check: grafted submission/inference.py (25a7047) steer path vs Pro equiv_open.csv on Baseline S3 OPEN examples (refe |
| `s3_graft_check2.py` | Variants of grafted steer on OPEN examples: all frames (graft as-is) / frames[::2] / all frames but row k->pred[2k]. |
| `s3_ground_speed.py` | S3 speed proxy v2 (Pro, decision 1a07c3d2 request "speed proxy improvement"): ground-plane zoom search. |
| `s3_helper_check.py` | Independent CPU check of origin/main 21da08c stage3_labels.accel_from_speed_series / |
| `s3_motion_accel_open.py` | Reference only: div_far_lr30 (r3 selected, train-fixed thresholds) on the 5 public S3 examples' official labels. |
| `s3_motion_accel_rule.py` | What div_far_lr30 (r3 selected feature) would do to accel Macro-F1 if used as a 3-way rule on e005 non-STOPPED rows. |
| `s3_motion_features.py` | Decision 12-D: 10 Hz motion features for S3 from low-res optical flow (comma2k19 subset). |
| `s3_motion_gate.py` | Decision 12-D: ACC-vs-DEC discrimination from motion features only (train-fit, val judged by gate 7). |
| `s3_motion_gate_r3.py` | Ultra request 4362cffd (decision 13 / 12-D): ACC-vs-DEC from INFERENCE-IDENTICAL motion channels only, gate 7. |
| `s3_motion_gate_r3_nested.py` | Nested leave-one-origin_group-out over ALL 23 comma sources (single-feature candidates from r3). |
| `s3_motion_select.py` | Decision 12-D: train-only feature selection by per-source robustness (median of per-train-source AUROC), |
| `s3_open_steer_def.py` | S3 steer definition probe on the official public examples (decision 13 gate back-validation). |
| `s3_order_audit.py` | S3 e005 prob review + model-free frame/label order audit (result de511b18 requests). |
| `s3_parallel_check.py` | Check main 72bcf5f: threaded _s3_motion_series/_s3_yaw_series == serial (workers=1), and timing on Pro CPU. |
| `s3_pitch_eval.py` | Correlate integrated pitch signals (high-passed) with the accel proxy, per source. Usage: s3_pitch_eval.py <pitch.csv> |
| `s3_pitch_probe.py` | S3 accel from body pitch (Pro probe). Braking dips the nose, accelerating lifts it; the camera is fixed to the body, |
| `s3_review.py` | Recompute Stage 3 validation metrics from a per-sample predictions CSV (Pro review tool). |
| `s3_review_e002.py` | Pro review of S3 e002 (result 182256b5, exp-7a701d04). CPU only, no val_predictions attached. |
| `s3_review_selftest.py` | Self-test for s3_review.py: oracle / majority / stopped-straight-only predictions on validation. |
| `s3_rule3_graft_check.py` | Check an Ultra rule3 graft (s3-accel-rule3) against the Pro reference. |
| `s3_shift_probe.py` | Probe: does shifting e005/e001 accel predictions in time (within source) change official S3? (alignment check) |
| `s3_speed_rule_check.py` | Pre-check for S3 e002 (speed_mps regression -> v1b rule), Pro-side, CPU only. |
| `s3_steer_sign.py` | Check the sign convention of steering_angle_deg in s3_auxiliary_10hz.csv against the comma video. |
| `s3_stopped_ceiling.py` | Ceiling / sensitivity of a STOPPED override on the e001 argmax base (decision cfafb2ad, e004 base = e001). |
| `s3_stopped_flow.py` | S3 STOPPED from image motion (flow magnitude), fit on TRAIN only; evaluate on val/test and OR-combined with e005. |
| `s3_stopped_flow_and.py` | Conjunction STOPPED rule: div_far_s15 <= a AND <guard>_s<w> <= b, both chosen on TRAIN only (max train F1). |
| `s3_stopped_flow_equiv.py` | Module equivalence: src/afda/s3_stopped_flow.py (worktree) vs evaluation features / rule predictions on given sources. |
| `s3_stopped_flow_fp.py` | False-positive / false-negative anatomy of the train-selected flow STOPPED rule (div_far smoothed w, thr). |
| `s3_stopped_flow_open.py` | Reference only: conjunction STOPPED rule on the 5 public S3 examples (20 Hz decode -> gray[::2] = 10 Hz rows). |
| `s3_stopped_gate.py` | S3 e004 gate check (decision 4fb9418c): binary STOPPED head on top of a base accel predictor. |
| `s3_stopped_graft_check.py` | Check main b1eaa28 inline STOPPED graft vs Pro open_examples.csv (reference, gray[::2] 10 Hz rows). |
| `s3_stopped_scale.py` | STOPPED rule sensitivity to flow-magnitude scale (FOV/resolution/frame-rate shift). |
| `s3_vstop_calib.py` | STOPPED threshold calibration for a speed-regression S3 head (proposal in review ae25318b). |
| `s3_vstop_e002_check.py` | Consistency checks before LOSO: e002 val_predictions vs Pro's v1b recomputation. |
| `s3_vstop_e002_diag.py` | Diagnostic: does e002 speed_pred carry STOPPED signal at all? AUROC + extended-grid LOSO (0.5..25 m/s). |
| `s3_yaw_equiv_open.py` | (1) module afda.s3_yaw_steer vs features.csv yaw_far on 2 comma sources; (2) reference metric on Baseline S3 OPEN exampl |
| `s3_yaw_sign.py` | Ultra request (decision 1a07c3d2): check the sign of the image yaw proxy against comma steering. |
| `s3_yaw_steer_rule.py` | S3 steering from the image yaw proxy alone (Pro, follow-up to decision 1a07c3d2 request). |
| `s3_yaw_vs_e005.py` | Join yaw steer rule predictions with e005 val predictions (result 91abe1ad); official S3 with steer swapped. |
| `shift_01037.py` |  |
| `track_01037.py` |  |
