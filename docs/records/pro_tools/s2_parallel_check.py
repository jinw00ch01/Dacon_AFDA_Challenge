"""Operator request (cycle 3707f7ef870e): freeze main 72bcf5f S2 rule outputs, later compare Ultra's parallel S2 frame read.

prep : build image folders like the private Stage 2 input (<root>/images/<ID>/<frame>.jpg)
       - 5 public examples (Baseline stage2 videos, every decoded frame, 000000.jpg...)
       - N Nexar 10Hz windows from work/s2_motion_rule_r1/windows_pair.csv (640px copies, file name = source frame index,
         so frame numbers start > 0 and step by 3: exercises the frame_numbers mapping)
run  : python s2_parallel_check.py run <inference.py> <tag> [--read <fn_name>]
       imports the given inference.py (no weights), reads every folder exactly like predict_stage2 does in that version
       (default: _s2_to_gray([cv2.imread(p) ...]); --read NAME calls inf.NAME(paths) instead), then runs the rule
       functions. Saves per-folder gray sha256, motion series, collision/entry/evasion, frame numbers -> <tag>.json/.npz
cmp  : python s2_parallel_check.py cmp <tagA> <tagB>
"""
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "work" / "s2_parallel_check"
IMG = OUT / "images"
N_NEXAR = 60


def prep():
    for mp4 in sorted((ROOT / "Baseline/data/stage2/videos").glob("*.mp4")):
        folder = IMG / mp4.stem
        folder.mkdir(parents=True, exist_ok=True)
        cap, i = cv2.VideoCapture(str(mp4)), 0
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            cv2.imwrite(str(folder / f"{i:06d}.jpg"), bgr)
            i += 1
        cap.release()
        print(mp4.stem, i)
    meta = pd.read_csv(ROOT / "work/nexar_v2/meta.csv", dtype={"video_id": str}).set_index("video_id")
    w = pd.read_csv(ROOT / "work/s2_motion_rule_r1/windows_pair.csv", dtype={"video_id": str})
    w = w[w.video_id.isin(meta.index)].reset_index(drop=True)
    pick = w.iloc[np.linspace(0, len(w) - 1, N_NEXAR).round().astype(int)]
    rows = []
    for _, r in pick.iterrows():
        idx = [int(x) for x in r.source_frame_indices.split()]
        want, folder = set(idx), IMG / f"nx{r.video_id}_w{int(r.win)}"
        folder.mkdir(parents=True, exist_ok=True)
        cap, i = cv2.VideoCapture(str(ROOT / meta.loc[r.video_id, "source_path"])), 0
        while i <= max(idx):
            ok, bgr = cap.read()
            if not ok:
                break
            if i in want:
                cv2.imwrite(str(folder / f"{i:06d}.jpg"), bgr)
            i += 1
        cap.release()
        n = len(list(folder.glob("*.jpg")))
        rows.append({"folder": folder.name, "video_id": r.video_id, "win": int(r.win), "group": r.group, "n": n})
        print(folder.name, n)
    pd.DataFrame(rows).to_csv(OUT / "nexar_windows.csv", index=False)


def load(path):
    spec = importlib.util.spec_from_file_location(f"inf_{abs(hash(path))}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(inf_path, tag, read_fn=None):
    inf = load(inf_path)
    res, arrays, t_read = {}, {}, 0.0
    for folder in sorted(p for p in IMG.iterdir() if p.is_dir()):
        paths = sorted((p for p in folder.iterdir() if p.suffix.lower() in inf.IMAGE_EXT), key=inf._frame_number)
        t = time.perf_counter()
        gray = getattr(inf, read_fn)(paths) if read_fn else inf._s2_to_gray([cv2.imread(str(p)) for p in paths])
        t_read += time.perf_counter() - t
        gray = np.asarray(gray)
        s = inf._s2_motion_series(gray)
        c = inf._s2_predict_collision(gray)
        e = inf._s2_predict_entry(c)
        fn = [inf._frame_number(p) for p in paths]
        res[folder.name] = {"n": len(paths), "gray_shape": list(gray.shape), "gray_dtype": str(gray.dtype),
                            "gray_sha256": hashlib.sha256(np.ascontiguousarray(gray).tobytes()).hexdigest(),
                            "rule_collision_idx": c, "rule_entry_idx": e,
                            "collision_frame": fn[c], "entry_frame": fn[e],
                            "evasion_space": int(inf._s2_predict_evasion(gray, c)),
                            "evasion_feature": inf._s2_evasion_feature(gray, c)}
        arrays[f"{folder.name}__div"], arrays[f"{folder.name}__dy"] = s["div"], s["dy"]
        arrays[f"{folder.name}__score"] = inf._s2_collision_score(s)
    meta = {"inference": str(inf_path), "read_fn": read_fn or "_s2_to_gray([cv2.imread])", "read_sec_total": round(t_read, 2),
            "cv2_threads": cv2.getNumThreads(), "n_folders": len(res)}
    (OUT / f"{tag}.json").write_text(json.dumps({"meta": meta, "folders": res}, indent=1))
    np.savez(OUT / f"{tag}.npz", **arrays)
    print(json.dumps(meta))


def cmp(a, b):
    ja, jb = (json.loads((OUT / f"{t}.json").read_text()) for t in (a, b))
    na, nb = np.load(OUT / f"{a}.npz"), np.load(OUT / f"{b}.npz")
    keys = ["n", "gray_shape", "gray_dtype", "gray_sha256", "rule_collision_idx", "rule_entry_idx",
            "collision_frame", "entry_frame", "evasion_space", "evasion_feature"]
    diffs = []
    for f in sorted(set(ja["folders"]) | set(jb["folders"])):
        fa, fb = ja["folders"].get(f), jb["folders"].get(f)
        if fa is None or fb is None:
            diffs.append({"folder": f, "field": "missing"})
            continue
        diffs += [{"folder": f, "field": k, "a": fa[k], "b": fb[k]} for k in keys if fa[k] != fb[k]]
    arr_diff = sorted(k for k in set(na.files) | set(nb.files)
                      if k not in na.files or k not in nb.files or na[k].tobytes() != nb[k].tobytes())
    rep = {"a": ja["meta"], "b": jb["meta"], "n_folders": len(ja["folders"]), "field_diffs": diffs,
           "array_diffs": arr_diff, "identical": not diffs and not arr_diff}
    (OUT / f"cmp_{a}_vs_{b}.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: rep[k] for k in ("n_folders", "identical")}), len(diffs), len(arr_diff))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "prep":
        prep()
    elif cmd == "run":
        rf = sys.argv[sys.argv.index("--read") + 1] if "--read" in sys.argv else None
        run(sys.argv[2], sys.argv[3], rf)
    elif cmd == "cmp":
        cmp(sys.argv[2], sys.argv[3])
