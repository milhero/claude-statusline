import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from ccsl import cache, paths, refresh, sources
from tests.helpers import Sandbox

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PROFILE = {"account": {"email_address": "secret@example.org"},
           "organization": {"plan_display_label": "Ultra plan",
                            "rate_limit_tier": "default_claude_max_20x", "uuid": "secret-uuid"}}


def usage(token, timeout=10):
    return json.loads((FIXTURES / "usage_answer.json").read_text(encoding="utf-8"))


class TestStdin(unittest.TestCase):
    def test_full_input(self):
        data = json.loads((FIXTURES / "stdin_full.json").read_text(encoding="utf-8"))
        s = sources.from_stdin(data, "de")
        self.assertEqual((s.week.label, s.week.percent), ("Woche", 91))
        self.assertEqual(s.context.percent, 14)
        self.assertEqual((s.model, s.effort, s.branch), ("Opus 5", "high", "main"))
        self.assertAlmostEqual(s.cost_usd, 2.41)

    def test_anything_goes(self):
        for junk in (None, [], "x", {"rate_limits": "x", "model": 3, "cost": {"total_cost_usd": True}}):
            s = sources.from_stdin(junk)
            self.assertIsNone(s.week)
            self.assertIsNone(s.cost_usd)


class TestPlan(Sandbox):
    def test_tiers(self):
        self.assertEqual(sources.tier_from_name(None, "default_claude_max_5x"), ("Max 5x", "max_5x"))
        self.assertEqual(sources.tier_from_name("Ultra plan", "default_claude_max_20x"),
                         ("Ultra", "ultra"))
        self.assertEqual(sources.tier_from_name(None, "default_claude_mega"), ("mega", "unknown"))
        self.assertEqual(sources.tier_from_name("", None), (None, None))

    def test_plan_and_token_from_the_credentials_file(self):
        paths.credentials_file().write_text(json.dumps({"claudeAiOauth": {
            "rateLimitTier": "default_claude_pro", "accessToken": "sk-x"}}), encoding="utf-8")
        self.assertEqual(sources.read_plan(), ("Pro", "pro"))
        self.assertEqual(sources.read_token(), "sk-x")
        self.assertNotIn("sk-x", repr(sources.read_plan()))

    def test_keychain_only_on_macos(self):
        with mock.patch.object(sources.subprocess, "run") as run:
            with mock.patch.object(sys, "platform", "linux"):
                self.assertEqual(sources._keychain(), {})
            run.assert_not_called()

    def test_keychain_is_read_when_the_file_is_missing(self):
        answer = mock.Mock(returncode=0, stdout=json.dumps(
            {"claudeAiOauth": {"accessToken": "sk-key"}}))
        with mock.patch.object(sys, "platform", "darwin"), \
                mock.patch.object(sources.subprocess, "run", return_value=answer):
            self.assertEqual(sources.read_token(), "sk-key")
            self.assertEqual(sources.credentials_source(), "keychain")


class TestUsage(unittest.TestCase):
    def test_scoped_window_found_by_kind_with_label_from_answer(self):
        g = sources.scoped_gauge(usage(None))
        self.assertEqual((g.label, g.percent), ("Fable", 100))

    def test_reduce_keeps_only_whats_needed(self):
        reduced = sources.reduce_usage(usage(None))
        self.assertEqual({x["kind"] for x in reduced["limits"]},
                         {"session", "weekly_all", "weekly_scoped"})
        self.assertNotIn("member_dashboard_available", reduced)

    def test_profile_keeps_nothing_personal(self):
        reduced = sources.reduce_profile(PROFILE)
        self.assertEqual(reduced, {"name": "Ultra plan", "tier": "default_claude_max_20x"})
        self.assertEqual(sources.plan_from_cache({"plan": reduced}), ("Ultra", "ultra"))

    def test_fresher(self):
        from datetime import datetime, timezone
        from ccsl.model import Gauge
        t1 = datetime(2026, 9, 20, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 27, tzinfo=timezone.utc)
        self.assertEqual(sources.fresher(Gauge("w", "W", 90, t1), Gauge("w", "W", 5, t2)).percent, 5)
        self.assertEqual(sources.fresher(Gauge("w", "W", 40, t1), Gauge("w", "W", 42, t1)).percent, 42)


class TestCacheAndRefresh(Sandbox):
    def test_refresh_writes_usage_and_plan_without_secrets(self):
        target = cache.default_path()
        refresh.run_once(target, token="sk-x", fetch=usage,
                         fetch_profile=lambda t, timeout=10: PROFILE)
        text = target.read_text(encoding="utf-8")
        for secret in ("secret@example.org", "secret-uuid", "sk-x"):
            self.assertNotIn(secret, text)
        self.assertIn("Ultra plan", text)

    def test_failed_plan_lookup_keeps_the_old_plan(self):
        target = cache.default_path()
        refresh.run_once(target, "t", fetch=usage, fetch_profile=lambda t, timeout=10: PROFILE)

        def broken(t, timeout=10):
            raise OSError("offline")
        refresh.run_once(target, "t", fetch=usage, fetch_profile=broken)
        self.assertEqual(json.loads(target.read_text())["plan"]["name"], "Ultra plan")

    def test_injected_fetch_makes_no_hidden_profile_call(self):
        target = cache.default_path()
        with mock.patch.object(sources, "fetch_profile") as hidden:
            refresh.run_once(target, "t", fetch=usage)
            hidden.assert_not_called()

    def test_failure_is_remembered_and_pauses(self):
        target = cache.default_path()

        def broken(t, timeout=10):
            raise OSError("offline")
        refresh.run_once(target, "t", fetch=broken, fetch_profile=broken)
        self.assertTrue(cache.pause_after_failure(target, 300))
        self.assertIsNone(cache.read(target, 300))

    def test_no_token_no_lookup(self):
        self.assertEqual(refresh.run_once(cache.default_path(), None, fetch=usage), 0)
        self.assertFalse(cache.default_path().exists())

    def test_spawn_never_raises(self):
        def boom(*a, **k):
            raise OSError("no")
        refresh.spawn(starter=boom)

    def test_collect_only_when_on_and_due(self):
        calls = []
        self.assertFalse(refresh.collect_if_due({"cost_tracking": False},
                                                collect=lambda: calls.append(1)))
        self.assertTrue(refresh.collect_if_due({"cost_tracking": True},
                                               collect=lambda: calls.append(1)))
        self.assertFalse(refresh.collect_if_due({"cost_tracking": True},
                                                collect=lambda: calls.append(1)))
        self.assertEqual(calls, [1])

    def test_cache_honours_max_age(self):
        target = cache.default_path()
        cache.write(target, {"a": 1})
        self.assertEqual(cache.read(target, 300), {"a": 1})
        old = os.path.getmtime(target) - 4000
        os.utime(target, (old, old))
        self.assertIsNone(cache.read(target, 99999))


if __name__ == "__main__":
    unittest.main()
