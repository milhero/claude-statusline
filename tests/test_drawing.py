import os
import unittest
from datetime import datetime, timedelta, timezone

from ccsl import config, draw, i18n, themes
from ccsl.model import Gauge, Status
from tests.helpers import Sandbox

UTC = timezone.utc


class TestDraw(unittest.TestCase):
    def test_levels_are_inclusive(self):
        self.assertEqual([draw.level(p, 50, 80) for p in (49, 50, 80)], ["ok", "warn", "crit"])
        self.assertEqual(draw.level("x", 50, 80), "ok")

    def test_truncate_keeps_colour_intact(self):
        text = draw.paint("abcdef", "warn", True)
        cut = draw.truncate(text, 3)
        self.assertEqual(draw.visible_len(cut), 3)
        self.assertTrue(cut.endswith(draw.RESET))

    def test_gauges(self):
        self.assertEqual(draw.gauge(0, 10), "")
        self.assertEqual(draw.gauge(1, 10), "━")                  # never invisible above zero
        self.assertEqual(draw.gauge(50, 10, track=True), "━" * 5 + "╌" * 5)
        self.assertEqual(draw.gauge(100, 1, "circle"), "●")
        self.assertEqual(draw.gauge(0, 1, "spark"), "▁")
        self.assertEqual(draw.gauge(55, 2, "block"), "█▏")
        self.assertEqual(draw.gauge(200, 4, "unknown-style"), "━━━━")

    def test_reset_by_calendar_day_in_both_languages(self):
        now = datetime(2026, 9, 15, 21, 0, tzinfo=UTC)          # a Tuesday
        tomorrow = datetime(2026, 9, 16, 8, 0, tzinfo=UTC)
        later = datetime(2026, 9, 19, 8, 0, tzinfo=UTC)
        self.assertEqual(draw.format_reset(tomorrow, now), "tomorrow 08:00")
        self.assertEqual(draw.format_reset(tomorrow, now, "de"), "morgen 08:00")
        self.assertEqual(draw.format_reset(later, now, "de"), "Sa 08:00")
        self.assertEqual(draw.format_reset(later, now), "Sat 08:00")
        self.assertEqual(draw.format_reset(now - timedelta(hours=1), now), "")

    def test_plan_span_grows_with_the_tier_and_ultra_gets_the_full_family(self):
        spans = [len(draw.plan_ramp("violet", t)) for t in ("pro", "max_5x", "max_20x", "ultra")]
        self.assertEqual(spans, sorted(spans))
        self.assertEqual(spans[-1], len(draw.FAMILIES["violet"]))
        self.assertGreater(spans[-1], spans[-2])
        self.assertEqual(len(draw.plan_ramp("nonsense", None)), 1)

    def test_model_colour_by_family_and_effort(self):
        self.assertEqual(draw.model_ramp("Fable 5", "max"), draw.MODEL_FAMILIES["fable"][3:7])
        self.assertEqual(draw.model_ramp("Haiku 5", None), draw.MODEL_FAMILIES["haiku"][:2])
        self.assertTrue(draw.effort_bold("xhigh"))
        self.assertEqual(draw.effort_name("xhigh", True), "ultracode")
        self.assertEqual(draw.effort_name("xhigh"), "xhigh")

    def test_gradient_leaves_spaces_alone(self):
        out = draw.gradient("A B", (1, 2), True)
        self.assertIn(" ", draw.ANSI.sub("", out))
        self.assertEqual(draw.gradient("AB", (1, 2), False), "AB")

    def test_colour_switch(self):
        self.assertFalse(draw.color_enabled("auto", {"NO_COLOR": "1", "TERM": "xterm"}))
        self.assertTrue(draw.color_enabled("always", {"NO_COLOR": "1"}))
        self.assertTrue(draw.color_enabled("auto", {"WT_SESSION": "x"}))


class TestI18n(unittest.TestCase):
    def test_language_from_environment(self):
        self.assertEqual(i18n.resolve("auto", {"LANG": "de_DE.UTF-8"}), "de")
        self.assertEqual(i18n.resolve("auto", {"LC_ALL": "en_GB.UTF-8", "LANG": "de_DE"}), "en")
        self.assertEqual(i18n.resolve("de", {"LANG": "en_US"}), "de")
        if os.name != "nt":
            self.assertEqual(i18n.resolve("auto", {}), "en")

    def test_money(self):
        self.assertEqual(i18n.money(1234.5), "$1,234.50")
        self.assertEqual(i18n.money(1234.5, "USD", "de"), "1.234,50 $")
        self.assertEqual(i18n.money(12, "EUR", "en"), "€12.00")
        self.assertEqual(i18n.money(12, "CHF", "en"), "CHF 12.00")
        self.assertEqual(i18n.money(4.2, "USD", "en", plus=True), "+$4.20")
        self.assertEqual(i18n.percent(69.51, 1, "de"), "69,5 %")


class TestConfig(Sandbox):
    def test_defaults_without_file(self):
        cfg = config.load(env={})
        self.assertEqual(cfg["theme"], "calm-one-line")
        self.assertFalse(cfg["cost_tracking"])

    def test_wrong_types_fall_back_and_unknown_keys_are_ignored(self):
        config.save({"theme": "nope", "cache_seconds": True, "thresholds": {"warn": "x"},
                     "bogus": 1, "project_roots": ["~/code", 3]})
        cfg = config.load()
        self.assertEqual(cfg["theme"], "calm-one-line")
        self.assertEqual(cfg["cache_seconds"], 300)
        self.assertEqual(cfg["thresholds"]["warn"], 50)
        self.assertEqual(cfg["project_roots"], [])
        self.assertNotIn("bogus", cfg)

    def test_environment_wins(self):
        config.save({"theme": "traffic"})
        cfg = config.load(env={"CCSL_THEME": "expressive", "CCSL_SHOW_COST": "1",
                               "CCSL_CACHE_SECONDS": "60", "CCSL_LANGUAGE": "de"})
        self.assertEqual((cfg["theme"], cfg["show"]["cost"], cfg["cache_seconds"],
                          cfg["language"]), ("expressive", True, 60, "de"))

    def test_save_merges(self):
        config.save({"show": {"cost": True}})
        config.save({"show": {"project": True}})
        cfg = config.load()
        self.assertTrue(cfg["show"]["cost"] and cfg["show"]["project"])


def status(**kw):
    later = datetime.now(UTC) + timedelta(days=3)
    base = dict(week=Gauge("week", "Week", 91, later), scoped=Gauge("model_week", "Fable", 38),
                five_hour=Gauge("five_hour", "5h", 12), context=Gauge("context", "Context", 22),
                plan="Max 20x", plan_tier="max_20x", model="Opus 5 (1M context)",
                effort="high", directory="~/code/aurora", branch="main", cost_usd=2.41)
    base.update(kw)
    return Status(**base)


class TestThemes(unittest.TestCase):
    def cfg(self, theme, **extra):
        cfg = config.load(path=os.devnull, env={})
        cfg["theme"] = theme
        cfg["show"]["cost"] = True
        cfg["_lang"] = extra.pop("lang", "en")
        cfg.update(extra)
        return cfg

    def test_every_layout_fits_every_width_and_keeps_the_plan(self):
        for theme in config.THEMES:
            for width in (20, 40, 60, 80, 120, 200):
                out = themes.render(status(), self.cfg(theme), width, color=False)
                for line in out.split("\n"):
                    self.assertLessEqual(draw.visible_len(line), width, (theme, width))
                self.assertIn("MAX 20×", out.replace("\n", " "), (theme, width))

    def test_wide_line_shows_more(self):
        narrow = themes.render(status(), self.cfg("calm-one-line"), 70, False)
        wide = themes.render(status(), self.cfg("calm-one-line"), 200, False)
        self.assertNotIn("~/code/aurora", narrow)
        self.assertIn("~/code/aurora", wide)
        self.assertIn("↻", wide)

    def test_session_cost_carries_a_plus_next_to_the_project_value(self):
        cfg = self.cfg("calm-one-line")
        cfg["show"]["project"] = True
        out = themes.render(status(project="aurora", project_usd=120.0), cfg, 220, False)
        self.assertIn("aurora $120.00", out)
        self.assertIn("+$2.41", out)
        alone = themes.render(status(project="aurora", project_usd=2.41), cfg, 220, False)
        self.assertEqual(alone.count("2.41"), 1)

    def test_german_labels_and_money(self):
        lang = "de"
        s = status(week=Gauge("week", i18n.t("week", lang), 91),
                   context=Gauge("context", i18n.t("context", lang), 22))
        out = themes.render(s, self.cfg("calm-two-line", lang=lang), 160, False)
        self.assertIn("Woche", out)
        self.assertIn("2,41 $", out)

    def test_big_amounts_drop_cents(self):
        cfg = self.cfg("calm-one-line")
        cfg["show"]["project"] = True
        out = themes.render(status(project="aurora", project_usd=15465.2), cfg, 220, False)
        self.assertIn("$15,465", out)
        self.assertNotIn("15,465.20", out)


if __name__ == "__main__":
    unittest.main()
