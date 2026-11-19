"""claude-costs: what the work cost, per project.

Two figures: what the same work would have cost through the API, and which
part of the subscription fee actually paid falls on the project.

Unlike the status line, this command may and should show errors: it is run
on purpose, and a silent malfunction would be worse than a message.
"""

import argparse
import calendar
import json
import os
import re
import shutil
import sys
from datetime import date, datetime, timedelta, timezone

from . import (archive, attribution, backfill, checks, config, daily_rates, discover,
               draw, i18n, invoices as inv, other_machines, paths, project_costs, report,
               rules as rules_mod, sources)

# The summary keeps each session's share for this long. The status line only
# needs it for sessions that may still be resumed.
SESSIONS_DAYS = 60

i18n.add({
    "cli_desc": ("What the work cost, per project.", "Was die Arbeit je Projekt gekostet hat."),
    "cli_empty": ("The archive is empty. Are there logs in {path}?",
                  "Das Archiv ist leer. Gibt es Protokolle unter {path}?"),
    "cli_collected": ("Archive: {total} sessions, {new} new.",
                      "Archiv: {total} Sitzungen, davon {new} neu."),
    "cli_busy": ("Another run is updating the archive right now.",
                 "Ein anderer Lauf schreibt gerade das Archiv fort."),
    "cli_no_project": ("No project contains \"{name}\". Present: {names}",
                       "Kein Projekt enthält „{name}“. Vorhanden: {names}"),
    "cli_bad_period": ("Invalid period: {text}. Allowed: 2026, 2026-09 or 2026-09-05.",
                       "Ungültiger Zeitraum: {text}. Erlaubt sind 2026, 2026-09 oder 2026-09-05."),
    "cli_written": ("Written: {path}", "Geschrieben: {path}"),
    "cli_check": ("Check: {text}", "Prüfung: {text}"),
    "cli_collect_failed": ("The archive could not be updated: {error}",
                           "Das Archiv konnte nicht fortgeschrieben werden: {error}"),
})


def width():
    try:
        cols = int(os.environ.get("COLUMNS", "0"))
        if cols > 0:
            return cols
    except ValueError:
        pass
    try:
        return shutil.get_terminal_size((100, 24)).columns
    except Exception:
        return 100


def period_bounds(text):
    """'2026-09' -> (2026-09-01, 2026-09-30), '2026' -> the whole year.

    An invalid period raises ValueError instead of silently turning June
    into "from June on, without end".
    """
    if not text:
        return None, None
    text = text.strip()
    if re.fullmatch(r"\d{4}", text):
        return text + "-01-01", text + "-12-31"
    if re.fullmatch(r"\d{4}-\d{2}", text):
        y, m = int(text[:4]), int(text[5:])
        if not 1 <= m <= 12:
            raise ValueError(text)
        return "{}-01".format(text), "{}-{:02d}".format(text, calendar.monthrange(y, m)[1])
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        date.fromisoformat(text)
        return text, text
    raise ValueError(text)


def color_on(setting, env, is_tty):
    """Colour only when the output lands on a terminal.

    The status line always colours, Claude Code renders it. This command
    also ends up in less, a file or a log, where escape codes get in the way.
    """
    if setting == "always":
        return True
    return is_tty and draw.color_enabled(setting, env)


def parser(lang):
    de = lang == "de"
    p = argparse.ArgumentParser(prog="claude-costs", description=i18n.t("cli_desc", lang))
    add = p.add_argument
    add("--by-source", action="store_true",
        help="Gemessen gegen geschätzt, je Projekt" if de else "measured vs. estimated, per project")
    add("--formula", action="store_true",
        help="Wie gerechnet wird, mit den benutzten Sätzen" if de else
        "how it is computed, with the rates used")
    add("--period", metavar="2026-09",
        help="Nur ein Zeitraum: 2026, 2026-09 oder 2026-09-05" if de else
        "one period only: 2026, 2026-09 or 2026-09-05")
    add("--project", metavar="NAME", help="Nur ein Projekt" if de else "one project only")
    add("--measured-only", action="store_true",
        help="Ohne Hochrechnung" if de else "without the backfill estimate")
    add("--compare", action="store_true",
        help="Wie lange dieselbe Arbeit mit anderen Stufen gedauert hätte" if de else
        "how long the same work would have taken on other plans")
    add("--check", action="store_true", help="Selbstprüfung" if de else "self-check")
    add("--history", action="store_true",
        help="Die Summen Tag für Tag" if de else "the totals day by day")
    add("--refreeze", action="store_true",
        help="Hochrechnung neu festschreiben" if de else "recompute and freeze the backfill")
    add("--collect", action="store_true",
        help="Nur das Archiv fortschreiben" if de else "only update the archive")
    add("--json", action="store_true",
        help="Nur die Schnittstellendatei schreiben" if de else "only write the summary file")
    add("--discover", action="store_true",
        help="Bestandsaufnahme als JSON (für die Einrichtung)" if de else
        "fact-finding as JSON (for the setup)")
    add("--lang", choices=("en", "de"), help="Sprache" if de else "language")
    add("--version", action="version", version="claude-costs " + sources.VERSION)
    return p


def _recent_sessions(records, today):
    limit = today - timedelta(days=SESSIONS_DAYS)
    return {r.get("session") for r in records
            if (attribution.day_of(r.get("start_ms")) or date.min) >= limit}


class Run:
    """One evaluation: everything loaded once, then shaped as asked."""

    def __init__(self, cfg, env=None):
        self.cfg = cfg
        self.env = env
        self.records = archive.read(archive.archive_path(env))
        self.user_rules = rules_mod.load(env=env)
        self.ctx = rules_mod.Context(self.user_rules, roots=cfg.get("project_roots"),
                                     env=env, known_roots=attribution.known_roots(self.records))
        self.invoices, self.currency = inv.load(env=env)
        if self.invoices and not self.currency:
            # Shown as "?" rather than guessed; the self-check says why.
            self.currency = "?"
        self.today = checks.today_local()
        self.rates = daily_rates.measured(self.records, self.invoices)
        self.start = backfill.archive_start(self.records)

    def summary(self, start=None, end=None, measured_only=False, refreeze=False, lang="en"):
        backfill_days, meta = {}, None
        if not measured_only:
            backfill_days, meta = backfill.get(
                self.records, self.ctx, self.user_rules, self.start, self.invoices,
                self.rates, self.cfg, path=backfill.frozen_path(self.env), refreeze=refreeze)
        result = attribution.evaluate(self.records, self.ctx, self.invoices, start=start,
                                      end=end, backfill_days=backfill_days, rates=self.rates)
        result["daily_rates"] = self.rates
        result["backfill"] = meta
        if start:
            result["period"]["requested"] = [start, end]
        recent = archive.logs_without_cost_lines(paths.logs_dir(self.env))
        findings = checks.run(result, self.invoices, self.records, today=self.today,
                              backfill_meta=meta,
                              archive_start=self.start.isoformat() if self.start else None,
                              currency=self.currency, lang=lang, recent_logs=recent)
        result["checks"] = findings
        return result

    def write_summary(self, result):
        content = dict(result)
        recent = _recent_sessions(self.records, self.today)
        content["sessions"] = {k: v for k, v in (result.get("sessions") or {}).items()
                               if k in recent}
        content["currency"] = self.currency
        content["daily_rates_derived"] = daily_rates.derive(self.rates)
        content["generated"] = datetime.now(timezone.utc).astimezone().isoformat(
            timespec="seconds")
        target = project_costs.summary_path(self.env)
        paths.write_atomic(target, json.dumps(content, indent=2, ensure_ascii=False,
                                              default=str) + "\n")
        checks.write_history(checks.history_path(self.env), result, self.today,
                             result.get("checks"))
        return target


def collect(cfg=None, env=None):
    cfg = cfg or config.load(env=env)
    records = archive.read(archive.archive_path(env))
    ctx = rules_mod.Context(rules_mod.load(env=env), roots=cfg.get("project_roots"), env=env,
                            known_roots=attribution.known_roots(records))
    return archive.collect(paths.logs_dir(env), archive.archive_path(env), ctx=ctx,
                           state=archive.state_path(env))


def collect_and_summarize(env=None):
    """What the status line's background process runs every few hours."""
    cfg = config.load(env=env)
    if collect(cfg, env).get("busy"):
        # Another window is writing the archive right now; its run will
        # write the summary. Writing one now would use old numbers.
        return
    run = Run(cfg, env)
    if run.records:
        result = run.summary(lang=i18n.resolve(cfg.get("language")))
        result["other_machines"] = other_machines.value(
            other_machines.read(other_machines.default_path(env)),
            archive.derive_prices(run.records))
        run.write_summary(result)


def main(argv=None, env=None):
    cfg = config.load(env=env)
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--lang", choices=("en", "de"))
    known, _ = pre.parse_known_args(argv)
    lang = known.lang or i18n.resolve(cfg.get("language"), env)
    args = parser(lang).parse_args(argv)

    try:
        start, end = period_bounds(args.period)
    except ValueError:
        print(i18n.t("cli_bad_period", lang, text=args.period), file=sys.stderr)
        return 1

    # The archive is updated on every call. Claude Code deletes its logs
    # after 30 days; whoever uses the command now and then loses nothing,
    # even without the status line running.
    try:
        collected = collect(cfg, env)
    except Exception as error:
        print(i18n.t("cli_collect_failed", lang, error=error), file=sys.stderr)
        collected = {"new": 0, "total": 0}

    if args.collect:
        if collected.get("busy"):
            print(i18n.t("cli_busy", lang))
        else:
            print(i18n.t("cli_collected", lang, total=collected.get("total", 0),
                         new=collected.get("new", 0)))
        return 0

    color = color_on(cfg.get("color", "auto"), os.environ if env is None else env,
                     sys.stdout.isatty())

    if args.history:
        print(report.history(checks.read_history(checks.history_path(env)), color, lang))
        return 0

    run = Run(cfg, env)
    if args.discover:
        print(discover.as_json(discover.run(env=env, records=run.records, cfg=cfg)))
        return 0
    if not run.records:
        print(i18n.t("cli_empty", lang, path=paths.logs_dir(env)))
        return 0

    filtered = bool(args.period or args.project or args.measured_only)
    result = run.summary(start, end, measured_only=args.measured_only,
                         refreeze=args.refreeze, lang=lang)

    if args.project:
        wanted = args.project.lower()
        chosen = [p for p in result["projects"] if wanted in p["name"].lower()]
        if not chosen:
            print(i18n.t("cli_no_project", lang, name=args.project,
                         names=", ".join(p["name"] for p in result["projects"])),
                  file=sys.stderr)
            return 1
        result = dict(result, projects=chosen, only_project=args.project)

    result["other_machines"] = other_machines.value(
        other_machines.read(other_machines.default_path(env)),
        archive.derive_prices(run.records), project=args.project, start=start, end=end)

    # A filtered view must never overwrite the summary: the status line would
    # show only that slice until the next full run.
    if not filtered:
        try:
            target = run.write_summary(result)
        except Exception as error:
            print(str(error), file=sys.stderr)
            target = None

    failing = [f for f in result.get("checks") or [] if not f["ok"]]
    if args.json:
        if not filtered and target:
            print(i18n.t("cli_written", lang, path=target))
        for f in failing:
            print(i18n.t("cli_check", lang, text=f["text"]), file=sys.stderr)
        return 0
    if args.check:
        print(report.checks(result.get("checks"), color, lang))
        return 1 if failing else 0
    if args.formula:
        print(report.formula(result, run.invoices, color, run.currency, lang))
        return 0
    if args.by_source:
        print(report.by_source(result, color, lang))
        return 0
    if args.compare:
        print(report.comparison(result, args.project, color, lang))
        return 0

    print(report.table(result, width(), color, run.currency, lang))
    if not run.invoices:
        print()
        print(draw.paint(i18n.t("rep_no_invoices", lang, path=inv.default_path(env)),
                         "quiet", color))
    if failing:
        print()
        for f in failing:
            print(draw.paint(i18n.t("cli_check", lang, text=f["text"]), "warn", color))
    return 0


def utf8_output():
    """Write UTF-8 explicitly. Windows hands a pipe cp1252, and every line,
    tick and umlaut of the table would break on it."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
