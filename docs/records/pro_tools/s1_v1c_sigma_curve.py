"""HF ratio vs grain sigma for one v1c ORIG clip (debug calibration). Usage: <orig.mp4> [sigmas...]"""
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "Dacon_AFDA_Challenge_wt/s1-v1c-calib/scripts"))
import s1_synth_digital as sd  # noqa: E402

orig = Path(sys.argv[1])
sigmas = [float(s) for s in sys.argv[2:]] or [1.0, 2.0, 3.0, 4.0, 6.0, 8.0]
ff = sd.find_ffmpeg(None)
dec, _ = sd.read_frames(orig)
p = {"contrast": 1.02, "black": 1.5, "crf": 23}
with tempfile.TemporaryDirectory() as td:
    out = Path(td) / "x.mp4"
    for s in sigmas:
        p["grain_sigma"] = s
        rng = np.random.default_rng(7)
        sd.write_x264(ff, out, [sd.tone(f, rng, p) for f in dec], 23)
        rec, _ = sd.read_frames(out)
        full = np.mean([sd.hf_std(rec[i]) / sd.hf_std(dec[i]) for i in range(len(dec))])
        print(s, round(sd.hf_ratio(dec, rec), 3), round(float(full), 3), out.stat().st_size, flush=True)
