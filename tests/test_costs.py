import json
import os
import time
import unittest
from datetime import date
from unittest import mock

from ccsl import (backfill, checks, compare, daily_rates, invoices as inv, other_machines,
                  project_costs, report)
from tests.helpers import Sandbox

INVOICES = [{"date": "2026-01-24", "amount": 20.0, "plan": "Pro"},
            {"date": "2026-03-08", "amount": 90.0, "plan": "Max 5x"},
            {"date": "2026-03-08", "amount": 10.0, "plan": "Max 5x"},
            {"date": "2026-02-02", "amount": 5.0, "kind": "extra"}]


class TestInvoices(unittest.TestCase):
    def test_same_day_invoices_add_up_and_extras_cover_no_span(self):
        merged = inv.ordered(INVOICES)
        self.assertEqual([(d.isoformat(), a) for d, a, _ in merged],
                         [("2026-01-24", 20.0), ("2026-03-08", 100.0)])
        self.assertEqual(inv.extras_total(INVOICES), 5.0)

    def test_daily_fee_until_next_invoice_then_open_span(self):
        self.assertAlmostEqual(inv.daily_fee(date(2026, 2, 1), INVOICES), 20.0 / 43)
        self.assertAlmostEqual(inv.daily_fee(date(2026, 5, 1), INVOICES), 100.0 / 30)
        self.assertEqual(inv.daily_fee(date(2025, 1, 1), INVOICES), 0.0)
        self.assertEqual(inv.plan_on(date(2026, 3, 9), INVOICES), "Max 5x")

    def test_spread(self):
        self.assertEqual(inv.spread({"a": 3, "b": 1}, 4.0), ({"a": 3.0, "b": 1.0}, 0.0))
        self.assertEqual(inv.spread({}, 4.0), ({}, 4.0))


class TestInvoiceFile(Sandbox):
    def test_round_trip_with_currency(self):
        inv.save(INVOICES, "EUR")
        loaded, currency = inv.load()
        self.assertEqual(currency, "EUR")
        self.assertEqual(len(loaded), 4)

    def test_missing_file_means_nothing(self):
        self.assertEqual(inv.load(), ([], None))


class TestDailyRates(unittest.TestCase):
    def test_missing_plans_derive_from_the_nearest_measured(self):
        full = daily_rates.derive({"Max 5x": 40.0, "Max 20x": 100.0})
        self.assertAlmostEqual(full["Pro"], 40.0 * (1 / 20) / (1 / 4))
        self.assertAlmostEqual(full["Ultra"], 100.0)

    def test_cap(self):
        self.assertEqual(daily_rates.apply_cap({"a": 30, "b": 10}, 20), {"a": 15.0, "b": 5.0})
        self.assertEqual(daily_rates.apply_cap({"a": 3}, 20), {"a": 3})


class FakeGit:
    def __init__(self, stdout, email="me@example.org"):
        self.stdout, self.email, self.calls = stdout, email, []

    def __call__(self, args, **kw):
        self.calls.append(args)
        if "config" in args:
            return mock.Mock(returncode=0, stdout=self.email + "\n")
        return mock.Mock(returncode=0, stdout=self.stdout)


class TestBackfill(Sandbox):
    def test_lines_skip_generated_files_and_only_own_commits_are_asked_for(self):
        out = ("\x002026-08-01\n10\t5\tsrc/a.py\n9000\t0\tpackage-lock.json\n"
               "30000\t0\tdata/corpus.txt\n-\t-\timg.png\n\x002026-08-02\n2\t0\tb.py\n")
        git = FakeGit(out)
        emails = backfill.author_emails("/repo", ["Extra@Example.org"], run=git)
        self.assertEqual(emails, ["extra@example.org", "me@example.org"])
        counts = backfill.lines_per_day("/repo", emails, run=git)
        self.assertEqual(counts, {date(2026, 8, 1): 15, date(2026, 8, 2): 2})
        self.assertIn("--author=<me@example.org>", git.calls[-1])

    def test_average_rate_only_from_projects_with_cost_and_lines(self):
        rates = backfill.rate_per_unit({"a": 10.0, "notes": 50.0}, {"a": 100, "notes": 0})
        self.assertEqual(rates, {"a": 0.1, "*": 0.1})

    def test_daily_values_respect_bounds(self):
        units = {"a": {date(2026, 1, 1): 10, date(2026, 2, 1): 10, date(2026, 3, 1): 10}}
        days = backfill.daily_values(units, {"a": 1.0}, until=date(2026, 3, 1),
                                     since=date(2026, 2, 1))
        self.assertEqual(days, {date(2026, 2, 1): {"a": 10.0}})

    def test_frozen_until_refreeze(self):
        calls = []

        def compute(*args):
            calls.append(1)
            return {date(2026, 1, 5): {"a": float(len(calls))}}, {"until": "2026-02-01"}
        args = ([], None, [], date(2026, 2, 1), [], {}, {})
        first, meta = backfill.get(*args, compute_fn=compute, min_days=0)
        again, _ = backfill.get(*args, compute_fn=compute, min_days=0)
        self.assertEqual(first, again)
        self.assertIn("created", meta)
        new, _ = backfill.get(*args, refreeze=True, compute_fn=compute, min_days=0)
        self.assertEqual(new[date(2026, 1, 5)]["a"], 2.0)

    def test_provisional_until_a_week_is_measured(self):
        calls = []

        def compute(*args):
            calls.append(1)
            return {}, {"until": "2026-02-01"}
        records = [{"start_ms": 1769900000000 + i * 86400000, "usd": 1} for i in range(3)]
        args = (records, None, [], date(2026, 2, 1), [], {}, {})
        _, meta = backfill.get(*args, compute_fn=compute)
        self.assertTrue(meta["provisional"])
        backfill.get(*args, compute_fn=compute)
        self.assertEqual(len(calls), 2)          # not frozen yet, computed again
        self.assertFalse(backfill.frozen_path().exists())

    def test_first_use_from_history_or_invoices(self):
        (self.claude / "history.jsonl").write_text(
            json.dumps({"timestamp": int(time.mktime((2026, 1, 10, 12, 0, 0, 0, 0, -1)) * 1000)})
            + "\n", encoding="utf-8")
        self.assertEqual(backfill.first_use(INVOICES), date(2026, 1, 10))


class TestChecks(unittest.TestCase):
    def result(self, **kw):
        base = {"projects": [{"name": "a", "api_usd": 10.0, "sub_share": 2.0,
                              "measured_usd": 6.0, "estimated_usd": 4.0}],
                "api_usd_total": 10.0, "subscription": {"paid": 3.0, "assigned": 2.0,
                                                        "unused": 1.0}}
        base.update(kw)
        return base

    def test_consistent_result_passes(self):
        found = checks.run(self.result(), INVOICES, today=date(2026, 3, 20))
        self.assertTrue(all(f["ok"] for f in found), found)

    def test_overdue_invoice_and_format_change_are_reported(self):
        found = checks.run(self.result(), INVOICES, today=date(2026, 6, 1),
                           recent_logs=(9, 0), lang="de")
        bad = [f["text"] for f in found if not f["ok"]]
        self.assertEqual(len(bad), 2)
        self.assertTrue(any("Protokollformat" in t for t in bad))

    def test_double_counted_process_is_found(self):
        records = [{"usd": 50, "processes": {"p": 50}}, {"usd": 50, "processes": {"p": 50}}]
        found = checks.run(self.result(), records=records)
        self.assertFalse([f for f in found if "counted twice" in f["text"]][0]["ok"])


class TestHistoryFile(Sandbox):
    def test_one_line_per_day(self):
        result = {"api_usd_total": 5, "projects": [{"name": "a", "api_usd": 5}]}
        checks.write_history(None, result, date(2026, 9, 1), [])
        checks.write_history(None, dict(result, api_usd_total=7), date(2026, 9, 1), [])
        lines = checks.read_history()
        self.assertEqual([(x["day"], x["total"]) for x in lines], [("2026-09-01", 7)])


class TestSmallParts(Sandbox):
    def test_compare_only_shows_ultra_when_measured(self):
        rows = compare.weeks_per_plan(700.0, {"Max 20x": 100.0})
        self.assertNotIn("Ultra", rows)
        self.assertEqual(rows["Max 20x"]["weeks"], 1.0)
        self.assertTrue(rows["Free"]["without_large_models"])

    def test_other_machines(self):
        other_machines.default_path().parent.mkdir(parents=True, exist_ok=True)
        other_machines.default_path().write_text(json.dumps([
            {"project": "aurora", "source": "laptop", "from": "2026-09-01", "to": "2026-09-30",
             "models": {"m": {"out": 1000}}}]), encoding="utf-8")
        valued = other_machines.value(other_machines.read(), {"m": 0.002})
        self.assertEqual(valued[0]["usd"], 10.0)
        self.assertEqual(other_machines.value(other_machines.read(), {}, project="x"), [])

    def test_project_costs_from_fresh_summary_only(self):
        target = project_costs.summary_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"projects": [{"name": "aurora", "api_usd": 120.0}],
                                      "sessions": {"s1": {"aurora": 20.0}}}), encoding="utf-8")
        entry = project_costs.for_project("aurora", session="s1")
        self.assertEqual((entry["api_usd"], entry["session_usd"]), (120.0, 20.0))
        self.assertEqual(project_costs.for_project("new")["api_usd"], 0.0)
        old = time.time() - 30 * 3600
        os.utime(target, (old, old))
        self.assertTrue(project_costs.for_project("aurora")["stale"])


class TestReport(unittest.TestCase):
    RESULT = {"period": {"from": "2026-09-01", "to": "2026-09-30", "active_days": 20},
              "projects": [{"name": "aurora", "api_usd": 1500.0, "share": 0.75,
                            "sub_share": 80.0, "compute_h": 10.0, "measured_usd": 500.0,
                            "estimated_usd": 1000.0},
                           {"name": "Unassigned", "api_usd": 500.0, "share": 0.25,
                            "sub_share": 20.0, "compute_h": 2.0, "measured_usd": 500.0,
                            "estimated_usd": 0.0}],
              "api_usd_total": 2000.0, "compute_total": 12.0,
              "subscription": {"paid": 120.0, "assigned": 100.0, "unused": 20.0, "extra": 0,
                               "total": 120.0}, "leverage": 20.0}

    def test_table_in_both_languages(self):
        en = report.table(self.RESULT, 100, False, "EUR", "en")
        self.assertIn("~ aurora", en)
        self.assertIn("$1,500.00", en)
        self.assertIn("€80.00", en)
        de = report.table(self.RESULT, 100, False, "EUR", "de")
        self.assertIn("1.500,00 $", de)
        self.assertIn("80,00 €", de)
        self.assertIn("Nicht zuzuordnen", de)

    def test_without_invoices_the_column_goes(self):
        out = report.table(dict(self.RESULT, subscription={"paid": 0}), 100, False, None, "en")
        self.assertNotIn("Subscription", out)

    def test_small_items_merge(self):
        projects = [{"name": "big", "api_usd": 1000}, {"name": "x", "api_usd": 1},
                    {"name": "y", "api_usd": 1}]
        merged = report.merge_small(projects, 1002, "en")
        self.assertEqual([p["name"] for p in merged], ["big", "Smaller projects"])

    def test_other_views_render(self):
        for lang in ("en", "de"):
            self.assertTrue(report.by_source(self.RESULT, False, lang))
            self.assertTrue(report.formula(self.RESULT, INVOICES, False, "EUR", lang))
            self.assertTrue(report.comparison(dict(self.RESULT, daily_rates={"Pro": 5.0}),
                                              None, False, lang))
            self.assertTrue(report.history([{"day": "2026-09-01", "total": 5}], False, lang))


if __name__ == "__main__":
    unittest.main()
