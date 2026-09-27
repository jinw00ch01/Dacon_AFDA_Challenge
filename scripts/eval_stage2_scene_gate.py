"""Pre-registered S2 scene-head gate: e005 vs e001 on the SAME v7 validation.

Decision 11 freezes S2 collision/entry TIMING at the v001 model output. e005's
ONLY change vs e001 is swapping the feature cache to the v7 label release, which
adds human-reviewed scene labels (evasion_space + entry_side). This script closes
the pre-registered gate wired in configs/exp/s2_e005.json:

  GATE: e005 dir(side) Macro-F1 AND evasion Macro-F1 each >= the v001/e001 model
  RE-EVALUATED on the identical v7 validation split. Baseline is reset per the
  v7 val-membership-shift caveat (STATUS 22:52): we do NOT compare against e001's
  old val numbers, we recompute e001 on this exact v7 val here.

Both models are loaded from their best.pt (each selected by min time_mae_s, so the
comparison is apples-to-apples: each model's scene head at its own best-time epoch).
The scene head is fed hidden states at the ARGMAX collision/entry positions, exactly
as scripts/train_stage2.py::evaluate does (no teacher forcing at eval).

Labels are agent+human v7 PROXY (not official GT); this is a self-diagnostic gate,
LB S2 remains the final arbiter. Only videos with a valid side/evasion label score.

Usage:
  python scripts/eval_stage2_scene_gate.py \
      --cache data/derived/s2_feat_cache_v7 \
      --model models/stage2:e001 --model models/stage2_e005:e005 \
      --out work/s2_scene_gate/report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from afda.models import Stage2Temporal  # noqa: E402
from afda import metrics  # noqa: E402
from train_stage2 import load_cache, _logits, _scene  # noqa: E402


@torch.inference_mode()
def eval_scene(model, items, device, amp):
    """Collect side/evasion true+pred over the val items (argmax positions)."""
    model.eval()
    ev_t, ev_p, sd_t, sd_p = [], [], [], []
    for it in items:
        x = torch.from_numpy(it["feats"]).unsqueeze(0).to(device)
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=amp):
            h, cl, el = _logits(model, x)
        c_pred, e_pred = int(cl.argmax(1)), int(el.argmax(1))
        scene = _scene(model, h.float(), c_pred, e_pred)
        if it["evasion"] is not None:
            ev_t.append(it["evasion"]); ev_p.append(int(scene[:, :2].argmax(1)))
        if it["side"] is not None:
            sd_t.append(it["side"]); sd_p.append(int(scene[:, 2:].argmax(1)))
    acc = lambda t, p: (float(np.mean(np.asarray(t) == np.asarray(p))) if t else None)
    f1 = lambda t, p: (metrics.macro_f1(t, p, labels=[0, 1]) if t else None)
    return {
        "n_evasion": len(ev_t), "evasion_acc": acc(ev_t, ev_p), "evasion_f1": f1(ev_t, ev_p),
        "n_side": len(sd_t), "side_acc": acc(sd_t, sd_p), "dir_f1": f1(sd_t, sd_p),
        "evasion_true": ev_t, "evasion_pred": ev_p,
        "side_true": sd_t, "side_pred": sd_p,
    }


def load_model(root: Path, device):
    ckpt = torch.load(root / "best.pt", map_location=device, weights_only=False)
    model = Stage2Temporal().to(device)
    model.load_state_dict(ckpt["model"])
    return model


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, default=ROOT / "data/derived/s2_feat_cache_v7")
    ap.add_argument("--split", default="validation")
    ap.add_argument("--model", action="append", required=True,
                    help="path[:tag]; repeatable. e.g. models/stage2:e001")
    ap.add_argument("--out", type=Path, default=ROOT / "work/s2_scene_gate/report.json")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp = device.type == "cuda"
    items = load_cache(args.cache, args.split, None)
    n_ev = sum(1 for it in items if it["evasion"] is not None)
    n_sd = sum(1 for it in items if it["side"] is not None)
    print(f"cache={args.cache.name} split={args.split} val_videos={len(items)} "
          f"evasion_labelled={n_ev} side_labelled={n_sd} device={device}", flush=True)

    results = {}
    for spec in args.model:
        path, _, tag = spec.partition(":")
        tag = tag or Path(path).name
        model = load_model(ROOT / path if not Path(path).is_absolute() else Path(path), device)
        r = eval_scene(model, items, device, amp)
        results[tag] = r
        print(f"[{tag}] evasion_f1={r['evasion_f1']} (acc={r['evasion_acc']}, n={r['n_evasion']}) "
              f"dir_f1={r['dir_f1']} (acc={r['side_acc']}, n={r['n_side']})", flush=True)

    # Pre-registered gate: e005 both heads >= e001 on the same val.
    gate = None
    if "e001" in results and "e005" in results:
        b, c = results["e001"], results["e005"]
        ev_pass = (c["evasion_f1"] is not None and b["evasion_f1"] is not None
                   and c["evasion_f1"] >= b["evasion_f1"])
        dir_pass = (c["dir_f1"] is not None and b["dir_f1"] is not None
                    and c["dir_f1"] >= b["dir_f1"])
        gate = {
            "evasion_f1_e001": b["evasion_f1"], "evasion_f1_e005": c["evasion_f1"],
            "evasion_pass": bool(ev_pass),
            "dir_f1_e001": b["dir_f1"], "dir_f1_e005": c["dir_f1"],
            "dir_pass": bool(dir_pass),
            "gate_pass": bool(ev_pass and dir_pass),
        }
        print(f"GATE: {json.dumps(gate)}", flush=True)

    out = {"cache": str(args.cache), "split": args.split,
           "val_videos": len(items), "evasion_labelled": n_ev, "side_labelled": n_sd,
           "results": results, "gate": gate,
           "label_source": "agent+human v7 proxy (not official GT)"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
