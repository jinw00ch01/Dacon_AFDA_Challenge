"""One-off: fix agent_bridge job wrapper argv (--config must precede the job-run subcommand) in a worktree."""
import sys
from pathlib import Path

path = Path(sys.argv[1]) / "agent_bridge/jobs.py"
old = 'argv = [cfg["python"], "-m", "agent_bridge", "job-run", "--config", str(config_path), "--job", job["job_id"]]'
new = ('# --config is a top-level option, so it must come before the subcommand\n'
       '            argv = [cfg["python"], "-m", "agent_bridge", "--config", str(config_path), "job-run", "--job", job["job_id"]]')
text = path.read_text(encoding="utf-8")
if old not in text:
    raise SystemExit("pattern not found")
path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
print("patched", path)
