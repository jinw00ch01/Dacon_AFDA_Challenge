"""CLI: python -m agent_bridge <command>. Config defaults to configs/local-exchange.json."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from . import jobs, packets, runner
from .state import ROOT, agent_root, ledger, load_config, load_policy, read_ledger, sandbox_package, strict_load


def _print(value):
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser():
    parser = argparse.ArgumentParser(prog="python -m agent_bridge", description=__doc__)
    parser.add_argument("--config", default=os.environ.get("AFDA_EXCHANGE_CONFIG") or str(ROOT / "configs/local-exchange.json"))
    # --config is also accepted after the subcommand (older loops put it there); SUPPRESS keeps the top-level value otherwise.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("loop", "Run the unattended service loop (used by the scheduled task)"),
                       ("tick", "One loop iteration without starting Claude (debug)"),
                       ("status", "Loop, cycle, packet, job and budget status"),
                       ("selftest", "Check config, policy, guard hook and claude executable"),
                       ("probe", "Run the real headless claude command once with a trivial task (costs cents)"),
                       ("inbox", "List imported packets and their local paths"),
                       ("pause", "Stop starting new cycles (jobs continue)"), ("resume", "Undo pause/stop"),
                       ("stop", "Ask the loop to exit")):
        sub.add_parser(name, parents=[common], help=text)
    wake = sub.add_parser("wake", parents=[common], help="Operator nudge: start a cycle as soon as limits allow, with a reason")
    wake.add_argument("--reason", required=True)
    publish = sub.add_parser("publish", parents=[common], help="Publish a packet from a JSON body (+ optional attachment folder)")
    publish.add_argument("--kind", required=True, choices=sorted(packets.KINDS - {"ack"}))
    publish.add_argument("--body", required=True, type=Path)
    publish.add_argument("--attach", type=Path)
    publish.add_argument("--target", choices=["ultra5060", "pro360"])
    job = sub.add_parser("job", parents=[common], help="Queue and inspect detached long jobs")
    job_sub = job.add_subparsers(dest="job_command", required=True)
    start = job_sub.add_parser("start", parents=[common])
    start.add_argument("--kind", required=True, choices=["cpu", "gpu"])
    start.add_argument("--timeout", required=True, type=float, help="seconds")
    start.add_argument("--name", required=True)
    start.add_argument("--allow-dirty", action="store_true")
    start.add_argument("child", nargs=argparse.REMAINDER)
    job_sub.add_parser("list", parents=[common])
    job_sub.add_parser("show", parents=[common]).add_argument("job_id")
    job_sub.add_parser("cancel", parents=[common]).add_argument("job_id")
    run = sub.add_parser("job-run", parents=[common], help=argparse.SUPPRESS)
    run.add_argument("--job", required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config)
    writes_state = args.command in {"loop", "tick", "publish", "pause", "resume", "stop", "wake"} or (
        args.command == "job" and args.job_command in {"start", "cancel"})
    package = sandbox_package(cfg["state_root"]) if writes_state else None
    if package:
        _print({"error": f"이 셸은 앱 샌드박스({package}) 안에서 실행 중이라, 상태 파일이 실제 루프에 전달되지 않습니다. "
                         "시작 메뉴의 Windows PowerShell에서 다시 실행하세요.", "command": args.command})
        return 2

    if args.command == "loop":
        runner.loop(cfg, args.config)
    elif args.command == "tick":
        _print(runner.tick(cfg, args.config, load_policy(cfg["role"])))
    elif args.command == "status":
        _print(runner.status(cfg))
    elif args.command == "selftest":
        checks = {"role": cfg["role"], "policy": bool(load_policy(cfg["role"])), "guard_denies_force_push": runner.guard_selftest(cfg)}
        try:
            checks["claude"] = runner.resolve_claude(load_policy(cfg["role"]))
        except FileNotFoundError as error:
            checks["claude"] = str(error)
        _print(checks)
        return 0 if checks["guard_denies_force_push"] and isinstance(checks["claude"], list) else 1
    elif args.command == "probe":
        result = runner.probe(cfg, load_policy(cfg["role"]))
        _print(result)
        return 0 if result["ok"] else 1
    elif args.command == "wake":
        # Reuses the agent's own next_wake mechanism; budgets, pause and backoff still apply.
        with ledger(cfg) as book:
            book["next_wake"] = {"mode": "asap", "reason": "운영자 요청: " + args.reason}
            _print({"next_wake": book["next_wake"]})
    elif args.command == "inbox":
        book = read_ledger(cfg)
        _print([{"packet_id": p, **{k: e.get(k) for k in ("kind", "status", "handled", "subject", "experiment_id", "imported_utc", "local_path", "detail")}}
                for p, e in sorted(book["packets"].items(), key=lambda item: item[1].get("imported_utc") or "")])
    elif args.command == "publish":
        body = strict_load(args.body)
        packet_id, manifest = packets.publish(cfg, args.kind, body, args.attach, args.target)
        _print({"packet_id": packet_id, "manifest_sha256": manifest, "kind": args.kind})
    elif args.command == "job":
        if args.job_command == "start":
            child = args.child[1:] if args.child[:1] == ["--"] else args.child
            _print(jobs.request(cfg, args.kind, args.timeout, args.name, child, args.allow_dirty))
        elif args.job_command == "list":
            _print(jobs.summary(cfg, 30))
        elif args.job_command == "show":
            folder = jobs.job_dir(cfg, args.job_id)
            done = folder / "done.json"
            _print({"ledger": read_ledger(cfg)["jobs"].get(args.job_id),
                    "done": json.loads(done.read_text(encoding="utf-8")) if done.exists() else None})
        else:
            _print(jobs.cancel(cfg, args.job_id))
    elif args.command == "job-run":
        return jobs.run(cfg, args.job)
    else:
        root = agent_root(cfg)
        flag = root / ("STOP" if args.command == "stop" else "PAUSE")
        if args.command == "resume":
            (root / "PAUSE").unlink(missing_ok=True)
            (root / "STOP").unlink(missing_ok=True)
        else:
            flag.write_text(args.command, encoding="utf-8")
        _print({"paused": (root / "PAUSE").exists(), "stop_requested": (root / "STOP").exists()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
