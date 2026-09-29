"""Check an Ultra rule3 graft (s3-accel-rule3) against the Pro reference.

Loads an inference.py (path or git rev, default origin/main), finds the grafted lr30 / rule3 helpers by name,
and on the 5 public examples (gray[::2], 10 Hz rows) compares them with
work/s3_accel_rule3_ref/public_rows_reference.csv (div_far_lr30_ref, rule3_nonstopped). Also checks the
thresholds / constants and runs the numpy reference on the same div_far for all 10 Hz rows (not just the 50).
usage: s3_rule3_graft_check.py <out_dir> [--rev origin/main | --file path/to/inference.py]
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from s3_accel_rule3_ref import T_ACC, T_DEC, _s3_accel_rule3, _s3_div_far_lr30  # noqa: E402

REF = ROOT / "work/s3_accel_rule3_ref/public_rows_reference.csv"


def load_inference(out: Path, rev: str | None, file: str | None):
    if file:
        src = Path(file)
    else:
        text = subprocess.run(["git", "show", f"{rev}:submission/inference.py"], cwd=ROOT, capture_output=True,
                              check=True).stdout
        src = out / "inference_under_test.py"
        src.write_bytes(text)
    spec = importlib.util.spec_from_file_location("inf_under_test", src)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "submission"))
    spec.loader.exec_module(mod)
    return mod, str(src)


def find(mod, keys):
    return [n for n, o in vars(mod).items() if callable(o) and any(k in n.lower() for k in keys)
            and getattr(o, "__module__", "") == mod.__name__]


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    rev = sys.argv[sys.argv.index("--rev") + 1] if "--rev" in sys.argv else "origin/main"
    file = sys.argv[sys.argv.index("--file") + 1] if "--file" in sys.argv else None
    inf, src = load_inference(out, None if file else rev, file)
    rep = {"source": src, "rev": None if file else rev}
    lr_names, rule_names = find(inf, ["lr30", "log_ratio"]), find(inf, ["rule3", "accel_rule"])
    consts = {n: v for n, v in vars(inf).items() if n.startswith("_S3_") and isinstance(v, (int, float))}
    rep["found_lr_fns"], rep["found_rule_fns"], rep["s3_constants"] = lr_names, rule_names, consts
    tdec = [v for n, v in consts.items() if "DEC" in n]
    tacc = [v for n, v in consts.items() if "ACC" in n and "DEC" not in n]
    rep["threshold_match"] = {"t_dec_ref": T_DEC, "t_acc_ref": T_ACC,
                              "t_dec_found": tdec, "t_acc_found": tacc,
                              "t_dec_ok": any(abs(v - T_DEC) < 1e-9 for v in tdec),
                              "t_acc_ok": any(abs(v - T_ACC) < 1e-9 for v in tacc)}
    ref = pd.read_csv(REF)
    rows = []
    for vid, g in ref.groupby("ID"):
        cap = cv2.VideoCapture(str(ROOT / f"Baseline/data/stage3/videos/{vid}.mp4"))
        gray = []
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            gray.append(cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (160, 120), interpolation=cv2.INTER_AREA))
        cap.release()
        g10 = np.stack(gray)[::2]
        div = inf._s3_motion_series(g10)[:, 1]
        lr_ref = _s3_div_far_lr30(div)
        rule_ref = np.asarray(_s3_accel_rule3(div, ["CONSTANT"] * len(div)))
        res = {"ID": vid, "rows10hz": len(g10)}
        for n in lr_names:
            try:
                lr = np.asarray(getattr(inf, n)(div), np.float64)
                res[f"{n}_maxabs_all_rows"] = float(np.max(np.abs(lr - lr_ref)))
                res[f"{n}_maxabs_public_rows"] = float(np.max(np.abs(lr[g.sample_index.to_numpy()]
                                                                  - g.div_far_lr30_ref.to_numpy())))
            except Exception as e:  # signature differs: record, do not guess further
                res[f"{n}_error"] = repr(e)
        for n in rule_names:
            fn = getattr(inf, n)
            try:
                nparams = len(inspect.signature(fn).parameters)
                pred = np.asarray(fn(div, ["CONSTANT"] * len(div)) if nparams >= 2 else fn(div))
                res[f"{n}_mismatch_all_rows"] = int((pred != rule_ref).sum())
                res[f"{n}_mismatch_public_rows"] = int((pred[g.sample_index.to_numpy()]
                                                        != g.rule3_nonstopped.to_numpy()).sum())
                st = np.asarray(fn(div, ["STOPPED"] * len(div))) if nparams >= 2 else None
                if st is not None:
                    res[f"{n}_keeps_stopped"] = bool((st == "STOPPED").all())
            except Exception as e:
                res[f"{n}_error"] = repr(e)
        rows.append(res)
    rep["per_video"] = rows
    ok = (rep["threshold_match"]["t_dec_ok"] and rep["threshold_match"]["t_acc_ok"] and lr_names + rule_names
          # reference CSV is rounded to 6 decimals
          and all(v < 1e-6 for r in rows for k, v in r.items() if "mismatch" in k or "maxabs" in k)
          and not any("error" in k for r in rows for k in r))
    rep["verdict"] = "MATCH" if ok else "CHECK"
    (out / "report.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
