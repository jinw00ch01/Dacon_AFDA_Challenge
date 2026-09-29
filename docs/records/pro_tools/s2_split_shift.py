"""v6(e001 학습) vs v7(e005·게이트 val) split 재현: cache_s2_features.assign_splits와 같은 로직(seed 0, val_frac 0.2)."""
import json, sys
import numpy as np
import pandas as pd


def assign_splits(df, val_frac=0.2, seed=0):
    rng = np.random.RandomState(seed)
    split = pd.Series("train", index=df.index)
    for _, idx in df.groupby(df["collision_valid"].astype(int)).groups.items():
        idx = list(idx)
        rng.shuffle(idx)
        n_val = max(1, round(len(idx) * val_frac)) if len(idx) >= 3 else 0
        for i in idx[:n_val]:
            split[i] = "validation"
    return split


def main():
    o = {}
    d = {}
    for ver in ["v6", "v7"]:
        df = pd.read_csv(f"work/agent/outbox/stage2_labels_{ver}_files/stage2_merged_{ver}.csv", dtype={"video_id": str})
        df["split"] = assign_splits(df)
        d[ver] = df.set_index("video_id")
        o[ver] = {"n_val": int((df.split == "validation").sum()), "n_rows": int(len(df))}
    v6, v7 = d["v6"], d["v7"]
    val7 = v7[v7.split == "validation"]
    for c in ["evasion_valid", "side_valid"]:
        s = val7[val7[c] == 1]
        in_train6 = [vid for vid in s.index if v6.loc[vid, "split"] == "train"]
        labelled_train6 = [vid for vid in in_train6 if v6.loc[vid, c] == 1]
        o[c] = {"v7_val_n": int(len(s)), "label_source": s.label_source.value_counts().to_dict(),
                "in_e001_train_split": len(in_train6), "in_e001_train_with_label": len(labelled_train6),
                "videos_in_e001_train_with_label": labelled_train6,
                "v7_val_videos": s.index.tolist()}
    o["v7_val_all_videos_in_v6_train"] = int((v6.loc[val7.index, "split"] == "train").sum())
    json.dump(o, open(sys.argv[1], "w"), indent=1)
    print(json.dumps(o, indent=1))


if __name__ == "__main__":
    main()
