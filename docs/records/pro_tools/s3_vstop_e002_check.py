"""Consistency checks before LOSO: e002 val_predictions vs Pro's v1b recomputation."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import s3_vstop_calib as C

pred = pd.read_csv(sys.argv[1], encoding="utf-8-sig")
val = C.load_val(C.ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv")
df = val.merge(pred, on=["source_id", "sample_index"], how="inner", validate="one_to_one")
print("pred rows", len(pred), "val rows", len(val), "joined", len(df), "dups", pred.duplicated(["source_id", "sample_index"]).sum())
print("split in pred", pred["split"].value_counts().to_dict())
print("accel_true==v1b", (df["accel_true"] == df["accel_true_v1b"]).mean(), "steer_true==v1b", (df["steer_true"] == df["steer_true_v1b"]).mean())
d = C.derive(df, 0.5)
print("derive(0.5)==accel_pred", (d == df["accel_pred"]).mean())
print("macro accel e002 as given", C.macro_f1(df["accel_true"].tolist(), df["accel_pred"].tolist()))
print("per-source true STOPPED", df.groupby("source_id")["accel_true"].apply(lambda s: (s == "STOPPED").sum()).to_dict())
print("per-source n", df.groupby("source_id").size().to_dict())
st = df[df["accel_true"] == "STOPPED"]["speed_pred"]
nst = df[df["accel_true"] != "STOPPED"]["speed_pred"]
print("speed_pred STOPPED true: q", st.quantile([0, .1, .5, .9, 1]).round(2).tolist())
print("speed_pred non-STOPPED: q", nst.quantile([0, .01, .05, .1, .5]).round(2).tolist())
print("speed_true STOPPED true max", df[df["accel_true"] == "STOPPED"]["speed_mps"].max())
