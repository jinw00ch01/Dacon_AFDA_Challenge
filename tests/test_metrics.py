"""Tests for the official scoring module src/afda/metrics.py (decision 10).

Pure stdlib so this runs under the GitHub CI contract job (psutil only).
"""
import importlib.util
import os
import unittest

# Load src/afda/metrics.py directly by path, bypassing the afda package __init__
# (which imports cv2/torch). This keeps the test runnable under the GitHub CI
# contract job, which installs only psutil.
_METRICS_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "afda", "metrics.py")
_spec = importlib.util.spec_from_file_location("afda_metrics_under_test", _METRICS_PATH)
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


class MacroF1Tests(unittest.TestCase):
    def test_perfect(self):
        self.assertEqual(M.macro_f1(["A", "B", "A"], ["A", "B", "A"], ["A", "B"]), 1.0)

    def test_all_wrong_binary(self):
        # every prediction flipped -> both classes F1 0
        self.assertEqual(M.macro_f1(["A", "B"], ["B", "A"], ["A", "B"]), 0.0)

    def test_absent_class_counts_as_zero(self):
        # predict only "A"; class B has tp=0,fp=0,fn=1 -> F1 0; A perfect recall
        # but fp=1 -> F1 = 2*1/(2*1+1+0)=0.6667; mean = (0.6667+0)/2
        f1 = M.macro_f1(["A", "B"], ["A", "A"], ["A", "B"])
        self.assertAlmostEqual(f1, (2 / 3 + 0.0) / 2)

    def test_matches_train_stage3_convention(self):
        # 3-class example computed by hand
        true = ["X", "Y", "Z", "X", "Y"]
        pred = ["X", "Y", "X", "X", "Z"]
        # X: tp2 fp1 fn0 -> 4/5=0.8 ; Y: tp1 fp0 fn1 -> 2/3 ; Z: tp0 fp1 fn1 -> 0
        expected = (0.8 + 2 / 3 + 0.0) / 3
        self.assertAlmostEqual(M.macro_f1(true, pred, ["X", "Y", "Z"]), expected)

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            M.macro_f1(["A"], ["A", "B"], ["A", "B"])


class Stage1Tests(unittest.TestCase):
    def test_constant_predictor_capped_at_half(self):
        # all RERECORDED (e001 behaviour): ORIGINAL F1 0, RERECORDED F1<=1
        true = ["ORIGINAL"] * 5 + ["RERECORDED"] * 5
        pred = ["RERECORDED"] * 10
        s1 = M.stage1_score(true, pred)
        # RERECORDED: tp5 fp5 fn0 -> 10/15=0.6667 ; ORIGINAL 0 -> mean 0.3333
        self.assertAlmostEqual(s1, (2 * 5 / (2 * 5 + 5) + 0) / 2)
        self.assertLessEqual(s1, 0.5)


class AccWithinTests(unittest.TestCase):
    def test_frame_tolerance_at_10fps(self):
        # 10fps: 0.3s tolerance == 3 frames
        acc = M.accuracy_within_frames([30, 34, 27], [30, 30, 30], fps=10.0)
        # diffs 0f(hit), 4f=0.4s(miss), 3f=0.3s(hit) -> 2/3
        self.assertAlmostEqual(acc, 2 / 3)

    def test_none_gt_excluded(self):
        acc = M.accuracy_within([1.0, 5.0], [1.1, None], tol=0.3)
        self.assertEqual(acc, 1.0)  # second video (no event) excluded

    def test_none_pred_is_miss(self):
        acc = M.accuracy_within([None, 2.0], [1.0, 2.0], tol=0.3)
        self.assertEqual(acc, 0.5)

    def test_empty_returns_zero(self):
        self.assertEqual(M.accuracy_within([], []), 0.0)

    def test_per_video_fps(self):
        # video A 10fps, B 30fps; both 6-frame error -> 0.6s / 0.2s
        acc = M.accuracy_within_frames([36, 36], [30, 30], fps=[10.0, 30.0])
        self.assertEqual(acc, 0.5)

    def test_bad_fps_raises(self):
        with self.assertRaises(ValueError):
            M.frame_to_seconds(10, 0)


class Stage2Tests(unittest.TestCase):
    def test_weighted_sum(self):
        s2 = M.stage2_score(collision_acc=1.0, entry_acc=0.0, dir_f1=1.0, evasion_f1=0.0)
        self.assertAlmostEqual(s2, 0.35 * 1 + 0.15 * 1)


class Stage3Tests(unittest.TestCase):
    def test_stopped_rows_excluded_from_steer(self):
        accel_true = ["STOPPED", "ACCELERATING", "CONSTANT"]
        accel_pred = ["STOPPED", "ACCELERATING", "CONSTANT"]
        # steer for the STOPPED row is garbage; it must be dropped
        steer_true = ["RIGHT", "LEFT", "STRAIGHT"]
        steer_pred = ["LEFT", "LEFT", "STRAIGHT"]  # only kept rows matter
        s3 = M.stage3_score(accel_true, accel_pred, steer_true, steer_pred)
        # accel over 4 fixed classes: ACC/CONST/STOPPED perfect, DECELERATING absent
        # -> (1+0+1+1)/4 = 0.75 (absent class penalised, matches train_stage3)
        accel_expected = (1.0 + 0.0 + 1.0 + 1.0) / 4
        # kept steer (LEFT/STRAIGHT) both correct, RIGHT absent -> (1+1+0)/3
        steer_expected = (1.0 + 1.0 + 0.0) / 3
        self.assertAlmostEqual(s3, 0.7 * accel_expected + 0.3 * steer_expected)

    def test_all_stopped_gives_zero_steer_term(self):
        # only STOPPED present over 4 accel classes -> 1/4; steer term 0 (all dropped)
        s3 = M.stage3_score(["STOPPED"], ["STOPPED"], ["LEFT"], ["RIGHT"])
        self.assertAlmostEqual(s3, 0.7 * 0.25 + 0.3 * 0.0)


class OverallTests(unittest.TestCase):
    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(M.W_S1 + M.W_S2 + M.W_S3, 1.0)

    def test_v001_leaderboard_recomputes(self):
        # decision 10: S1 0.5650 S2 0.2060 S3 0.4656 -> overall ~0.382
        overall = M.overall_score(0.5650, 0.2060, 0.4656)
        self.assertAlmostEqual(overall, 0.2 * 0.5650 + 0.4 * 0.2060 + 0.4 * 0.4656)
        self.assertAlmostEqual(overall, 0.38164)


if __name__ == "__main__":
    unittest.main()
