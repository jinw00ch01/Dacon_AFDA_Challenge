import contextlib
import csv
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("s2_human_review", ROOT / "scripts/s2_human_review.py")
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)

FIELDS = ["video_id", "source_path", "source_label", "fps", "decoded_frames", "actual_contact", "lane_entry_suitable",
          "collision_frame", "entry_frame", "evasion_space", "entry_side", "review_status", "notes"]


class S2HumanReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.human = self.base / "human.csv"
        with self.human.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, FIELDS, lineterminator="\n")
            writer.writeheader()
            for vid in ("00082", "00282"):
                writer.writerow({"video_id": vid, "source_path": f"x/{vid}.mp4", "source_label": "positive", "fps": "30.0",
                                 "decoded_frames": "1200", "review_status": "unreviewed", "notes": ""})

    def write_sheet(self, rows, encoding="utf-8-sig"):
        path = self.base / "sheet.csv"
        names = ["video_id"] + review.HUMAN_COLUMNS
        with path.open("w", encoding=encoding, newline="") as handle:
            writer = csv.DictWriter(handle, names)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in names})
        return path

    def rows(self):
        with self.human.open(encoding="utf-8-sig", newline="") as handle:
            return {r["video_id"]: r for r in csv.DictReader(handle)}

    def test_apply_marks_reviewed_and_restores_leading_zeros(self):
        # Excel stripped the zeros (82) and saved CP949 with a Korean note and float-looking numbers.
        sheet = self.write_sheet([{"video_id": "82", "actual_contact": "Yes", "lane_entry_suitable": "yes",
                                   "collision_frame": "575.0", "entry_frame": "560", "evasion_space": "0",
                                   "entry_side": "r", "human_notes": "접촉 확인"}], encoding="cp949")
        self.assertEqual(review.apply(sheet, self.human, backup_dir=self.base / "bk", today="2026-09-26"), 0)
        rows = self.rows()
        got = {k: rows["00082"][k] for k in review.LABEL_FIELDS + ["review_status"]}
        self.assertEqual(got, {"actual_contact": "yes", "lane_entry_suitable": "yes", "collision_frame": "575",
                               "entry_frame": "560", "evasion_space": "0", "entry_side": "RIGHT", "review_status": "reviewed"})
        self.assertIn("human review 2026-09-26: 접촉 확인", rows["00082"]["notes"])
        self.assertEqual(rows["00282"]["review_status"], "unreviewed")  # untouched
        self.assertEqual(len(list((self.base / "bk").iterdir())), 1)

    def test_invalid_rows_write_nothing(self):
        before = self.human.read_bytes()
        for bad in ({"actual_contact": "no", "collision_frame": "575"},
                    {"actual_contact": "yes", "collision_frame": "560", "entry_frame": "575"},
                    {"actual_contact": "yes", "collision_frame": "5000"},
                    {"actual_contact": "maybe"},
                    {"actual_contact": "yes", "evasion_space": "2"},
                    {"actual_contact": "yes", "entry_side": "FRONT"}):
            with self.subTest(bad=bad):
                sheet = self.write_sheet([{"video_id": "00082", **bad}])
                self.assertEqual(review.apply(sheet, self.human, backup_dir=self.base / "bk"), 1)
                self.assertEqual(self.human.read_bytes(), before)

    def test_blank_rows_are_skipped_and_dry_run_writes_nothing(self):
        before = self.human.read_bytes()
        sheet = self.write_sheet([{"video_id": "00082"}, {"video_id": "00282", "actual_contact": "uncertain"}])
        self.assertEqual(review.apply(sheet, self.human, dry_run=True, backup_dir=self.base / "bk"), 0)
        self.assertEqual(self.human.read_bytes(), before)
        self.assertEqual(review.apply(sheet, self.human, backup_dir=self.base / "bk"), 0)
        rows = self.rows()
        self.assertEqual((rows["00082"]["review_status"], rows["00282"]["review_status"]), ("unreviewed", "reviewed"))

    def test_korean_notes_print_on_a_cp1252_stdout(self):
        # GitHub's English Windows runner pipes stdout as cp1252; printing the Korean note used to raise there.
        sheet = self.write_sheet([{"video_id": "00282", "actual_contact": "uncertain", "human_notes": "접촉 확인"}])
        stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(review.apply(sheet, self.human, dry_run=True, backup_dir=self.base / "bk"), 0)
        stdout.flush()
        self.assertIn("접촉 확인", stdout.detach().getvalue().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
