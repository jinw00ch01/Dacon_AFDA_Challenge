"""e001 (v001 S2) collision/entry predictions on the SAME windows as Pro's
motion-rule eval (CLAUDE.md decision 12-A, Pro qa 04a6895b / request 056da1af).

Pro's rule predicts a within-window collision index (0..49) for each 50-frame
10Hz window in windows_pair.csv. To compare fairly we feed the SAME 50 window
frames to the v001 S2 model (ResNet18 IMAGENET1K_V1 features -> BiGRU temporal
head, submission/inference.py) and take the argmax over the 50 window positions
-- i.e. e001 sees exactly the frames the rule sees, not the whole video.

Per-video ResNet18 features are decoded once from the ORIGINAL mp4 (v1 =
data/external/nexar_subset_v1, v2 = data/external/nexar_subset_v2; frame numbers
match Pro's 640px copies, parity confirmed) and gathered by
source_frame_indices for each window. Feature row i == decode frame index i,
the same convention cache_s2_features.py / the agent labels use.

Metric: official Acc@0.3s == |pred - gt| <= 3 (both are 10Hz window indices;
0.3 s at 10Hz == 3 frames). Reported per group / subset alongside the rule's
pred_pair column so Ultra and Pro compute the same number from one CSV.

Usage:
  python scripts/eval_s2_e001_windows.py \
      --windows data/derived/experiment_packets/inbox/<qa>/files/windows_pair.csv \
      --labels  <stage2_merged_nexar_v2.csv> \
      --model-root models/stage2 \
      --out work/s2_e001_windows/e001_windows.csv
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from PIL import Image
from torch import nn
from torchvision.models import resnet18, ResNet18_Weights

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submission"))
from inference import _Stage2Temporal  # noqa: E402  (byte-identical to submission)

V2_ROOT = ROOT / "data" / "external" / "nexar_subset_v2" / "train"


def resolve_video(video_id: str, src: str, source_path: str) -> Path:
    """v1 uses the merged-CSV source_path; v2 is remapped to the Ultra original."""
    if src == "v2":
        for cls in ("positive", "negative"):
            cand = V2_ROOT / cls / f"{video_id}.mp4"
            if cand.exists():
                return cand
        raise FileNotFoundError(f"v2 original missing for {video_id} under {V2_ROOT}")
    p = ROOT / source_path
    if not p.exists():
        raise FileNotFoundError(f"v1 source missing: {p}")
    return p


def decode_features(video_path: Path, backbone, transform, device, batch_size: int):
    """Stream-decode the whole clip -> (T, 512) float32 features (row i == frame i)."""
    cap = cv2.VideoCapture(str(video_path))
    feats, batch = [], []

    def flush():
        x = torch.stack(batch).to(device, non_blocking=True)
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=(device.type == "cuda")):
            out = backbone(x)
        feats.append(out.float().cpu())
        batch.clear()

    with torch.inference_mode():
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            batch.append(transform(Image.fromarray(rgb)))
            if len(batch) >= batch_size:
                flush()
        if batch:
            flush()
    cap.release()
    if not feats:
        raise ValueError(f"cannot decode {video_path.name}")
    return torch.cat(feats)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--windows", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--model-root", default="models/stage2")
    ap.add_argument("--out", default="work/s2_e001_windows/e001_windows.csv")
    ap.add_argument("--batch-size", type=int, default=256)
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model_root = ROOT / args.model_root

    # Backbone + transform byte-identical to submission.inference.predict_stage2.
    transform = ResNet18_Weights.IMAGENET1K_V1.transforms()
    backbone = resnet18(weights=None)
    backbone.load_state_dict(
        torch.load(model_root / "resnet18-f37072fd.pth", map_location="cpu", weights_only=True)
    )
    backbone.fc = nn.Identity()
    backbone.to(device).eval()
    temporal = _Stage2Temporal()
    temporal.load_state_dict(
        torch.load(model_root / "best.pt", map_location="cpu", weights_only=False)["model"]
    )
    temporal.to(device).eval()

    wp = pd.read_csv(ROOT / args.windows, dtype={"video_id": str})
    lab = pd.read_csv(ROOT / args.labels, dtype={"video_id": str})
    src_by_vid = dict(zip(lab.video_id, lab.source_path))

    rows = []
    per_video = {vid: g for vid, g in wp.groupby("video_id")}
    t0 = time.time()
    for n, (vid, g) in enumerate(per_video.items(), 1):
        src = g.iloc[0]["src"]
        video_path = resolve_video(vid, src, src_by_vid.get(vid, ""))
        feats = decode_features(video_path, backbone, transform, device, args.batch_size)
        T = feats.shape[0]
        with torch.inference_mode():
            for r in g.itertuples():
                idx = [int(x) for x in str(r.source_frame_indices).split()]
                if max(idx) >= T:
                    raise IndexError(f"{vid} win {r.win}: frame {max(idx)} >= decoded {T}")
                seq = feats[idx][None].to(device)  # (1, 50, 512)
                col, ent, _ = temporal(seq)
                rows.append({
                    "video_id": vid, "win": int(r.win), "group": r.group, "src": src,
                    "e001_clean": int(r.e001_clean), "label_source": r.label_source,
                    "gt_collision": int(r.gt_collision),
                    "gt_entry": (None if pd.isna(r.gt_entry) else int(r.gt_entry)),
                    "pred_pair": int(r.pred_pair),
                    "e001_collision": int(col.item()), "e001_entry": int(ent.item()),
                })
        print(f"[{n}/{len(per_video)}] {vid} src={src} T={T} wins={len(g)} "
              f"({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows)
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)

    # Acc@0.3s == |pred - gt| <= 3 (10Hz window indices). Same metric as the rule.
    def acc(sub, col, gt="gt_collision"):
        m = sub[gt].notna()
        s = sub[m]
        if not len(s):
            return None
        return round(float((np.abs(s[col] - s[gt]) <= 3).mean()), 4)

    summary = {"created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "n_rows": len(out), "model_root": args.model_root, "groups": {}}
    for grp in ("HELD", "FIT"):
        gsub = out[out.group == grp]
        if not len(gsub):
            continue
        block = {"n": len(gsub)}
        for name, ss in (("all", gsub), ("human", gsub[gsub.label_source == "human"]),
                         ("e001_clean", gsub[gsub.e001_clean == 1]),
                         ("v1", gsub[gsub.src == "v1"]), ("v2", gsub[gsub.src == "v2"])):
            block[name] = {
                "n": int(len(ss)),
                "e001_collision_acc03": acc(ss, "e001_collision"),
                "rule_pair_acc03": acc(ss, "pred_pair"),
            }
        # entry (only rows with a within-window gt_entry)
        block["entry_all"] = {
            "n_with_gt": int(gsub["gt_entry"].notna().sum()),
            "e001_entry_acc03": acc(gsub, "e001_entry", "gt_entry"),
        }
        summary["groups"][grp] = block

    (out_path.parent / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    print(f"wrote {out_path} and summary.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
