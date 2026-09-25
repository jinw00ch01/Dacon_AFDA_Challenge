"""Stage 2 agent-label store: expansion metadata (--meta) and nexar_event merge rules. Stdlib only."""
import argparse
import contextlib
import csv
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("stage2_agent_label", ROOT / "scripts" / "stage2_agent_label.py")
label = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(label)

HUMAN_FIELDS = ["video_id", "source_path", "source_label", "decoded_frames", "fps", "review_status",
                "actual_contact", "lane_entry_suitable", "collision_frame", "entry_frame", "evasion_space", "entry_side"]
META_FIELDS = ["video_id", "source_path", "source_label", "decoded_frames", "fps", "nexar_event_frame"]


def write(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)


def add_args(**kw):
    base = dict(collision_frame=None, entry_frame=None, evasion_space=None, entry_side=None, evidence=[], notes="",
                model="test", guideline="g", meta=[], lane_entry_suitable="no")
    base.update(kw)
    return argparse.Namespace(**base)


class Stage2AgentLabelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.human, self.agent, self.meta = d / "human.csv", d / "agent.csv", d / "ext.csv"
        blank = {k: "" for k in HUMAN_FIELDS}
        write(self.human, HUMAN_FIELDS, [
            {**blank, "video_id": "00001", "source_path": "a/00001.mp4", "source_label": "positive",
             "decoded_frames": "300", "fps": "30"},
            {**blank, "video_id": "00002", "source_path": "a/00002.mp4", "source_label": "positive",
             "decoded_frames": "300", "fps": "30", "review_status": "reviewed", "actual_contact": "yes",
             "lane_entry_suitable": "no", "collision_frame": "150"},
        ])
        write(self.meta, META_FIELDS, [
            {"video_id": "01500", "source_path": "b/01500.mp4", "source_label": "positive", "decoded_frames": "400",
             "fps": "30", "nexar_event_frame": "210.0"},
            {"video_id": "01501", "source_path": "b/01501.mp4", "source_label": "positive", "decoded_frames": "400",
             "fps": "30", "nexar_event_frame": "220"},
            {"video_id": "01502", "source_path": "b/01502.mp4", "source_label": "positive", "decoded_frames": "400",
             "fps": "30", "nexar_event_frame": "230"},
        ])
        self.patches = [(label, "HUMAN", label.HUMAN), (label, "AGENT", label.AGENT)]
        label.HUMAN, label.AGENT = self.human, self.agent

    def tearDown(self):
        for obj, name, value in self.patches:
            setattr(obj, name, value)
        self.tmp.cleanup()

    def run_quiet(self, fn, args):
        with contextlib.redirect_stdout(io.StringIO()):
            fn(args)

    def merged(self, meta):
        out = Path(self.tmp.name) / f"merged_{len(meta)}.csv"
        self.run_quiet(label.merge, argparse.Namespace(out=out, meta=meta))
        with out.open(encoding="utf-8", newline="") as handle:
            return {r["video_id"]: r for r in csv.DictReader(handle)}

    def test_expansion_video_requires_meta(self):
        with self.assertRaises(SystemExit):
            label.add(add_args(video_id="01500", actual_contact="no", confidence=0.9))
        self.run_quiet(label.add, add_args(video_id="01500", actual_contact="no", confidence=0.9,
                                           meta=[str(self.meta)]))
        self.assertIn("01500", label.latest())

    def test_frame_range_uses_expansion_decoded_frames(self):
        with self.assertRaises(SystemExit):
            label.add(add_args(video_id="01500", actual_contact="yes", collision_frame=400, confidence=0.9,
                               meta=[str(self.meta)]))

    def test_merge_without_meta_keeps_human_rows_only(self):
        rows = self.merged([])
        self.assertEqual(set(rows), {"00001", "00002"})
        self.assertEqual(rows["00001"]["label_source"], "none")
        self.assertEqual(rows["00002"]["label_source"], "human")
        self.assertEqual(rows["00002"]["collision_frame_source"], "human")
        self.assertEqual(rows["00002"]["collision_valid"], "1")

    def test_merge_nexar_event_rules(self):
        meta = [str(self.meta)]
        self.run_quiet(label.add, add_args(video_id="01501", actual_contact="yes", confidence=0.8, meta=meta))
        self.run_quiet(label.add, add_args(video_id="01502", actual_contact="yes", collision_frame=240,
                                           confidence=0.8, meta=meta))
        rows = self.merged(meta)
        unverified = rows["01500"]
        self.assertEqual(unverified["label_source"], "nexar_event")
        self.assertEqual(unverified["actual_contact"], "contact_unverified")
        self.assertEqual(unverified["collision_frame"], "210")
        self.assertEqual(unverified["collision_valid"], "0")
        self.assertEqual(unverified["source_path"], "b/01500.mp4")
        filled = rows["01501"]
        self.assertEqual((filled["label_source"], filled["collision_frame"], filled["collision_frame_source"]),
                         ("agent", "220", "nexar_event"))
        self.assertEqual(filled["collision_valid"], "1")
        corrected = rows["01502"]
        self.assertEqual((corrected["collision_frame"], corrected["collision_frame_source"]), ("240", "agent"))

    def test_conflicting_decoded_frames_rejected(self):
        write(self.meta, META_FIELDS, [{"video_id": "00001", "source_path": "x", "source_label": "positive",
                                        "decoded_frames": "299", "fps": "30", "nexar_event_frame": ""}])
        with self.assertRaises(SystemExit):
            label.load_meta([str(self.meta)])


if __name__ == "__main__":
    unittest.main()
