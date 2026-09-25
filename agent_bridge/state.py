"""Shared helpers: role config, strict JSON, and the locked per-PC ledger.

The ledger is the only memory the unattended loop trusts between cycles.
Conversation history is never used as state.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time

from exchange_bridge.__main__ import atomic_json, digest, dirs, load_config, safe_path  # noqa: F401
from exchange_bridge.transport import FOLDERS

ROLES = tuple(FOLDERS)
ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "configs" / "agent_policy.json"


def utc_now():
    return datetime.now(timezone.utc)


def utc_text(moment=None):
    return (moment or utc_now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(text):
    if not isinstance(text, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z", text):
        raise ValueError(f"Expected RFC3339 UTC timestamp ending in Z: {text!r}")
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _reject_constant(value):
    raise ValueError(f"JSON constant not allowed: {value}")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_loads(text):
    return json.loads(text, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)


def strict_load(path, limit=64 * 1024**2):
    path = Path(path)
    if path.stat().st_size > limit:
        raise ValueError(f"JSON file too large: {path.name}")
    return strict_loads(path.read_text(encoding="utf-8-sig"))


def load_policy(role):
    policy = strict_load(POLICY_PATH)
    if policy.get("version") != 1 or role not in policy.get("roles", {}):
        raise ValueError("configs/agent_policy.json is missing this role")
    local = ROOT / "configs" / "local-agent-policy.json"
    merged = dict(policy)
    merged["role"] = dict(policy["roles"][role])
    if local.exists():
        merged["role"].update(strict_load(local).get(role, {}))
    return merged


def agent_root(cfg):
    path = Path(cfg["state_root"]) / "agent"
    path.mkdir(parents=True, exist_ok=True)
    return path


def git(cfg, *args, timeout=60):
    return subprocess.run(["git", *args], cwd=cfg["project_root"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


def head_commit(cfg):
    value = git(cfg, "rev-parse", "HEAD").stdout.strip()
    return value if re.fullmatch(r"[a-f0-9]{40}", value) else None


def tree_clean(cfg):
    result = git(cfg, "status", "--porcelain")
    return result.returncode == 0 and not result.stdout.strip()


EMPTY_LEDGER = {"version": 1, "packets": {}, "sent": {}, "acks": {}, "jobs": {}, "cycles": [],
                "watch": {}, "next_wake": {"mode": "asap", "reason": "first start"},
                "budget": {}, "failures": 0, "loop_heartbeat_utc": None}


@contextmanager
def _file_lock(path, wait_seconds=60):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + wait_seconds
        while True:
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"Timed out waiting for lock {path.name}")
                time.sleep(0.2)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def ledger(cfg):
    """Read-modify-write the ledger under an OS lock shared by loop and CLI calls."""
    root = agent_root(cfg)
    path = root / "ledger.json"
    with _file_lock(root / "ledger.lock"):
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else json.loads(json.dumps(EMPTY_LEDGER))
        for key, value in EMPTY_LEDGER.items():
            data.setdefault(key, json.loads(json.dumps(value)))
        yield data
        atomic_json(path, data)


def read_ledger(cfg):
    path = agent_root(cfg) / "ledger.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else json.loads(json.dumps(EMPTY_LEDGER))
