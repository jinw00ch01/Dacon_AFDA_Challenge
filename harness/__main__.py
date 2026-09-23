"""Run with python -m harness. Commands write immutable per-run evidence."""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import time
import traceback
import uuid
import zipfile
from datetime import datetime, timezone

from .contracts import SCHEMAS, validate

ROOT = Path(__file__).resolve().parents[1]
MODELS = ("stage1/best.pt", "stage2/best.pt", "stage2/resnet18-f37072fd.pth", "stage3/best.pt")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def source_hashes():
    paths = [*ROOT.glob("*.md"), *ROOT.glob("*.html"), *ROOT.glob("Baseline/*.ipynb"),
             *ROOT.glob("harness/*.py"), *ROOT.glob("configs/*.json"),
             *ROOT.glob("scripts/*.ps1"), *ROOT.glob("scripts/*.py"), *ROOT.glob("requirements/*.txt"),
             *ROOT.glob("src/*.py"), *ROOT.glob("tests/*.py"), *ROOT.glob("docs/*.md"), *ROOT.glob("docs/*.csv"),
             *ROOT.glob("environment/*.py"), *ROOT.glob("environment/Dockerfile"), *ROOT.glob(".github/workflows/*.yml")]
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}


def check_source(source):
    tree = ast.parse(source)
    definitions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for name in ("predict_stage1", "predict_stage2", "predict_stage3"):
        if name not in definitions or [a.arg for a in definitions[name].args.args] != ["data_dir", "model_dir"]:
            raise ValueError(f"Missing/incorrect signature: {name}(data_dir, model_dir)")
    return tree


def extract(args, config, run):
    notebook = next(ROOT.glob("Baseline/*Inference*.ipynb"))
    data = json.loads(notebook.read_text(encoding="utf-8"))
    parts = ["".join(c["source"]) for c in data["cells"] if c["cell_type"] == "code"
             and "# BASELINE_INFERENCE_PART" in "".join(c["source"])]
    if len(parts) != 4:
        raise ValueError("Expected exactly four baseline inference cells")
    source = "\n\n".join(p.rstrip() for p in parts) + "\n"
    check_source(source)
    out = ROOT / "src/baseline_inference.py"
    out.parent.mkdir(exist_ok=True)
    if out.exists() and out.read_text(encoding="utf-8") != source:
        raise ValueError("Extraction would overwrite changes; preserve/rename edited file first")
    out.write_text(source, encoding="utf-8")
    return {"file": str(out), "sha256": sha(out), "notebook_sha256": sha(notebook), "cells": 4,
            "note": "Unmodified reference only; not a memory-tuned production inference implementation"}


def doctor(args, config, run):
    import torch
    import torchvision
    import cv2
    import psutil
    expected = {"torch": "2.8.0", "torchvision": "0.23.0", "numpy": "1.26.4", "pandas": "2.2.2",
                "opencv-python-headless": "4.10.0.84", "pillow": "10.4.0", "tqdm": "4.66.5", "psutil": "6.1.1"}
    installed = {key: importlib.metadata.version(key) for key in expected}
    errors = [f"Version mismatch: {key}={installed[key]} expected {value}" for key, value in expected.items()
              if installed[key].split("+")[0] != value]
    disk = shutil.disk_usage(ROOT)
    if disk.free < config["min_free_disk_gib"] * 1024**3:
        errors.append("Insufficient free disk space")
    cuda = {"available": torch.cuda.is_available(), "runtime": torch.version.cuda}
    if config["device"] == "cuda":
        if not cuda["available"]:
            errors.append("CUDA required for Ultra profile")
        else:
            cuda.update(name=torch.cuda.get_device_name(), capability=torch.cuda.get_device_capability(),
                        total_memory_gib=torch.cuda.get_device_properties(0).total_memory / 1024**3)
            value = torch.ones((32, 32), device="cuda")
            assert (value @ value)[0, 0].item() == 32
            torch.cuda.synchronize()
            cuda["matrix_test"] = "passed"
            if torch.version.cuda != "12.8":
                errors.append("GPU profile requires CUDA 12.8 PyTorch wheels")
    result = {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
              "host": platform.node(), "expected_host": config["expected_host"],
              "host_matches": (platform.node().upper() == config["expected_host"].upper()
                               if config.get("expected_host") else None),
              "packages": installed, "cuda": cuda, "disk_free_gib": disk.free / 1024**3,
              "ram_total_gib": psutil.virtual_memory().total / 1024**3,
              "ram_available_gib": psutil.virtual_memory().available / 1024**3,
              "errors": errors, "os_matches_evaluation": False}
    write_json(run / "environment.json", result)
    frozen = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True, check=True)
    (run / "pip-freeze.txt").write_text(frozen.stdout, encoding="utf-8")
    if errors:
        raise ValueError("; ".join(errors))
    return result


def inventory(args, config, run):
    import cv2
    results = {"videos": [], "labels": {}, "notebooks": [], "warnings": []}
    for notebook in sorted(ROOT.glob("Baseline/*.ipynb")):
        nb = json.loads(notebook.read_text(encoding="utf-8"))
        cells = []
        for i, cell in enumerate(nb["cells"]):
            code = "".join(cell.get("source", []))
            if cell["cell_type"] == "code" and code.strip() and not code.lstrip().startswith("%"):
                ast.parse(code)
            cells.append({"index": i, "type": cell["cell_type"], "lines": len(code.splitlines())})
        results["notebooks"].append({"path": notebook.name, "sha256": sha(notebook), "cells": cells})
    for label_file in sorted(ROOT.glob("Baseline/data/*/labels.csv")):
        with label_file.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            columns = reader.fieldnames
        if not rows:
            raise ValueError(f"Empty labels: {label_file}")
        stage = label_file.parent.name
        counts = {}
        for field in ("label", "accel_label", "steer_label", "evasion_space", "entry_side", "t_entry"):
            if field in columns:
                counts[field] = {value: sum(row[field] == value for row in rows) for value in sorted({row[field] for row in rows})}
        keys = [(row["ID"], row.get("sample_index")) for row in rows]
        if len(set(keys)) != len(keys):
            raise ValueError(f"Duplicate label keys: {stage}")
        for row in rows:
            path = label_file.parent / row["path"] if "path" in row else label_file.parent / "videos" / (row["ID"] + ".mp4")
            if not path.is_file():
                raise ValueError(f"Missing source video: {path}")
        results["labels"][stage] = {"rows": len(rows), "ids": len({r["ID"] for r in rows}), "columns": columns,
                                    "counts": counts, "sha256": sha(label_file)}
    for path in sorted(ROOT.glob("Baseline/data/**/*.mp4")):
        cap = cv2.VideoCapture(str(path))
        try:
            count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            head, _ = cap.read()
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, count - 1))
            tail, _ = cap.read()
            if not head or not tail or count <= 0 or fps <= 0:
                raise ValueError(f"Undecodable source video: {path}")
            results["videos"].append({"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
                                      "sha256": sha(path), "frames_reported": count, "fps_reported": fps,
                                      "width": width, "height": height, "duration_estimate_s": count / fps,
                                      "head_tail_decode": True, "full_decode_checked": False})
        finally:
            cap.release()
    results["warnings"] = ["Stage 2: entry/evasion/side labels -1 are missing labels, never valid targets.",
                            "Stage 3: sparse source labels; no interpolation into ground truth.",
                            "Frame counts and FPS here are container metadata, not a VFR timestamp mapping."]
    groups = {}
    for video in results["videos"]:
        groups.setdefault(video["sha256"], []).append(video["path"])
    results["duplicate_content_groups"] = [paths for paths in groups.values() if len(paths) > 1]
    with (ROOT / "Baseline/data/stage3/labels.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    timing = []
    for video in results["videos"]:
        if "/stage3/" not in video["path"]:
            continue
        selected = [r for r in rows if r["ID"] == Path(video["path"]).stem and float(r["time_seconds"]) > 0]
        inferred = sorted({round(float(r["frame_index"]) / float(r["time_seconds"]), 6) for r in selected})
        mismatch = any(abs(fps - video["fps_reported"]) > 0.1 for fps in inferred)
        timing.append({"ID": Path(video["path"]).stem, "label_implied_fps": inferred,
                       "container_fps": video["fps_reported"], "mismatch": mismatch})
    results["stage3_timing_audit"] = timing
    if any(r["mismatch"] for r in timing):
        results["warnings"].append("BLOCK TRAINING DATA PROMOTION: Stage 3 label timing differs from container FPS. Resolve timebase first.")
    write_json(run / "dataset_manifest.json", results)
    return {"videos": len(results["videos"]), "labels": results["labels"], "notebooks": len(results["notebooks"]),
            "timing_mismatches": sum(r["mismatch"] for r in timing), "warnings": results["warnings"],
            "manifest": str(run / "dataset_manifest.json")}


def smoke(args, config, run):
    import torch
    from torchvision.models import resnet18
    torch.manual_seed(config["seed"])
    torch.set_num_threads(config["torch_threads"])
    device = config["device"]
    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA unavailable")
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()
    model = resnet18(weights=None).to(device).eval()
    with torch.inference_mode():
        out = model(torch.zeros(1, 3, 224, 224, device=device))
    assert out.shape == (1, 1000) and torch.isfinite(out).all()
    del model, out
    models = ["resnet18"]
    if device == "cuda":
        from torchvision.models.video import mvit_v2_s
        model = mvit_v2_s(weights=None).to(device).eval()
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            out = model(torch.zeros(config["batch_size"], 3, 16, 224, 224, device=device))
        assert out.shape == (config["batch_size"], 400) and torch.isfinite(out).all()
        torch.cuda.synchronize()
        models.append("mvit_v2_s")
    return {"device": device, "models": models, "seconds": time.monotonic() - started,
            "max_allocated_gib": torch.cuda.max_memory_allocated() / 1024**3 if device == "cuda" else None,
            "scope": "Synthetic forward only; no optimizer/backward, trained weights, accuracy, or full inference validation"}


def check(args, config, run):
    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    with args.csv.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        result = validate(args.stage, reader.fieldnames, list(reader), expected)
    return result


def validate_zip(path):
    required = {"inference.py", "requirements.txt", *("model/" + p for p in MODELS)}
    if path.stat().st_size > 10_000_000_000:
        raise ValueError("ZIP exceeds conservative 10 GB limit")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP entries")
        if required - set(names):
            raise ValueError(f"Missing required entries: {sorted(required - set(names))}")
        for name in names:
            parts = PurePosixPath(name).parts
            if not parts or name.startswith("/") or ".." in parts or "\\" in name or ":" in name:
                raise ValueError(f"Unsafe ZIP entry: {name}")
            if parts[0] not in {"inference.py", "requirements.txt", "model"}:
                raise ValueError(f"Unexpected top-level ZIP entry: {name}")
            if parts[0] != "model" and name not in {"inference.py", "requirements.txt"}:
                raise ValueError(f"Unexpected nested entry: {name}")
        infos = archive.infolist()
        total = sum(info.file_size for info in infos)
        if total > 32_000_000_000:
            raise ValueError("Unpacked content exceeds conservative 32 GB limit")
        for name in required:
            if name != "requirements.txt" and archive.getinfo(name).file_size == 0:
                raise ValueError(f"Empty required file: {name}")
        check_source(archive.read("inference.py").decode("utf-8-sig"))
        broken = archive.testzip()
        if broken:
            raise ValueError(f"ZIP CRC failed: {broken}")
    return {"sha256": sha(path), "zip_bytes": path.stat().st_size, "unpacked_bytes": total,
            "scope": "Structure/CRC/signatures only; model compatibility and offline runtime not proven"}


def package(args, config, run):
    check_source(args.inference.read_text(encoding="utf-8-sig"))
    for name in MODELS:
        if not (args.model_dir / name).is_file():
            raise ValueError(f"Missing checkpoint: {name}; training must happen before packaging")
    if args.output.exists():
        raise ValueError("Output already exists; use a new versioned filename")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.write(args.inference, "inference.py")
            archive.write(ROOT / "requirements/submission.txt", "requirements.txt")
            for name in MODELS:
                archive.write(args.model_dir / name, "model/" + name)
        result = validate_zip(temporary)
        temporary.rename(args.output)
    finally:
        temporary.unlink(missing_ok=True)
    result["file"] = str(args.output.resolve())
    return result


def bundle(args, config, run):
    """Portable source handoff; never includes venv, pc_info, weights or run logs."""
    if args.output.exists():
        raise ValueError("Handoff already exists; use a new filename")
    files = [ROOT / p for p in ("README.md", "AGENTS.md", ".gitignore", "overview.md", "evaluation.md", "code submission.html")]
    if (ROOT / "data_description.md").is_file():
        files.append(ROOT / "data_description.md")
    for directory in ("harness", "configs", "scripts", "requirements", "tests", "docs", "src"):
        files.extend(p for p in (ROOT / directory).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts
                     and not (directory == "configs" and p.name.startswith("local")))
    files.extend(ROOT.glob("Baseline/*.ipynb"))
    files.extend(ROOT.glob("sample_*.png"))
    files.append(ROOT / "Baseline/requirements.txt")
    if args.include_samples:
        files.extend(p for p in (ROOT / "Baseline/data").rglob("*") if p.is_file())
    manifest = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(set(files))}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "x", zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for name in manifest:
            archive.write(ROOT / name, name)
        archive.writestr("handoff_manifest.json", json.dumps(manifest, indent=2))
    return {"file": str(args.output.resolve()), "files": len(manifest), "sha256": sha(args.output),
            "samples_included": args.include_samples}


def verify_handoff(args, config, run):
    root = ROOT.resolve()
    manifest = json.loads((root / "handoff_manifest.json").read_text(encoding="utf-8"))
    errors = []
    for name, digest in manifest.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or sha(path) != digest:
            errors.append(name)
    if errors:
        raise ValueError(f"Handoff mismatch: {errors}")
    return {"verified_files": len(manifest)}


def execute(args, config, run):
    """Supervise one process tree; CPU/GPU role is declared, not a sandbox."""
    import psutil
    command = list(args.child_command)
    if command and command[0] == "--":
        command.pop(0)
    if not command or args.timeout <= 0:
        raise ValueError("Provide a command after -- and a positive timeout")
    if args.kind == "gpu" and not config["allow_training"]:
        raise ValueError("GPU/training jobs belong on Ultra, not Pro 360")
    lock = ROOT / "work/gpu.lock"
    acquired = False
    child = None
    try:
        if args.kind == "gpu":
            lock.parent.mkdir(exist_ok=True)
            with lock.open("x", encoding="utf-8") as handle:
                json.dump({"supervisor_pid": os.getpid(), "host": platform.node(), "run": str(run)}, handle)
            acquired = True
        environment = os.environ.copy()
        environment.update(OMP_NUM_THREADS=str(config["torch_threads"]), MKL_NUM_THREADS=str(config["torch_threads"]),
                           PYTHONHASHSEED=str(config["seed"]), AFDA_PROFILE=args.profile,
                           AFDA_RUN_DIR=str(run), PYTHONUNBUFFERED="1")
        if config["device"] == "cpu":
            environment["CUDA_VISIBLE_DEVICES"] = ""
        started = time.monotonic()
        peak_rss = 0
        failure = None
        with (run / "stdout.log").open("w", encoding="utf-8") as out, (run / "stderr.log").open("w", encoding="utf-8") as err:
            child = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=out, stderr=err)
            process = psutil.Process(child.pid)
            while child.poll() is None:
                try:
                    family = [process, *process.children(recursive=True)]
                    rss = sum(p.memory_info().rss for p in family if p.is_running())
                    peak_rss = max(peak_rss, rss)
                    if rss > config["ram_budget_gib"] * 1024**3:
                        failure = "Process tree exceeded configured RAM budget"
                    if time.monotonic() - started > args.timeout:
                        failure = "Process tree exceeded timeout"
                    if failure:
                        for p in reversed(family):
                            try:
                                p.kill()
                            except psutil.NoSuchProcess:
                                pass
                        child.wait(timeout=15)
                        break
                except psutil.NoSuchProcess:
                    pass
                time.sleep(0.2)
        result = {"argv": command, "returncode": child.returncode, "peak_process_tree_rss_gib": peak_rss / 1024**3,
                  "seconds": time.monotonic() - started, "failure": failure,
                  "note": "RAM sampling every 0.2s; GPU VRAM/cache budgets are advisory, not hard limits"}
        write_json(run / "process.json", result)
        if failure or child.returncode:
            raise RuntimeError(failure or f"Child exited with code {child.returncode}; see stderr.log")
        return result
    finally:
        if child is not None and child.poll() is None:
            try:
                process = psutil.Process(child.pid)
                for p in reversed([process, *process.children(recursive=True)]):
                    try:
                        p.kill()
                    except psutil.NoSuchProcess:
                        pass
                child.wait(timeout=15)
            except psutil.NoSuchProcess:
                pass
        if acquired:
            lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "inventory", "extract", "smoke", "check", "package", "preflight", "bundle", "verify-handoff", "execute"):
        p = sub.add_parser(name)
        p.add_argument("--profile", choices=["pro360", "ultra5060"], default="ultra5060")
        if name == "check":
            p.add_argument("--stage", choices=SCHEMAS, required=True)
            p.add_argument("--csv", type=Path, required=True)
            p.add_argument("--expected", type=Path, required=True)
        if name == "package":
            p.add_argument("--inference", type=Path, required=True)
            p.add_argument("--model-dir", type=Path, required=True)
        if name in {"package", "bundle"}:
            p.add_argument("--output", type=Path, required=True)
        if name == "bundle":
            p.add_argument("--include-samples", action="store_true")
        if name == "preflight":
            p.add_argument("--zip", type=Path, required=True)
        if name == "execute":
            p.add_argument("--kind", choices=["cpu", "gpu"], required=True)
            p.add_argument("--timeout", type=float, default=3600)
            p.add_argument("child_command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    config = json.loads((ROOT / "configs" / (args.profile + ".json")).read_text(encoding="utf-8"))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + args.command + "_" + uuid.uuid4().hex[:8]
    run = ROOT / "runs" / run_id
    run.mkdir(parents=True)
    metadata = {"run_id": run_id, "started_utc": datetime.now(timezone.utc).isoformat(), "host": platform.node(),
                "command": sys.argv, "profile": config, "source_sha256": source_hashes(), "python": sys.executable}
    metadata["python_version"] = sys.version
    metadata["runtime_packages"] = {}
    for package_name in ("torch", "torchvision", "numpy", "pandas", "opencv-python-headless", "opencv-python", "psutil"):
        try:
            metadata["runtime_packages"][package_name] = importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            pass
    started = time.monotonic()
    try:
        metadata["result"] = validate_zip(args.zip) if args.command == "preflight" else globals()[args.command.replace("-", "_")](args, config, run)
        metadata["status"] = "passed"
        status = 0
    except Exception as error:
        metadata["status"] = "failed"
        metadata["error"] = f"{type(error).__name__}: {error}"
        (run / "traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        status = 1
    metadata["elapsed_s"] = time.monotonic() - started
    write_json(run / "run.json", metadata)
    print(json.dumps({"status": metadata["status"], "run": str(run),
                      "result": metadata.get("result"), "error": metadata.get("error")}, ensure_ascii=False, indent=2))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
