"""The unattended wake loop: import packets, run jobs, and start one Claude cycle at a time.

A cycle starts only for a concrete reason (new packet, finished job, changed human
input, the agent's own next_wake request, or a heartbeat). Each reason is delivered
once; a failed cycle keeps its reasons and retries with exponential backoff.
"""
from __future__ import annotations

from datetime import timedelta
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

from . import jobs, packets
from .state import ROOT, _file_lock, agent_root, atomic_json, ledger, load_policy, read_ledger, utc_now, utc_text, parse_utc

WATCH = {
    "pro360": ["data/derived/nexar_subset_v1/stage2_review_with_metadata.csv",
               "data/derived/comma_subset_v1/s23_capture_ready.csv", "data/captures/s23", "data/derived/labels/human"],
    "ultra5060": ["data/derived/peer_reviews/latest.json", "data/derived/labels/human"],
}
REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "What changed this cycle, with evidence paths"},
        "actions": {"type": "array", "items": {"type": "string"}},
        "packets_published": {"type": "array", "items": {"type": "string"}},
        "jobs_requested": {"type": "array", "items": {"type": "string"}},
        "human_actions": {"type": "array", "items": {"type": "string"},
                          "description": "Only things a human must physically do (upload, capture, admin install)"},
        "blocked": {"type": "array", "items": {"type": "string"}},
        "next_wake": {
            "type": "object",
            "properties": {"mode": {"type": "string", "enum": ["asap", "on_event", "after_minutes"]},
                           "minutes": {"type": ["integer", "null"]}, "reason": {"type": "string"}},
            "required": ["mode", "reason"],
        },
        "submission_candidate": {
            "type": ["object", "null"],
            "properties": {"path": {"type": "string"}, "sha256": {"type": "string"}, "evidence": {"type": "string"}},
        },
    },
    "required": ["summary", "actions", "human_actions", "next_wake"],
}
AUTONOMY_NOTE = (
    "You are running UNATTENDED as the AFDA {role} agent (cycle {cycle}). No human will read or answer "
    "questions during this run: never ask for confirmation, decide within the rules in CLAUDE.md and your role file, "
    "and record anything that truly needs a human in human_actions. Keep every shell command under 10 minutes; "
    "queue longer work with `python -m agent_bridge job start`. Finish by returning the JSON report."
)


def resolve_claude(policy):
    configured = policy["role"].get("claude_command")
    if configured:
        return list(configured)
    candidates = []
    shim = shutil.which("claude")
    if shim:
        base = Path(shim).parent
        candidates += [base / "node_modules/@anthropic-ai/claude-code/bin/claude.exe", Path(shim)]
    candidates += [Path.home() / ".local/bin/claude.exe", Path(os.environ.get("APPDATA", "")) / "npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe"]
    for path in candidates:
        if path.suffix.lower() in {".exe", ""} and path.is_file():
            return [str(path)]
    raise FileNotFoundError("claude executable not found; set roles.<role>.claude_command in configs/local-agent-policy.json")


def _stamp(root, name):
    path = root / name
    if path.is_file():
        info = path.stat()
        return [1, info.st_size, info.st_mtime_ns]
    if path.is_dir():
        files = [p for p in path.rglob("*") if p.is_file() and not p.name.endswith(".partial")]
        return [len(files), sum(p.stat().st_size for p in files), max((p.stat().st_mtime_ns for p in files), default=0)]
    return None


def watch_inputs(cfg, book, stable_seconds=60):
    """Human/peer inputs that changed and have been stable for a while."""
    root = Path(cfg["project_root"])
    changed = []
    now = time.time()
    for name in WATCH[cfg["role"]]:
        stamp = _stamp(root, name)
        entry = book["watch"].setdefault(name, {"seen": stamp, "stamp": stamp, "since": now})
        if entry.get("stamp") != stamp:
            entry.update(stamp=stamp, since=now)
        elif stamp != entry.get("seen") and now - entry["since"] >= stable_seconds:
            changed.append(name)
    return changed


def _allowed_after(book, policy):
    backoff = policy.get("backoff", {})
    if not book["failures"] or not book["cycles"]:
        return None
    delay = min(backoff.get("max_seconds", 3600), backoff.get("base_seconds", 120) * 2 ** (book["failures"] - 1))
    return parse_utc(book["cycles"][-1]["ended_utc"]) + timedelta(seconds=delay)


def wake_reasons(cfg, policy, book):
    """Return (reasons, blocked_reason). Reasons are concrete events; blocked explains a skip."""
    now = utc_now()
    role = policy["role"]
    stop_after = policy.get("stop_after_utc")
    if stop_after and now > parse_utc(stop_after):
        return [], "competition window closed"
    if (agent_root(cfg) / "PAUSE").exists():
        return [], "paused by PAUSE file"
    today = book["budget"].setdefault(now.strftime("%Y-%m-%d"), {"cycles": 0, "usd": 0.0})
    if today["cycles"] >= role["max_cycles_per_day"] or today["usd"] >= role["max_usd_per_day"]:
        return [], "daily cycle/USD budget exhausted"
    allowed = _allowed_after(book, policy)
    if allowed and now < allowed:
        return [], f"backoff after failures until {utc_text(allowed)}"
    last_end = parse_utc(book["cycles"][-1]["ended_utc"]) if book["cycles"] else None
    if last_end and (now - last_end).total_seconds() < role["min_gap_seconds"]:
        return [], "minimum gap between cycles"
    reasons = []
    for packet_id, entry in book["packets"].items():
        if entry.get("status") == "imported" and not entry.get("handled"):
            reasons.append({"type": "packet", "packet_id": packet_id, "kind": entry["kind"],
                            "subject": entry.get("subject"), "experiment_id": entry.get("experiment_id"),
                            "path": entry["local_path"]})
        elif entry.get("status") == "quarantined" and not entry.get("handled"):
            reasons.append({"type": "quarantined_packet", "packet_id": packet_id, "detail": entry.get("detail")})
    for job in book["jobs"].values():
        if job["status"] in {"succeeded", "failed", "lost", "cancelled"} and not job.get("reported"):
            reasons.append({"type": "job_finished", "job_id": job["job_id"], "name": job["name"], "status": job["status"],
                            "run_dir": job.get("run_dir"), "error": job.get("error")})
    for name in watch_inputs(cfg, book):
        reasons.append({"type": "input_changed", "path": name})
    wake = book.get("next_wake") or {"mode": "asap"}
    if not reasons:
        if wake["mode"] == "asap":
            reasons.append({"type": "scheduled", "reason": wake.get("reason", "agent requested asap")})
        elif wake["mode"] == "after_minutes" and last_end and now >= last_end + timedelta(minutes=wake.get("minutes") or 30):
            reasons.append({"type": "scheduled", "reason": wake.get("reason", "timer")})
        elif last_end is None or now >= last_end + timedelta(minutes=role["heartbeat_minutes"]):
            reasons.append({"type": "heartbeat", "reason": "periodic check-in"})
    return reasons, None


def guard_selftest(cfg):
    """The PreToolUse guard must deny an obviously destructive command before any cycle runs."""
    python = shutil.which("python") or cfg["python"]
    event = {"tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}}
    try:
        result = subprocess.run([python, str(ROOT / ".claude/hooks/guard.py")], input=json.dumps(event), capture_output=True,
                                text=True, timeout=30, env={**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT), "AFDA_AUTONOMOUS": "1"},
                                creationflags=0x08000000 if os.name == "nt" else 0)
        decision = json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]
        return decision == "deny"
    except Exception:
        return False


def _context(cfg, policy, book, reasons, cycle_id):
    recent = [{"cycle_id": c["cycle_id"], "ended_utc": c["ended_utc"], "status": c["status"],
               "summary": (c.get("report") or {}).get("summary"), "next_wake": (c.get("report") or {}).get("next_wake")}
              for c in book["cycles"][-5:]]
    now = utc_now()
    return {
        "role": cfg["role"], "cycle_id": cycle_id, "now_utc": utc_text(now),
        "now_kst": (now + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M KST"),
        "deadline_utc": policy.get("deadline_utc"),
        "hours_to_deadline": round((parse_utc(policy["deadline_utc"]) - now).total_seconds() / 3600, 1) if policy.get("deadline_utc") else None,
        "wake_reasons": reasons, "recent_cycles": recent,
        "jobs": jobs.summary(cfg, 8),
        "unacked_sent_packets": [pid for pid, s in book["sent"].items() if pid not in book["acks"]][-10:],
        "budget_today": book["budget"].get(now.strftime("%Y-%m-%d")),
        "exchange_config": str(Path(cfg["project_root"]) / "configs/local-exchange.json"),
    }


def start_cycle(cfg, policy, reasons):
    cycle_id = uuid.uuid4().hex[:12]
    session_id = str(uuid.uuid4())
    folder = agent_root(cfg) / "cycles" / cycle_id
    folder.mkdir(parents=True)
    with ledger(cfg) as book:
        context = _context(cfg, policy, book, reasons, cycle_id)
    prompt = ("Run one AFDA autonomous cycle. Follow the afda-cycle skill (.claude/skills/afda-cycle/SKILL.md) and your role file "
              f"(.claude/roles/{cfg['role']}.md).\n\nCycle context (JSON, generated by agent_bridge):\n```json\n"
              + json.dumps(context, ensure_ascii=False, indent=2) + "\n```\n")
    role = policy["role"]
    argv = resolve_claude(policy) + ["-p", "--output-format", "json", "--json-schema", json.dumps(REPORT_SCHEMA),
                                     "--max-budget-usd", str(role["max_budget_usd_per_cycle"]),
                                     "--permission-mode", "acceptEdits", "--session-id", session_id,
                                     "--append-system-prompt", AUTONOMY_NOTE.format(role=cfg["role"], cycle=cycle_id)]
    if role.get("model"):
        argv += ["--model", role["model"]]
    if role.get("effort"):
        argv += ["--effort", role["effort"]]
    environment = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDECODE") and k != "CLAUDE_CODE_ENTRYPOINT"}
    environment.update(AFDA_AUTONOMOUS="1", AFDA_ROLE=cfg["role"], AFDA_CYCLE_ID=cycle_id,
                       AFDA_EXCHANGE_CONFIG=str(Path(cfg["project_root"]) / "configs/local-exchange.json"))
    (folder / "prompt.md").write_text(prompt, encoding="utf-8")
    stdout = (folder / "stdout.json").open("wb")
    stderr = (folder / "stderr.log").open("wb")
    process = subprocess.Popen(argv, cwd=cfg["project_root"], stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, env=environment,
                               creationflags=0x08000000 if os.name == "nt" else 0)
    process.stdin.write(prompt.encode("utf-8"))
    process.stdin.close()
    record = {"cycle_id": cycle_id, "session_id": session_id, "pid": process.pid, "started_utc": utc_text(),
              "reasons": reasons, "status": "running", "folder": str(folder)}
    with ledger(cfg) as book:
        book["active_cycle"] = record
    return process, record, (stdout, stderr)


def _kill_tree(pid):
    try:
        import psutil
        root = psutil.Process(pid)
        for process in reversed([root, *root.children(recursive=True)]):
            try:
                process.kill()
            except psutil.Error:
                pass
    except Exception:
        pass


def finish_cycle(cfg, policy, record, returncode, timed_out=False):
    folder = Path(record["folder"])
    raw = (folder / "stdout.json").read_text(encoding="utf-8", errors="replace").strip()
    result = {}
    try:
        result = json.loads(raw[raw.index("{"):]) if raw else {}
    except ValueError:
        result = {}
    report = result.get("structured_output")
    if report is None and isinstance(result.get("result"), dict):
        report = result["result"]
    ok = returncode == 0 and not timed_out and not result.get("is_error") and isinstance(report, dict)
    status = "succeeded" if ok else ("timed_out" if timed_out else (result.get("subtype") or f"exit_{returncode}"))
    cost = float(result.get("total_cost_usd") or 0.0)
    now = utc_now()
    with ledger(cfg) as book:
        day = book["budget"].setdefault(now.strftime("%Y-%m-%d"), {"cycles": 0, "usd": 0.0})
        day["cycles"] += 1
        day["usd"] = round(day["usd"] + cost, 4)
        if ok:
            book["failures"] = 0
            for reason in record["reasons"]:
                if reason["type"] in {"packet", "quarantined_packet"} and reason["packet_id"] in book["packets"]:
                    book["packets"][reason["packet_id"]]["handled"] = True
                elif reason["type"] == "job_finished" and reason["job_id"] in book["jobs"]:
                    book["jobs"][reason["job_id"]]["reported"] = True
                elif reason["type"] == "input_changed" and reason["path"] in book["watch"]:
                    entry = book["watch"][reason["path"]]
                    entry["seen"] = entry.get("stamp")
            book["next_wake"] = report.get("next_wake") or {"mode": "on_event", "reason": "no next_wake given"}
        else:
            book["failures"] += 1
            book["next_wake"] = {"mode": "asap", "reason": f"retry after {status}"}
        entry = {**record, "status": status, "ended_utc": utc_text(now), "returncode": returncode, "cost_usd": cost,
                 "num_turns": result.get("num_turns"), "report": report if ok else None,
                 "error": None if ok else (result.get("result") if isinstance(result.get("result"), str) else raw[-2000:])}
        entry.pop("pid", None)
        book["cycles"].append(entry)
        book["cycles"] = book["cycles"][-200:]
        book.pop("active_cycle", None)
    atomic_json(folder / "cycle.json", entry)
    atomic_json(Path(cfg["project_root"]) / "work" / "agent" / "last_cycle.json", entry)
    if ok and (report.get("human_actions") or report.get("submission_candidate")):
        notify(cfg, report)
    stderr = (folder / "stderr.log").read_text(encoding="utf-8", errors="replace") if (folder / "stderr.log").exists() else ""
    if not ok and re.search(r"authenticat|oauth|/login|not been trusted|credit balance|rate.?limit|usage limit", f"{entry['error']} {stderr}", re.I):
        notify(cfg, {"human_actions": [f"Claude CLI cannot run on {cfg['role']} ({status}). Open a terminal in the project, "
                                       "run `claude`, accept trust and /login, or wait for the usage limit to reset. Details: "
                                       + str(folder)]})
    return entry


def notify(cfg, report):
    """Best-effort Windows toast plus a local file; never raises."""
    lines = list(report.get("human_actions") or [])
    if report.get("submission_candidate"):
        lines.insert(0, "Submission candidate: " + str(report["submission_candidate"].get("path")))
    path = Path(cfg["project_root"]) / "work" / "agent" / "HUMAN_ACTIONS.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## {utc_text()} ({cfg['role']})\n" + "".join(f"- {line}\n" for line in lines))
    if os.name != "nt" or not lines:
        return
    text = (lines[0][:180]).replace("'", "''").replace("<", " ").replace(">", " ").replace("&", " and ")
    script = ("[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]>$null;"
              "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
              f"$t=$x.GetElementsByTagName('text');$t.Item(0).InnerText='AFDA {cfg['role']}';$t.Item(1).InnerText='{text}';"
              "$n=[Windows.UI.Notifications.ToastNotification]::new($x);"
              "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show($n)")
    try:
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], timeout=20,
                       capture_output=True, creationflags=0x08000000)
    except Exception:
        pass


def keep_awake(enable=True):
    """Ask Windows not to idle-sleep while the loop runs (does not change power settings)."""
    if os.name != "nt":
        return
    import ctypes
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if enable else 0))


def tick(cfg, config_path, policy, allow_cycle=True):
    """One non-blocking iteration. Returns a small status dict for logging."""
    imported = packets.import_inbox(cfg)
    lost = jobs.monitor(cfg)
    launched = jobs.launch_queued(cfg, config_path)
    with ledger(cfg) as book:
        book["loop_heartbeat_utc"] = utc_text()
        reasons, blocked = wake_reasons(cfg, policy, book) if allow_cycle else ([], "cycle running")
    return {"imported": imported, "lost_jobs": lost, "launched_jobs": launched, "reasons": reasons, "blocked": blocked}


def loop(cfg, config_path, once=False):
    root = agent_root(cfg)
    log = root / "loop.log"
    with _file_lock(root / "loop.lock", wait_seconds=1):
        keep_awake(True)
        with ledger(cfg) as book:
            stale = book.pop("active_cycle", None)
            if stale:
                stale.update(status="interrupted_by_loop_restart", ended_utc=utc_text(), report=None)
                book["cycles"].append(stale)
        active = None
        try:
            while not (root / "STOP").exists():
                policy = load_policy(cfg["role"])
                try:
                    if active:
                        process, record, handles = active
                        timeout = policy["role"]["cycle_timeout_minutes"] * 60
                        elapsed = (utc_now() - parse_utc(record["started_utc"])).total_seconds()
                        if process.poll() is None and elapsed > timeout:
                            _kill_tree(process.pid)
                            process.wait(timeout=30)
                            timed_out = True
                        else:
                            timed_out = False
                        if process.poll() is not None:
                            for handle in handles:
                                handle.close()
                            entry = finish_cycle(cfg, policy, record, process.returncode, timed_out)
                            _log(log, f"cycle {entry['cycle_id']} {entry['status']} cost=${entry['cost_usd']:.2f}")
                            active = None
                    status = tick(cfg, config_path, policy, allow_cycle=active is None)
                    if status["imported"] or status["launched_jobs"] or status["lost_jobs"]:
                        _log(log, json.dumps({k: v for k, v in status.items() if k != "reasons"}))
                    if active is None and status["reasons"]:
                        if not guard_selftest(cfg):
                            _log(log, "guard self-test failed; not starting Claude (python on PATH? .claude/hooks/guard.py)")
                        else:
                            active = start_cycle(cfg, policy, status["reasons"])
                            _log(log, f"cycle {active[1]['cycle_id']} started: " + ", ".join(r["type"] for r in status["reasons"]))
                except Exception as error:  # keep the service alive; the log is the evidence
                    _log(log, f"loop error: {type(error).__name__}: {error}")
                if once and active is None:
                    break
                time.sleep(policy.get("tick_seconds", 20))
        finally:
            if active:
                _log(log, "loop stopping; waiting for the running cycle to finish is not possible, killing it")
                _kill_tree(active[0].pid)
            keep_awake(False)


def _log(path, message):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{utc_text()} {message}\n")


def status(cfg):
    book = read_ledger(cfg)
    policy = load_policy(cfg["role"])
    today = book["budget"].get(utc_now().strftime("%Y-%m-%d"), {"cycles": 0, "usd": 0.0})
    return {
        "role": cfg["role"], "loop_heartbeat_utc": book.get("loop_heartbeat_utc"),
        "active_cycle": {k: book["active_cycle"].get(k) for k in ("cycle_id", "started_utc", "reasons")} if book.get("active_cycle") else None,
        "last_cycles": [{k: c.get(k) for k in ("cycle_id", "status", "ended_utc", "cost_usd")} | {"summary": (c.get("report") or {}).get("summary")}
                        for c in book["cycles"][-5:]],
        "next_wake": book.get("next_wake"), "failures": book["failures"], "budget_today": today,
        "limits": {k: policy["role"][k] for k in ("max_cycles_per_day", "max_usd_per_day", "max_budget_usd_per_cycle")},
        "packets_waiting": [p for p, e in book["packets"].items() if e.get("status") == "waiting"],
        "packets_unhandled": [p for p, e in book["packets"].items() if e.get("status") == "imported" and not e.get("handled")],
        "quarantined": [p for p, e in book["packets"].items() if e.get("status") == "quarantined"],
        "sent_unacked": [p for p in book["sent"] if p not in book["acks"]],
        "jobs": jobs.summary(cfg, 5),
        "paused": (agent_root(cfg) / "PAUSE").exists(),
    }
