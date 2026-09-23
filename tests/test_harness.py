import tempfile
import unittest
from pathlib import Path
import zipfile
import sys
import json
from types import SimpleNamespace
from unittest.mock import patch

from harness.contracts import SCHEMAS, integer, validate
from harness.__main__ import MODELS, check_source, validate_zip
from harness.__main__ import execute
from harness.__main__ import sha, verify_handoff, bundle


class ContractTests(unittest.TestCase):
    def test_nonfinite_negative_fraction_boolean_rejected(self):
        for value in ("nan", "inf", -1, 1.2, None, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                integer(value)

    def test_stage1_complete_ids(self):
        row = {"ID": "a", "answer": "ORIGINAL"}
        validate("stage1", SCHEMAS["stage1"], [row], {"a": None})
        for rows in ([], [row, row], [{"ID": "b", "answer": "ORIGINAL"}]):
            with self.assertRaises(ValueError):
                validate("stage1", SCHEMAS["stage1"], rows, {"a": None})

    def test_stage2_preserves_noncontiguous_original_frame_numbers(self):
        row = dict(ID="a", collision_frame=20, entry_frame=10, evasion_space=0, entry_side="LEFT")
        validate("stage2", SCHEMAS["stage2"], [row], {"a": [10, 20, 30]})
        row["collision_frame"] = 1
        with self.assertRaises(ValueError):
            validate("stage2", SCHEMAS["stage2"], [row], {"a": [10, 20, 30]})

    def test_stage3_all_samples_and_stopped_steer_required(self):
        rows = [dict(ID="a", sample_index=i, accel_label="STOPPED", steer_label="STRAIGHT") for i in range(2)]
        validate("stage3", SCHEMAS["stage3"], rows, {"a": 2})
        with self.assertRaises(ValueError):
            validate("stage3", SCHEMAS["stage3"], rows[:1], {"a": 2})
        rows[0]["steer_label"] = ""
        with self.assertRaises(ValueError):
            validate("stage3", SCHEMAS["stage3"], rows, {"a": 2})

    def test_column_drift_and_empty_manifest(self):
        with self.assertRaises(ValueError):
            validate("stage1", ["ID", "label"], [], {"a": None})
        with self.assertRaises(ValueError):
            validate("stage1", SCHEMAS["stage1"], [], {})

    def test_invalid_expected_manifest(self):
        with self.assertRaises(ValueError):
            validate("stage3", SCHEMAS["stage3"], [], {"a": 0})
        with self.assertRaises(ValueError):
            validate("stage2", SCHEMAS["stage2"], [], {"a": [0, 0]})

    def test_wrong_signature(self):
        with self.assertRaises(ValueError):
            check_source("def predict_stage1(): pass")

    def test_zip_structure_and_traversal(self):
        source = "\n".join(f"def predict_stage{s}(data_dir, model_dir): pass" for s in (1, 2, 3))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("inference.py", source)
                archive.writestr("requirements.txt", "")
                for name in MODELS:
                    archive.writestr("model/" + name, b"TEST FIXTURE, NOT WEIGHTS")
            self.assertIn("sha256", validate_zip(path))
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr("model/../../outside.txt", "bad")
            with self.assertRaises(ValueError):
                validate_zip(path)


class SupervisorTests(unittest.TestCase):
    def invoke(self, temporary, code, timeout=5, kind="cpu", allow=True):
        root = Path(temporary)
        run = root / "run"
        run.mkdir(exist_ok=True)
        args = SimpleNamespace(child_command=[sys.executable, "-c", code], timeout=timeout,
                               kind=kind, profile="ultra5060")
        config = dict(allow_training=allow, torch_threads=1, seed=42, device="cpu", ram_budget_gib=1)
        with patch("harness.__main__.ROOT", root):
            return execute(args, config, run)

    def test_child_success_and_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.invoke(tmp, "print('recorded')")
            self.assertEqual(result["returncode"], 0)
            self.assertIn("recorded", (Path(tmp) / "run/stdout.log").read_text())

    def test_failed_child_propagates(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(RuntimeError):
            self.invoke(tmp, "raise RuntimeError('expected failure')")

    def test_timeout_releases_gpu_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "timeout"):
                self.invoke(tmp, "import time; time.sleep(5)", timeout=0.1, kind="gpu")
            self.assertFalse((Path(tmp) / "work/gpu.lock").exists())

    def test_cpu_role_rejects_gpu_job(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            self.invoke(tmp, "print('must not run')", kind="gpu", allow=False)

    def test_existing_gpu_lock_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "work/gpu.lock"
            lock.parent.mkdir()
            lock.write_text("owned by another run")
            with self.assertRaises(FileExistsError):
                self.invoke(tmp, "print('must not run')", kind="gpu")
            self.assertEqual(lock.read_text(), "owned by another run")

    def test_ram_budget_stops_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            run.mkdir()
            args = SimpleNamespace(child_command=[sys.executable, "-c", "import time; time.sleep(5)"],
                                   timeout=5, kind="cpu", profile="pro360")
            config = dict(allow_training=False, torch_threads=1, seed=42, device="cpu", ram_budget_gib=0.00001)
            with patch("harness.__main__.ROOT", root), self.assertRaisesRegex(RuntimeError, "RAM budget"):
                execute(args, config, run)


class HandoffTests(unittest.TestCase):
    def test_bundle_includes_bootstrap_dependencies_excludes_local_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("README.md", "AGENTS.md", ".gitignore", "overview.md",
                         "evaluation.md", "data_description.md", "code submission.html", "Baseline/requirements.txt",
                         "requirements/local-common.txt", "configs/local-private.json"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture", encoding="utf-8")
            output = root / "handoff.zip"
            args = SimpleNamespace(output=output, include_samples=False)
            with patch("harness.__main__.ROOT", root):
                bundle(args, None, None)
            with zipfile.ZipFile(output) as archive:
                manifest = json.loads(archive.read("handoff_manifest.json"))
                self.assertIn("requirements/local-common.txt", manifest)
                self.assertIn("data_description.md", manifest)
                self.assertIn("requirements/local-common.txt", archive.namelist())
                self.assertNotIn("configs/local-private.json", archive.namelist())

    def test_round_trip_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file = root / "example.txt"
            file.write_text("original")
            (root / "handoff_manifest.json").write_text(json.dumps({"example.txt": sha(file)}))
            with patch("harness.__main__.ROOT", root):
                self.assertEqual(verify_handoff(None, None, None)["verified_files"], 1)
                file.write_text("changed")
                with self.assertRaises(ValueError):
                    verify_handoff(None, None, None)

    def test_handoff_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "handoff_manifest.json").write_text(json.dumps({"../outside.txt": "anything"}))
            with patch("harness.__main__.ROOT", root), self.assertRaises(ValueError):
                verify_handoff(None, None, None)

    def test_handoff_normalizes_root_before_containment_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'nested').mkdir()
            file = root / 'example.txt'
            file.write_text('original')
            (root / 'handoff_manifest.json').write_text(json.dumps({'example.txt': sha(file)}))
            with patch('harness.__main__.ROOT', root / 'nested' / '..'):
                self.assertEqual(verify_handoff(None, None, None)['verified_files'], 1)


if __name__ == "__main__":
    unittest.main()
