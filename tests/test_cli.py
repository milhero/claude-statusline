import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ccsl import project_costs, report_cli, rules, session_project
from tests.helpers import Sandbox, answer, cost

ROOT = Path(__file__).resolve().parent.parent


def run_cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = report_cli.main(list(args))
    return code, out.getvalue(), err.getvalue()


class TestPeriod(unittest.TestCase):
    def test_bounds(self):
        self.assertEqual(report_cli.period_bounds("2026-02"), ("2026-02-01", "2026-02-28"))
        self.assertEqual(report_cli.period_bounds("2026"), ("2026-01-01", "2026-12-31"))
        for bad in ("2026-13", "2026-02-30", "soon"):
            with self.assertRaises(ValueError):
                report_cli.period_bounds(bad)


class TestCli(Sandbox):
    def setUp(self):
        super().setUp()
        self.app = self.repo("code", "aurora")
        # Recent sessions: the summary only keeps the last 60 days per session.
        now = datetime.now(timezone.utc)
        self.month = (now - timedelta(days=3)).strftime("%Y-%m")
        self.log("p", "one", [answer(cwd=self.app, when=self.iso(now - timedelta(days=3))),
                              cost(12.0, 1000, session="one")])
        self.log("p", "two", [answer(cwd=self.app, when=self.iso(now - timedelta(days=40))),
                              cost(8.0, 2000, session="two")])

    @staticmethod
    def iso(when):
        return when.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def test_table_writes_the_summary(self):
        code, out, _ = run_cli("--measured-only")
        self.assertEqual(code, 0)
        self.assertIn("aurora", out)
        self.assertFalse(project_costs.summary_path().exists())   # filtered view
        code, out, _ = run_cli()
        summary = json.loads(project_costs.summary_path().read_text(encoding="utf-8"))
        self.assertEqual(summary["api_usd_total"], 20.0)
        self.assertEqual(summary["sessions"]["one"], {"aurora": 12.0})

    def test_unknown_project_and_bad_period_fail(self):
        self.assertEqual(run_cli("--project", "nope")[0], 1)
        self.assertEqual(run_cli("--period", "2026-13")[0], 1)

    def test_german_output(self):
        _, out, _ = run_cli("--lang", "de", "--period", self.month)
        self.assertIn("12,00 $", out)

    def test_discover_is_json(self):
        _, out, _ = run_cli("--discover")
        data = json.loads(out)
        self.assertIn("no_invoices", data["issues"])
        self.assertEqual(data["archive"]["sessions"], 2)

    def test_check_and_other_views(self):
        for flag in ("--check", "--formula", "--by-source", "--compare", "--history",
                     "--collect"):
            code, out, err = run_cli(flag)
            self.assertIn(code, (0, 1), flag)
            self.assertTrue(out.strip(), flag)

    def test_help_does_not_crash(self):
        with self.assertRaises(SystemExit) as stop, \
                contextlib.redirect_stdout(io.StringIO()):
            report_cli.main(["--help"])
        self.assertEqual(stop.exception.code, 0)


class TestSessionProject(Sandbox):
    def test_four_steps(self):
        app = self.repo("code", "aurora")
        ctx = rules.Context([])
        self.assertEqual(session_project.determine("s", app, None, ctx), "aurora")
        # The directory wanders off, the project stays.
        self.assertEqual(session_project.determine("s", str(self.home), None, ctx), "aurora")
        transcript = self.log("p", "t", [answer(file_path=app + "/main.py")])
        self.assertEqual(session_project.determine("other", str(self.home), None, ctx,
                                                   transcript=str(transcript)), "aurora")
        self.assertIsNone(session_project.determine(None, "/nowhere", None, ctx))


class TestStatuslineScript(Sandbox):
    def run_script(self, stdin, *args, extra_env=None):
        env = dict(os.environ, COLUMNS="140", TERM="dumb", **(extra_env or {}))
        return subprocess.run([sys.executable, str(ROOT / "statusline.py")] + list(args),
                              input=stdin, capture_output=True, text=True, env=env,
                              encoding="utf-8", timeout=60)

    def test_always_exits_zero_with_output(self):
        fixture = (ROOT / "tests" / "fixtures" / "stdin_full.json").read_text(encoding="utf-8")
        for stdin in (fixture, "", "not json", "[]"):
            done = self.run_script(stdin, extra_env={"CCSL_LIVE_LOOKUP": "0"})
            self.assertEqual(done.returncode, 0)
            self.assertEqual(done.stderr, "")
        self.assertIn("Opus 5", self.run_script(fixture, extra_env={"CCSL_LIVE_LOOKUP": "0"}).stdout)

    def test_project_value_without_double_counting(self):
        # In-process: the sandbox sits in the temp folder, which only the
        # patched rules treat as an ordinary place.
        spec = importlib.util.spec_from_file_location("statusline_main", ROOT / "statusline.py")
        main = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(main)
        app = self.repo("code", "aurora")
        target = project_costs.summary_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"projects": [{"name": "aurora", "api_usd": 100.0}],
                                      "sessions": {"s1": {"aurora": 30.0}}}), encoding="utf-8")
        data = {"session_id": "s1", "workspace": {"current_dir": app},
                "cost": {"total_cost_usd": 40.0}, "model": {"display_name": "Opus"}}
        cfg = main.load_config({"CCSL_LIVE_LOOKUP": "0", "CCSL_SHOW_PROJECT": "1",
                                "CCSL_SHOW_COST": "1"})
        status = main.build_status(data, cfg)
        out = main.themes.render(status, cfg, 200, False)
        self.assertIn("aurora $110.00", out)
        self.assertIn("+$40.00", out)

    def test_demo_colors_diagnose_version(self):
        for flag in ("--demo", "--colors", "--diagnose", "--version"):
            done = self.run_script("", flag, extra_env={"CCSL_LIVE_LOOKUP": "0"})
            self.assertEqual(done.returncode, 0, flag)
            self.assertTrue(done.stdout.strip(), flag)


if __name__ == "__main__":
    unittest.main()
