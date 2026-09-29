"""Feed frame-labeler JSON decisions (a JSON list file) into scripts/stage2_agent_label.py add."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def rel(path):
    p = Path(path)
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def main():
    decisions = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    model = sys.argv[2] if len(sys.argv) > 2 else "claude-opus-5-5"
    for d in decisions:
        cmd = [sys.executable, str(ROOT / "scripts/stage2_agent_label.py"), "add", "--video-id", d["video_id"],
               "--actual-contact", d["actual_contact"], "--lane-entry-suitable", d["lane_entry_suitable"],
               "--confidence", str(d["confidence"]), "--model", model, "--notes", d.get("notes") or ""]
        for meta in sys.argv[3:]:  # expansion metadata CSVs (needs --meta support, pro/s2-ext-labels)
            cmd += ["--meta", meta]
        for key, flag in (("collision_frame", "--collision-frame"), ("entry_frame", "--entry-frame"),
                          ("evasion_space", "--evasion-space"), ("entry_side", "--entry-side")):
            if d.get(key) is not None:
                cmd += [flag, str(d[key])]
        if d.get("evidence"):
            cmd += ["--evidence", *[rel(e) for e in d["evidence"]]]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        print(d["video_id"], "OK" if result.returncode == 0 else "FAIL " + result.stderr.strip())


if __name__ == "__main__":
    main()
