"""S2 scene 헤드 5-fold out-of-fold 독립 재계산 (decision 9bb29d60 항목 6).

입력 CSV(Ultra result 첨부): video_id, fold, true, pred, prob [, head, model].
 - head 열이 없으면 --head 로 지정(evasion | side). 긴 형식(head 열)이면 두 헤드를 한 번에 처리한다.
 - model 열이 있으면 모델별로 따로 채점한다(e001 재학습 vs 후보 비교).
 - side 라벨은 LEFT=0, RIGHT=1 (문자열도 허용). evasion 은 0/1.
 - prob 는 class 1 확률. pred 와 (prob>=0.5) 불일치는 보고만 한다.

출력: 무결성(v7 라벨 조인, 중복, fold 교차, 누락), out-of-fold Macro-F1, 영상 bootstrap 95% CI(seed 0, 2000회),
상수 예측 하한(두 상수 중 최대), 예측 클래스 분포, fold별 F1, 라벨 출처(human/agent) 수, 판정.
판정(decision 9bb29d60 항목 3 + 순열 귀무): 최빈 예측 비율 <= --max-share, CI 하한 > 상수 하한,
순열 p < 0.05(예측 분포 유지, seed 0) 를 모두 만족하면 candidate. 상수 하한만으로는 무작위 비상수 예측(Macro-F1 ~0.5)도 통과한다.

사용: s2_scene_oof.py --pred oof.csv --out work/s2_scene_oof_<name>/ [--head evasion] [--labels <v7 merged csv>]
셀프 테스트: s2_scene_oof.py --selftest --out work/s2_scene_oof_selftest/
"""
import argparse, json, os, sys
import numpy as np
import pandas as pd

LABELS = "work/agent/outbox/stage2_labels_v7_files/stage2_merged_v7.csv"
SIDE = {"LEFT": 0, "RIGHT": 1, "0": 0, "1": 1}
HEADS = {"evasion": ("evasion_valid", "evasion_space"), "side": ("side_valid", "entry_side")}


def macro_f1(t, p, labels=(0, 1)):
    t, p = np.asarray(t), np.asarray(p)
    f = []
    for c in labels:
        tp = ((p == c) & (t == c)).sum(); fp = ((p == c) & (t != c)).sum(); fn = ((p != c) & (t == c)).sum()
        f.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return float(np.mean(f))


def truth_table(labels_csv, head):
    df = pd.read_csv(labels_csv, dtype={"video_id": str})
    vcol, lcol = HEADS[head]
    sub = df[df[vcol] == 1].copy()
    y = sub[lcol].map(lambda v: SIDE[str(v)] if head == "side" else int(float(v)))
    return pd.DataFrame({"video_id": sub.video_id.values, "y_true": y.values.astype(int), "label_source": sub.label_source.values})


def norm_lab(s, head):
    if head == "side":
        return s.map(lambda v: SIDE[str(v).split(".")[0]] if str(v).split(".")[0] in SIDE else SIDE[str(v)])
    return s.astype(float).astype(int)


def score(sub, truth, head, n_boot=2000, max_share=0.9):
    r = {"n_rows": int(len(sub))}
    integ = {}
    integ["duplicate_videos"] = sub.video_id[sub.video_id.duplicated()].tolist()
    m = truth.merge(sub, on="video_id", how="outer", indicator=True)
    integ["missing_from_pred"] = m.loc[m._merge == "left_only", "video_id"].tolist()
    integ["extra_not_in_labels"] = m.loc[m._merge == "right_only", "video_id"].tolist()
    j = m[m._merge == "both"].copy()
    j["true_n"] = norm_lab(j["true"], head); j["pred_n"] = norm_lab(j["pred"], head)
    integ["true_mismatch_vs_v7"] = j.loc[j.true_n != j.y_true, "video_id"].tolist()
    if "prob" in j and j["prob"].notna().all():
        integ["pred_vs_prob_mismatch"] = int(((j.prob >= 0.5).astype(int) != j.pred_n).sum())
    integ["fold_sizes"] = {str(k): int(v) for k, v in j.fold.value_counts().sort_index().items()}
    integ["pass"] = not (integ["duplicate_videos"] or integ["missing_from_pred"] or integ["extra_not_in_labels"]
                         or integ["true_mismatch_vs_v7"])
    r["integrity"] = integ
    t, p = j.y_true.values, j.pred_n.values
    f1 = macro_f1(t, p)
    const = {f"all_{c}": macro_f1(t, np.full_like(t, c)) for c in (0, 1)}
    floor = max(const.values())
    rng = np.random.default_rng(0)
    n = len(t)
    boots = np.array([macro_f1(t[i], p[i]) for i in (rng.integers(0, n, n) for _ in range(n_boot))])
    lo, hi = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
    share = {str(c): float((p == c).mean()) for c in (0, 1)}
    per_fold = {str(k): {"n": int(len(g)), "macro_f1": macro_f1(g.y_true.values, g.pred_n.values)} for k, g in j.groupby("fold")}
    src = {}
    for s_, g in j.groupby("label_source"):
        src[s_] = {"n": int(len(g)), "macro_f1": macro_f1(g.y_true.values, g.pred_n.values),
                   "acc": float((g.y_true == g.pred_n).mean())}
    auroc = None
    if "prob" in j and j["prob"].notna().all() and len(set(t)) == 2:
        pos, neg = j.prob[t == 1].values, j.prob[t == 0].values
        auroc = float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))
    maxshare = max(share.values())
    # 순열 귀무: 예측 분포를 유지한 채 영상-정답 대응만 섞는다(무작위 비상수 예측의 기대 수준).
    prng = np.random.default_rng(0)
    perm = np.array([macro_f1(t, prng.permutation(p)) for _ in range(n_boot)])
    perm_p = float((1 + (perm >= f1).sum()) / (1 + n_boot))
    if not integ["pass"]:
        verdict = "integrity_fail"
    elif maxshare > max_share:
        verdict = "collapsed"
    elif lo <= floor:
        verdict = "not_above_constant"
    elif perm_p >= 0.05:
        verdict = "not_above_chance"
    else:
        verdict = "candidate"
    r.update({"n": int(n), "oof_macro_f1": f1, "ci95": [lo, hi], "constant_floor": floor, "constant": const,
              "auroc_prob": auroc, "pred_share": share, "true_share": {str(c): float((t == c).mean()) for c in (0, 1)},
              "accuracy": float((t == p).mean()), "per_fold": per_fold, "label_source": src,
              "perm_null_mean": float(perm.mean()), "perm_null_q95": float(np.percentile(perm, 95)), "perm_p": perm_p,
              "score_contribution_0.15": 0.15 * f1,
              "verdict": verdict,
              "rule": f"integrity pass and max pred share <= {max_share} and ci_low > constant_floor and permutation p < 0.05"})
    return r


def run(pred_csv, out, head, labels_csv, max_share):
    df = pd.read_csv(pred_csv, dtype={"video_id": str})
    if "head" not in df:
        if not head:
            sys.exit("head 열이 없으면 --head 필요")
        df["head"] = head
    if "model" not in df:
        df["model"] = "model"
    res = {"pred_csv": pred_csv, "labels_csv": labels_csv, "results": {}}
    for (mdl, hd), sub in df.groupby(["model", "head"]):
        res["results"].setdefault(mdl, {})[hd] = score(sub.reset_index(drop=True), truth_table(labels_csv, hd), hd,
                                                       max_share=max_share)
    for mdl, hs in res["results"].items():
        if "evasion" in hs and "side" in hs:
            hs["scene_contrib"] = 0.15 * hs["side"]["oof_macro_f1"] + 0.15 * hs["evasion"]["oof_macro_f1"]
            hs["scene_contrib_constant"] = 0.15 * hs["side"]["constant_floor"] + 0.15 * hs["evasion"]["constant_floor"]
    os.makedirs(out, exist_ok=True)
    json.dump(res, open(os.path.join(out, "oof_report.json"), "w"), indent=1, ensure_ascii=False)
    return res


def selftest(out):
    os.makedirs(out, exist_ok=True)
    rows, rng = [], np.random.default_rng(1)
    for hd in HEADS:
        tt = truth_table(LABELS, hd)
        folds = rng.permutation(np.arange(len(tt)) % 5)
        for mdl in ["oracle", "const", "random"]:
            for (_, r), f in zip(tt.iterrows(), folds):
                if mdl == "oracle":
                    pr = int(r["y_true"]); pb = 0.9 if pr else 0.1
                elif mdl == "const":
                    pr = 1; pb = 0.7
                else:
                    pb = float(rng.random()); pr = int(pb >= 0.5)
                lab = (lambda v: ["LEFT", "RIGHT"][v]) if hd == "side" else (lambda v: v)
                rows.append({"model": mdl, "head": hd, "video_id": r["video_id"], "fold": int(f),
                             "true": lab(int(r["y_true"])), "pred": lab(pr), "prob": pb})
    good = pd.DataFrame(rows)
    good.to_csv(os.path.join(out, "synthetic_oof.csv"), index=False)
    res = run(os.path.join(out, "synthetic_oof.csv"), os.path.join(out, "good"), None, LABELS, 0.9)["results"]
    bad = good[good.model == "oracle"].copy()
    bad = pd.concat([bad.iloc[1:], bad.iloc[:1], bad.iloc[:1]])  # 중복 1
    bad.to_csv(os.path.join(out, "bad.csv"), index=False)
    rb = run(os.path.join(out, "bad.csv"), os.path.join(out, "bad"), None, LABELS, 0.9)["results"]
    checks = {
        "oracle_candidate": all(res["oracle"][h]["verdict"] == "candidate" and res["oracle"][h]["oof_macro_f1"] == 1.0 for h in HEADS),
        "const_collapsed": all(res["const"][h]["verdict"] == "collapsed" for h in HEADS),
        "const_equals_floor": all(abs(res["const"][h]["oof_macro_f1"] - res["const"][h]["constant"]["all_1"]) < 1e-12 for h in HEADS),
        "random_not_candidate": all(res["random"][h]["verdict"] != "candidate" for h in HEADS),
        "random_passes_old_rule": all(res["random"][h]["ci95"][0] > res["random"][h]["constant_floor"] for h in HEADS),
        "all_integrity_pass": all(res[m][h]["integrity"]["pass"] for m in res for h in HEADS),
        "dup_detected": any(not rb["oracle"][h]["integrity"]["pass"] for h in HEADS),
    }
    summary = {"checks": checks, "pass": all(checks.values()),
               "floors": {h: res["const"][h]["constant_floor"] for h in HEADS},
               "random": {h: {k: res["random"][h][k] for k in ("oof_macro_f1", "ci95", "perm_null_mean", "perm_null_q95", "perm_p", "verdict")} for h in HEADS},
               "oracle_perm_p": {h: res["oracle"][h]["perm_p"] for h in HEADS}}
    json.dump(summary, open(os.path.join(out, "selftest.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred"); ap.add_argument("--out", required=True); ap.add_argument("--head", choices=list(HEADS))
    ap.add_argument("--labels", default=LABELS); ap.add_argument("--max-share", type=float, default=0.9)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(a.out)
    else:
        res = run(a.pred, a.out, a.head, a.labels, a.max_share)
        print(json.dumps({m: {h: (v if not isinstance(v, dict) else {k: v[k] for k in ("n", "oof_macro_f1", "ci95", "constant_floor", "pred_share", "verdict")})
                             for h, v in hs.items()} for m, hs in res["results"].items()}, indent=1))
