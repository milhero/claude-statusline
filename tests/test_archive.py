import json
import unittest

from ccsl import archive, rules
from tests.helpers import Sandbox, answer, cost


class TestCostLines(Sandbox):
    def read(self, lines):
        return archive.read_session(self.log("p", "s", lines), rules.Context([]))

    def test_a_message_mentioning_the_word_does_not_count_as_cost_line(self):
        mention = {"type": "user", "message": {"role": "user", "content": "grep cost-state x"}}
        s = self.read([answer(), cost(12.5, 1000), mention])
        self.assertEqual(s["usd"], 12.5)
        self.assertFalse(s["estimated"])

    def test_two_windows_add_up(self):
        s = self.read([answer(), cost(38.22, 1000), cost(54.48, 2000), cost(40.32, 1000)])
        self.assertAlmostEqual(s["usd"], 94.80, places=2)

    def test_empty_process_last_deletes_nothing(self):
        s = self.read([answer(), cost(0.0, 2000), cost(53.25, 1000), cost(0.0, 2000)])
        self.assertAlmostEqual(s["usd"], 53.25, places=2)

    def test_resumed_process_counts_with_its_highest_counter(self):
        s = self.read([answer(), cost(45.62, 1000), cost(71.36, 1000), cost(58.68, 1000)])
        self.assertAlmostEqual(s["usd"], 71.36, places=2)
        self.assertEqual(s["processes"], {"1000": 71.36})

    def test_without_cost_line_tokens_are_kept_and_requests_counted_once(self):
        usage = {"output_tokens": 50, "input_tokens": 10}
        s = self.read([answer(usage=usage, request="r1"), answer(usage=usage, request="r1"),
                       answer(usage=usage, request="r2")])
        self.assertTrue(s["estimated"])
        self.assertEqual(s["models"]["claude-opus-5"]["out"], 100)

    def test_nothing_at_all_gives_none(self):
        self.assertIsNone(self.read([{"type": "user", "message": {"content": "hi"}}]))


class TestSignals(Sandbox):
    def read(self, lines):
        return archive.read_session(self.log("p", "s", lines), rules.Context([]))

    def test_files_keep_only_their_folder(self):
        repo = self.repo("code", "aurora")
        s = self.read([answer(out=7, file_path=repo + "/src/app.py"), cost(1, 1)])
        self.assertEqual(s["paths"], {repo + "/src": 7})
        self.assertEqual(s["git_roots"][repo + "/src"], repo)

    def test_windows_file_paths_count(self):
        s = self.read([answer(out=5, file_path="C:\\Users\\ana\\proj\\main.py"), cost(1, 1)])
        self.assertEqual(s["paths"], {"C:/Users/ana/proj": 5})

    def test_macos_paths_in_commands_count(self):
        repo = self.repo("Users", "ana", "code", "aurora")
        s = self.read([answer(out=3, command="cd {} && make".format(repo)), cost(1, 1)])
        self.assertIn(repo, s["commands"])

    def test_system_paths_in_commands_are_dropped(self):
        s = self.read([answer(out=3, command="/usr/bin/env python3 /etc/hosts"), cost(1, 1)])
        self.assertEqual(s["commands"], {})

    def test_temp_paths_never_count(self):
        s = self.read([answer(out=3, cwd="/proc/self", file_path="/proc/x/y.txt"), cost(1, 1)])
        self.assertEqual(s["cwd"], {})
        self.assertEqual(s["paths"], {})

    def test_escaped_windows_paths_in_commands(self):
        from ccsl.session_project import paths_in_command, unescape
        command = unescape('cd \\"C:\\\\Users\\\\ana\\\\proj\\" && dir')
        self.assertEqual(paths_in_command(command), ["C:\\Users\\ana\\proj"])
        signals = archive.Signals(rules.Context([]))
        signals.home = "C:/Users/ana"
        signals.add_command(command, 2)
        self.assertEqual(signals.commands, {"C:/Users/ana/proj": 2})


class TestSettle(unittest.TestCase):
    def test_process_in_two_sessions_counts_once(self):
        a = {"session": "a", "first_ms": 1, "usd": 50, "processes": {"p": 50.0}}
        b = {"session": "b", "first_ms": 2, "usd": 80, "processes": {"p": 80.0}}
        archive.settle_processes([b, a])
        self.assertEqual((a["usd"], b["usd"]), (50.0, 30.0))

    def test_prices_come_from_measured_sessions(self):
        measured = {"models": {"m": {"usd": 10.0, "out": 1000}}}
        estimated = {"estimated": True, "models": {"m": {"out": 500}}}
        prices = archive.derive_prices([measured, estimated])
        archive.recompute([estimated], prices)
        self.assertAlmostEqual(estimated["usd"], 5.0)

    def test_measured_replaces_estimated_never_the_other_way(self):
        est = {"estimated": True, "models": {}}
        meas = {"estimated": False, "processes": {"1": 2.0}}
        self.assertTrue(archive.should_replace(est, meas))
        self.assertFalse(archive.should_replace(meas, est))


class TestCollect(Sandbox):
    def test_collect_is_incremental_and_keeps_deleted_sessions(self):
        repo = self.repo("code", "aurora")
        first = self.log("p", "one", [answer(cwd=repo), cost(2.0, 1000, session="one")])
        self.log("p", "two", [answer(cwd=repo), cost(3.0, 2000, session="two")])
        ctx = rules.Context([])
        r1 = archive.collect(ctx=ctx)
        self.assertEqual((r1["new"], r1["total"]), (2, 2))
        r2 = archive.collect(ctx=ctx)
        self.assertEqual((r2["new"], r2["replaced"]), (0, 0))
        first.unlink()
        r3 = archive.collect(ctx=ctx)
        self.assertEqual(r3["total"], 2)
        stored = archive.read()
        self.assertEqual({r["session"] for r in stored}, {"one", "two"})
        self.assertEqual(stored[0]["git_roots"][repo], repo)

    def test_changed_file_is_read_again(self):
        path = self.log("p", "one", [answer(), cost(2.0, 1000, session="one")])
        archive.collect(ctx=rules.Context([]))
        path.write_text(path.read_text() + json.dumps(cost(5.0, 1000, session="one")) + "\n")
        archive.collect(ctx=rules.Context([]))
        self.assertEqual(archive.read()[0]["usd"], 5.0)

    def test_format_check_counts_logs_with_cost_lines(self):
        self.log("p", "a", [answer(), cost(1, 1)])
        self.log("p", "b", [answer()])
        self.assertEqual(archive.logs_without_cost_lines(), (2, 1))


if __name__ == "__main__":
    unittest.main()
