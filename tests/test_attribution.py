import unittest
from datetime import date, datetime

from ccsl import attribution, rules
from tests.helpers import Sandbox


def ms(day, hour=12):
    return int(datetime(day.year, day.month, day.day, hour).timestamp() * 1000)


class TestShares(Sandbox):
    def test_text_without_place_spreads_over_recognised_work(self):
        a, b = self.repo("a"), self.repo("b")
        shares = attribution.session_shares({"cwd": {a: 30}, "paths": {b + "/src": 10}},
                                            rules.Context([]))
        self.assertEqual(shares, {"a": 0.75, "b": 0.25})

    def test_secondary_only_counts_without_projects(self):
        ctx = rules.Context([{"prefix": "/notes", "project": "Notes", "rank": "secondary"}])
        repo = self.repo("app")
        self.assertEqual(attribution.session_shares(
            {"cwd": {repo: 1}, "paths": {"/notes/x": 100}}, ctx), {"app": 1.0})
        self.assertEqual(attribution.session_shares({"paths": {"/notes/x": 5}}, ctx),
                         {"Notes": 1.0})

    def test_nothing_recognised_is_unassigned(self):
        self.assertEqual(attribution.session_shares({"cwd": {"/opt/x": 1}}, rules.Context([])),
                         {attribution.UNASSIGNED: 1.0})


class TestEvaluate(Sandbox):
    def setUp(self):
        super().setUp()
        self.app = self.repo("app")
        self.ctx = rules.Context([])

    def record(self, day, usd, sid="s"):
        return {"session": sid, "start_ms": ms(day), "usd": usd, "api_ms": 3_600_000,
                "cwd": {self.app: 1}}

    def test_fee_spreads_over_days_and_unused_days_stay_unused(self):
        invoices = [{"date": "2026-09-01", "amount": 30.0, "plan": "Pro"},
                    {"date": "2026-10-01", "amount": 30.0, "plan": "Pro"}]
        records = [self.record(date(2026, 9, 1), 10), self.record(date(2026, 9, 3), 5, "t")]
        result = attribution.evaluate(records, self.ctx, invoices)
        sub = result["subscription"]
        self.assertAlmostEqual(sub["paid"], 3.0)          # three days at 1.00
        self.assertAlmostEqual(sub["assigned"], 2.0)
        self.assertAlmostEqual(sub["unused"], 1.0)
        self.assertEqual(result["projects"][0]["api_usd"], 15.0)
        self.assertEqual(result["projects"][0]["compute_h"], 2.0)

    def test_without_invoices_no_subscription_share(self):
        result = attribution.evaluate([self.record(date(2026, 9, 1), 10)], self.ctx, [])
        self.assertEqual(result["subscription"]["paid"], 0)
        self.assertIsNone(result["leverage"])

    def test_backfill_is_capped_by_measured_day(self):
        invoices = [{"date": "2026-08-01", "amount": 100.0, "plan": "Max 5x"}]
        records = [self.record(date(2026, 9, 1), 40)]
        backfill = {date(2026, 8, 20): {"app": 500.0}}
        rates = {"Max 5x": 40.0}
        result = attribution.evaluate(records, self.ctx, invoices, backfill_days=backfill,
                                      rates=rates)
        p = result["projects"][0]
        self.assertAlmostEqual(p["estimated_usd"], 40.0)
        self.assertAlmostEqual(p["measured_usd"], 40.0)

    def test_period_filter_and_session_shares(self):
        records = [self.record(date(2026, 9, 1), 10, "a"), self.record(date(2026, 10, 1), 7, "b")]
        result = attribution.evaluate(records, self.ctx, [], start="2026-10-01",
                                      end="2026-10-31")
        self.assertEqual(result["api_usd_total"], 7.0)
        self.assertEqual(result["sessions"], {"b": {"app": 7.0}})


if __name__ == "__main__":
    unittest.main()
