"""S1 고주파(HF) 에너지 탐침: e001이 '흐림=RERECORDED'를 배웠는지 확인한다.

- S23 format-matched 192클립과 v1 합성 학습셋(ORIG/SYN*)에서 프레임 8장을 균등 추출한다.
- 각 프레임에서 (a) 네이티브 해상도 Laplacian 분산, (b) 모델 입력처럼 224x224로 줄인 뒤 Laplacian 분산을 잰다.
- 쌍 단위로 RERECORDED/ORIGINAL HF 비율, 그리고 e001 prob와 HF의 클래스 내 순위상관을 낸다.
"""
import argparse, json, os
import cv2
import numpy as np
import pandas as pd


def hf_stats(path, n=8):
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    idx = set(np.linspace(0, max(total - 1, 0), n).astype(int).tolist())
    nat, small, i = [], [], 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if i in idx:
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            nat.append(cv2.Laplacian(g, cv2.CV_64F).var())
            s = cv2.resize(g, (224, 224), interpolation=cv2.INTER_AREA)
            small.append(cv2.Laplacian(s, cv2.CV_64F).var())
        i += 1
    cap.release()
    return float(np.mean(nat)), float(np.mean(small))


def spearman(a, b):
    ra = pd.Series(a).rank().values
    rb = pd.Series(b).rank().values
    return float(np.corrcoef(ra, rb)[0, 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s23-dir", default="data/derived/s1_s23_format_matched_v1")
    ap.add_argument("--pred", required=True)
    ap.add_argument("--v1-dir", default="data/derived/s1_synthetic_v1")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rep = {}

    d = pd.read_csv(a.pred)
    rows = []
    for r in d.itertuples():
        nat, sm = hf_stats(os.path.join(a.s23_dir, r.file))
        rows.append(dict(file=r.file, pair_id=r.pair_id, split=r.split, codec=r.codec, kind=r.kind,
                         prob=r.prob_rerecorded, hf_native=nat, hf_224=sm))
    s = pd.DataFrame(rows)
    s.to_csv(os.path.join(a.out, "s23_hf.csv"), index=False)
    rep["s23"] = {}
    for c, g in s.groupby("codec"):
        p = g.pivot(index="pair_id", columns="kind", values=["hf_native", "hf_224", "prob"])
        ent = {}
        for m in ["hf_native", "hf_224"]:
            ratio = p[(m, "capture")] / p[(m, "original")]
            ent[m] = dict(median_ratio_capture_over_original=float(ratio.median()),
                          frac_capture_higher=float((ratio > 1).mean()))
        ent["spearman_prob_vs_hf224_within"] = {k: spearman(gg.prob, gg.hf_224) for k, gg in g.groupby("kind")}
        ent["spearman_prob_vs_hf224_pooled"] = spearman(g.prob, g.hf_224)
        dp = p[("prob", "capture")] - p[("prob", "original")]
        dh = np.log(p[("hf_224", "capture")] / p[("hf_224", "original")])
        ent["spearman_pairdiff_prob_vs_loghfratio"] = spearman(dp.values, dh.values)
        rep["s23"][c] = ent

    if os.path.isdir(a.v1_dir):
        man = pd.read_csv(os.path.join(a.v1_dir, "manifest.csv"))
        vr = []
        for r in man.itertuples():
            nat, sm = hf_stats(os.path.join(a.v1_dir, r.file))
            vr.append(dict(file=r.file, source_id=r.source_id, split=r.split, variant=r.variant, hf_native=nat, hf_224=sm))
        v = pd.DataFrame(vr)
        v.to_csv(os.path.join(a.out, "v1_hf.csv"), index=False)
        orig = v[v.variant == "ORIG"].set_index("source_id")
        syn = v[v.variant != "ORIG"].copy()
        for m in ["hf_native", "hf_224"]:
            syn[m + "_ratio"] = syn[m] / syn.source_id.map(orig[m])
        rep["v1"] = {m: dict(median_ratio_syn_over_orig=float(syn[m + "_ratio"].median()),
                             frac_syn_higher=float((syn[m + "_ratio"] > 1).mean()),
                             n=int(len(syn))) for m in ["hf_native", "hf_224"]}
    json.dump(rep, open(os.path.join(a.out, "report.json"), "w"), indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
