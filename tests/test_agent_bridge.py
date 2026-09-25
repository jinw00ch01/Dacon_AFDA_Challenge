import json
from pathlib import Path
import shutil
import tempfile
import unittest

from agent_bridge import jobs, packets, runner
from agent_bridge.state import ledger, load_policy, read_ledger, utc_text


class AgentBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.ultra = self.config("ultra5060")
        self.pro = self.config("pro360")

    def config(self, role):
        root = self.base / role
        root.mkdir()
        return dict(version=1, role=role, project_root=str(root), exchange_root=str(self.base / "exchange"),
                    state_root=str(self.base / (role + "-state")), python="python")

    # Both configs share one exchange root, so each outbox is already the peer's inbox (Syncthing simulated).
    def result_body(self):
        return {"experiment_id": "exp-" + "a" * 32, "attempt_id": "a001", "status": "succeeded",
                "spec_sha256": "b" * 64, "metrics_by_seed": []}

    def test_round_trip_imports_once_and_acks(self):
        attach = self.base / "attach"
        (attach / "sub").mkdir(parents=True)
        (attach / "predictions.csv").write_text("ID,answer\n1,ORIGINAL\n", encoding="utf-8")
        (attach / "sub" / "metrics.json").write_text("{}", encoding="utf-8")
        packet_id, manifest = packets.publish(self.ultra, "result", self.result_body(), attach)
        self.assertEqual(packets.import_inbox(self.pro), [packet_id])
        local = Path(self.pro["project_root"]) / "data/derived/experiment_packets/inbox" / packet_id
        self.assertTrue((local / "files/predictions.csv").is_file())
        self.assertEqual(json.loads((local / "result.json").read_text(encoding="utf-8"))["sender"], "ultra5060")
        self.assertEqual(packets.import_inbox(self.pro), [])
        book = read_ledger(self.pro)
        self.assertFalse(book["packets"][packet_id]["handled"])
        packets.import_inbox(self.ultra)
        self.assertEqual(read_ledger(self.ultra)["acks"][packet_id]["status"], "received")
        self.assertIn(packet_id, read_ledger(self.ultra)["sent"])

    def test_partial_sync_waits_and_tampering_quarantines(self):
        packet_id, _ = packets.publish(self.ultra, "result", self.result_body())
        folder = self.base / "exchange/ultra_to_pro/experiments/v1" / packet_id
        body = folder / "result.json"
        saved = body.read_bytes()
        body.unlink()
        packets.import_inbox(self.pro)
        self.assertEqual(read_ledger(self.pro)["packets"][packet_id]["status"], "waiting")
        body.write_bytes(saved.replace(b"succeeded", b"failedxxx"))
        packets.import_inbox(self.pro)
        entry = read_ledger(self.pro)["packets"][packet_id]
        self.assertEqual(entry["status"], "quarantined")
        self.assertIn("hash mismatch", entry["detail"])

    def test_authority_and_templates_enforced(self):
        with self.assertRaises(ValueError):
            packets.publish(self.pro, "decision", {"experiment_id": "exp-" + "a" * 32, "decision": "accept", "reason": "x"})
        with self.assertRaises(ValueError):
            packets.publish(self.ultra, "review", {"experiment_id": "exp-" + "a" * 32, "attempt_id": "a001", "proposal": {}})
        template = json.loads((Path(__file__).resolve().parents[1] / "docs/templates/experiments/spec.example.json").read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):
            packets.validate(template)
        with self.assertRaises(ValueError):
            packets.publish(self.pro, "qa", {"subject": ""})
        bad = self.base / "bad"
        bad.mkdir()
        (bad / "run.ps1").write_text("whoami", encoding="utf-8")
        with self.assertRaises(ValueError):
            packets.publish(self.pro, "qa", {"subject": "labels"}, bad)
        self.assertFalse(any((self.base / "exchange/pro_to_ultra/experiments/v1").glob(".staging-*")))

    def test_forged_sender_is_quarantined(self):
        packet_id, _ = packets.publish(self.pro, "qa", {"subject": "labels v1"})
        source = self.base / "exchange/pro_to_ultra/experiments/v1" / packet_id
        forged = self.base / "exchange/ultra_to_pro/experiments/v1" / packet_id
        forged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, forged)
        packets.import_inbox(self.pro)
        self.assertEqual(read_ledger(self.pro)["packets"][packet_id]["status"], "quarantined")

    def test_wake_reasons_deliver_each_event_once(self):
        policy = load_policy("pro360")
        packet_id, _ = packets.publish(self.ultra, "request", {"subject": "label 10 more videos", "body": "ids ..."})
        packets.import_inbox(self.pro)
        with ledger(self.pro) as book:
            book["next_wake"] = {"mode": "on_event", "reason": "test"}
            book["cycles"] = [{"cycle_id": "c0", "ended_utc": utc_text(), "status": "succeeded"}]
            book["cycles"][0]["ended_utc"] = "2000-01-01T00:00:00Z"
            reasons, blocked = runner.wake_reasons(self.pro, policy, book)
        self.assertIsNone(blocked)
        self.assertEqual([r["type"] for r in reasons if r["type"] == "packet"], ["packet"])
        record = {"cycle_id": "c1", "folder": str(self.base), "reasons": reasons, "started_utc": utc_text()}
        (self.base / "stdout.json").write_text(json.dumps({"is_error": False, "total_cost_usd": 1.5, "structured_output": {
            "summary": "done", "actions": [], "human_actions": [], "next_wake": {"mode": "on_event", "reason": "wait"}}}), encoding="utf-8")
        entry = runner.finish_cycle(self.pro, policy, record, 0)
        self.assertEqual(entry["status"], "succeeded")
        with ledger(self.pro) as book:
            again, _ = runner.wake_reasons(self.pro, policy, book)
        self.assertFalse([r for r in again if r["type"] == "packet"])
        self.assertEqual(read_ledger(self.pro)["budget"][utc_text()[:10]]["usd"], 1.5)

    def test_failed_cycle_keeps_reasons_and_backs_off(self):
        policy = load_policy("pro360")
        packets.publish(self.ultra, "request", {"subject": "x"})
        packets.import_inbox(self.pro)
        with ledger(self.pro) as book:
            reasons, _ = runner.wake_reasons(self.pro, policy, book)
        (self.base / "stdout.json").write_text(json.dumps({"is_error": True, "subtype": "error_max_budget_usd", "total_cost_usd": 3}), encoding="utf-8")
        runner.finish_cycle(self.pro, policy, {"cycle_id": "c1", "folder": str(self.base), "reasons": reasons, "started_utc": utc_text()}, 1)
        book = read_ledger(self.pro)
        self.assertEqual(book["failures"], 1)
        self.assertFalse(any(e["handled"] for e in book["packets"].values() if e["kind"] == "request"))
        with ledger(self.pro) as book:
            _, blocked = runner.wake_reasons(self.pro, policy, book)
        self.assertIn("backoff", blocked)

    def test_budget_and_pause_block_cycles(self):
        policy = load_policy("ultra5060")
        with ledger(self.ultra) as book:
            book["budget"][utc_text()[:10]] = {"cycles": 0, "usd": policy["role"]["max_usd_per_day"]}
            _, blocked = runner.wake_reasons(self.ultra, policy, book)
        self.assertIn("budget", blocked)
        (Path(self.ultra["state_root"]) / "agent" / "PAUSE").write_text("x")
        with ledger(self.ultra) as book:
            _, blocked = runner.wake_reasons(self.ultra, policy, book)
        self.assertIn("paused", blocked)

    def test_usage_limit_reset_parsing(self):
        from datetime import datetime, timedelta, timezone
        kst = timezone(timedelta(hours=9))
        now = datetime(2026, 9, 25, 5, 0, tzinfo=timezone.utc)  # 14:00 KST
        until = lambda text: runner.usage_limit_until(text, now, kst)  # noqa: E731
        minute = timedelta(minutes=1)
        self.assertIsNone(until("API Error: 529 overloaded"))
        self.assertEqual(until("You've hit your limit · resets 3pm (Asia/Seoul)"), datetime(2026, 9, 25, 6, 0, tzinfo=timezone.utc) + minute)
        self.assertEqual(until("5-hour limit reached ∙ resets 1:30am"), datetime(2026, 9, 25, 16, 30, tzinfo=timezone.utc) + minute)
        future = now + timedelta(hours=3)
        self.assertEqual(until(f"Claude AI usage limit reached|{int(future.timestamp())}"), future + minute)
        self.assertEqual(until("usage limit reached, resets in 2h 15m"), now + timedelta(hours=2, minutes=15) + minute)
        self.assertEqual(until("Your weekly limit resets Sep 29, 9am"), datetime(2026, 9, 29, 0, 0, tzinfo=timezone.utc) + minute)
        self.assertEqual(until("usage limit reached"), now + timedelta(minutes=30))

    def test_usage_limit_pauses_without_counting_a_failure(self):
        from unittest.mock import patch
        policy = load_policy("pro360")
        packets.publish(self.ultra, "request", {"subject": "x"})
        packets.import_inbox(self.pro)
        with ledger(self.pro) as book:
            reasons, _ = runner.wake_reasons(self.pro, policy, book)
        (self.base / "stdout.json").write_text(json.dumps({"is_error": True, "result": "You've hit your limit · resets in 45m",
                                                           "total_cost_usd": 0}), encoding="utf-8")
        with patch.object(runner, "notify") as notify:
            entry = runner.finish_cycle(self.pro, policy, {"cycle_id": "c1", "folder": str(self.base), "reasons": reasons,
                                                           "started_utc": utc_text()}, 1)
            runner.finish_cycle(self.pro, policy, {"cycle_id": "c2", "folder": str(self.base), "reasons": reasons,
                                                   "started_utc": utc_text()}, 1)
        self.assertEqual(entry["status"], "usage_limit")
        self.assertEqual(notify.call_count, 1)  # one notice per limit episode
        book = read_ledger(self.pro)
        self.assertEqual(book["failures"], 0)
        self.assertFalse(any(e["handled"] for e in book["packets"].values() if e["kind"] == "request"))
        with ledger(self.pro) as book:
            _, blocked = runner.wake_reasons(self.pro, policy, book)
            self.assertIn("usage limit", blocked)
            book["limit_until_utc"] = "2000-01-01T00:00:00Z"
            book["cycles"][-1]["ended_utc"] = "2000-01-01T00:00:00Z"  # past the minimum gap
            reasons, blocked = runner.wake_reasons(self.pro, policy, book)
        self.assertIsNone(blocked)
        self.assertTrue(any(r["type"] == "packet" for r in reasons))

    def test_code_reload_keeps_modules_usable(self):
        runner._reload_code()
        self.assertIsNone(runner.usage_limit_until("all good"))
        self.assertTrue(callable(runner.jobs.launch_queued))

    def test_cli_accepts_config_before_or_after_subcommand(self):
        from agent_bridge.__main__ import build_parser
        parser = build_parser()
        self.assertEqual(parser.parse_args(["job-run", "--config", "X", "--job", "j"]).config, "X")
        self.assertEqual(parser.parse_args(["--config", "X", "job-run", "--job", "j"]).config, "X")
        args = parser.parse_args(["--config", "X", "job", "start", "--kind", "gpu", "--timeout", "5", "--name", "t", "--",
                                  "python", "-m", "afda.train", "--config", "exp.json"])
        self.assertEqual(args.config, "X")
        self.assertEqual(args.child[-2:], ["--config", "exp.json"])

    def test_loop_launch_command_parses(self):
        from unittest.mock import patch
        from agent_bridge.__main__ import build_parser
        jobs.request(self.pro, "cpu", 60, "metrics", ["python", "b.py"])
        with patch.object(jobs.subprocess, "Popen") as popen:
            popen.return_value.pid = 4242
            jobs.launch_queued(self.pro, "cfg.json")
        argv = popen.call_args.args[0]
        self.assertEqual(argv[1:3], ["-m", "agent_bridge"])
        args = build_parser().parse_args(argv[3:])
        self.assertEqual((args.command, args.config), ("job-run", "cfg.json"))

    def test_job_rules(self):
        with self.assertRaises(ValueError):
            jobs.request(self.pro, "gpu", 60, "train", ["python", "a.py"])
        with self.assertRaises(ValueError):
            jobs.request(self.ultra, "gpu", 60, "train", ["python", "a.py"])  # temp dir is not a clean git tree
        spec = jobs.request(self.pro, "cpu", 60, "metrics", ["python", "b.py"])
        self.assertEqual(read_ledger(self.pro)["jobs"][spec["job_id"]]["status"], "queued")


if __name__ == "__main__":
    unittest.main()
