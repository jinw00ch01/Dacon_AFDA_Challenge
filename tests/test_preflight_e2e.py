"""Contract tests for the safety-net end-to-end preflight layout builder.

These exercise only the CPU-side layout/manifest preparation (no GPU, no model
weights). The GPU inference path is covered by running the driver as a job.
"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ML_MISSING = [m for m in ("numpy", "cv2") if importlib.util.find_spec(m) is None]
if ML_MISSING:
    raise unittest.SkipTest("ML stack not installed: " + ", ".join(ML_MISSING))

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("preflight_e2e", ROOT / "scripts" / "preflight_e2e.py")
pe = importlib.util.module_from_spec(spec)
sys.modules["preflight_e2e"] = pe
spec.loader.exec_module(pe)


def _write_video(path: Path, frames: int, size=(64, 48)):
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, size)
    for i in range(frames):
        frame = np.full((size[1], size[0], 3), i % 256, dtype=np.uint8)
        writer.write(frame)
    writer.release()


class PreflightLayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.baseline = self.tmp / "baseline"
        self.out = self.tmp / "out"
        self.out.mkdir(parents=True)
        for sub in ("original", "rerecorded"):
            for i in (1, 2):
                _write_video(self.baseline / "stage1" / sub / f"{i:06d}.mp4", 5)
        for i in (1, 2, 3):
            _write_video(self.baseline / "stage2" / "videos" / f"{i:06d}.mp4", 6)
        for name in ("OPEN_001", "OPEN_002"):
            _write_video(self.baseline / "stage3" / "videos" / f"{name}.mp4", 7)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stage1_merges_dirs_with_unique_ids(self):
        data_dir, expected = pe.prepare_stage1(self.baseline, self.out)
        videos = sorted(p.name for p in (data_dir / "videos").glob("*.mp4"))
        # 2 original + 2 rerecorded, all unique stems, no collisions
        self.assertEqual(len(videos), 4)
        self.assertEqual(len(set(videos)), 4)
        self.assertEqual(set(expected), {p[:-4] for p in videos})
        self.assertTrue(all(v is None for v in expected.values()))

    def test_stage2_decodes_frames_to_contiguous_jpgs(self):
        data_dir, expected = pe.prepare_stage2(self.baseline, self.out)
        for ident, frames in expected.items():
            jpgs = sorted((data_dir / "images" / ident).glob("*.jpg"))
            self.assertEqual(len(jpgs), len(frames))
            # expected must be the contiguous 0..N-1 frame numbers the model returns
            self.assertEqual(frames, list(range(len(frames))))
            self.assertGreater(len(frames), 0)

    def test_stage3_copies_and_counts_samples(self):
        data_dir, expected = pe.prepare_stage3(self.baseline, self.out)
        self.assertEqual(set(expected), {"OPEN_001", "OPEN_002"})
        for ident, count in expected.items():
            self.assertTrue((data_dir / "videos" / f"{ident}.mp4").exists())
            self.assertGreater(count, 0)

    def test_prepared_manifests_pass_contract_validate(self):
        from harness.contracts import validate

        # Build minimal contract-valid rows from the prepared expected manifests
        _, s2 = pe.prepare_stage2(self.baseline, self.out)
        rows = [{
            "ID": ident,
            "collision_frame": str(frames[0]),
            "entry_frame": str(frames[-1]),
            "evasion_space": "1",
            "entry_side": "LEFT",
        } for ident, frames in s2.items()]
        result = validate("stage2", ["ID", "collision_frame", "entry_frame", "evasion_space", "entry_side"], rows, s2)
        self.assertTrue(result["valid"])


if __name__ == "__main__":
    unittest.main()
