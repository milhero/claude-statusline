"""Self-check of the balance, and its history over the days.

Every full run checks whether the numbers add up, and keeps the result per
day in a history file. When a total jumps, that shows on which day and in
which part.

The checks are counter-calculations, not repetitions of the same sum: what
holds here holds from a second angle.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from . import i18n, invoices as inv, paths

# The next subscription invoice is due after this many days at the latest.
# Missing, the balance keeps going with the amount of the last one.
INVOICE_DUE_AFTER = 31

# Rounding: every project value is rounded to cents, the total is not.
CENT = 0.01

# Below this many recent logs a missing cost line can just be a session that
# is still running.
MIN_RECENT_LOGS = 5

i18n.add({
    "chk_sub": ("Subscription check: {assigned} assigned plus {unused} unused makes {paid} paid",
                "Abo-Probe: {assigned} zugeordnet plus {unused} ungenutzt ergibt {paid} gezahlt"),
    "chk_sum": ("Projects add up to the total: {api} API value, {sub} subscription share",
                "Projekte ergeben die Summe: {api} API-Wert, {sub} Abo-Anteil"),
    "chk_split_ok": ("Measured plus estimated equals the API value for every project",
                     "Gemessen plus geschätzt ergibt je Projekt den API-Wert"),
    "chk_split_bad": ("Measured plus estimated differs for: {names}",
                      "Gemessen plus geschätzt weicht ab bei: {names}"),
    "chk_invoice_ok": ("Last subscription invoice from {date}, {days} days ago",
                       "Letzte Abo-Rechnung vom {date}, vor {days} Tagen"),
    "chk_invoice_bad": ("Last subscription invoice from {date} is {days} days old: is one "
                        "missing? Until then its amount carries on",
                        "Letzte Abo-Rechnung vom {date} ist {days} Tage alt: fehlt eine "
                        "Rechnung? Bis dahin wird mit ihrem Betrag weitergerechnet"),
    "chk_proc_ok": ("Every process counted once: {usd} measured",
                    "Jeder Prozess einmal gezählt: {usd} gemessen"),
    "chk_proc_bad": ("A process counted twice: sessions add up to {usd}, the processes "
                     "only to {expected}",
                     "Prozess doppelt gezählt: Sitzungen ergeben {usd}, die Prozesse "
                     "nur {expected}"),
    "chk_backfill_ok": ("Backfill frozen on {created}, for the time before {until}",
                        "Hochrechnung festgeschrieben am {created}, für die Zeit vor dem "
                        "{until}"),
    "chk_backfill_bad": ("Backfill ends on {until}, the archive starts on {start}: run "
                         "claude-costs --refreeze",
                         "Hochrechnung endet am {until}, das Archiv beginnt am {start}: "
                         "claude-costs --refreeze"),
    "chk_backfill_provisional": ("Backfill provisional until a week is measured; it is "
                                 "frozen after that",
                                 "Hochrechnung vorläufig, bis eine Woche gemessen ist; "
                                 "danach wird sie festgeschrieben"),
    "chk_no_currency": ("Invoices have no currency: add \"currency\" (e.g. \"EUR\") to "
                        "invoices.json",
                        "Rechnungen ohne Währung: \"currency\" (etwa \"EUR\") in "
                        "invoices.json eintragen"),
    "chk_format_bad": ("{recent} logs from the last 7 days, none with a cost line: Claude "
                       "Code's log format has probably changed, costs are not being "
                       "measured",
                       "{recent} Protokolle der letzten 7 Tage, keines mit Kostenzeile: "
                       "das Protokollformat von Claude Code hat sich vermutlich geändert, "
                       "es wird nichts gemessen"),
    "chk_format_ok": ("Cost lines found in {with_cost} of {recent} recent logs",
                      "Kostenzeilen in {with_cost} von {recent} aktuellen Protokollen"),
})


def history_path(env=None):
    return paths.data_file("cost-history.jsonl", env)


def _date(iso, lang):
    day = inv.as_date(str(iso)[:10]) if iso else None
    if not day:
        return str(iso)
    return day.strftime("%d.%m.%Y") if lang == "de" else day.isoformat()


def _finding(ok, text):
    return {"ok": bool(ok), "text": text}


def run(result, invoices=None, records=None, today=None, backfill_meta=None,
        archive_start=None, currency=None, lang="en", recent_logs=None):
    """A list of findings {ok, text}."""
    findings = []
    projects = result.get("projects") or []
    sub = result.get("subscription") or {}
    tolerance = CENT * max(1, len(projects))
    cur = currency or "USD"

    def money(v, c=cur):
        return i18n.money(v, c, lang)

    # 1. The fee is spread completely: what no project got stands as unused.
    paid = sub.get("paid") or 0
    assigned = sub.get("assigned") or 0
    unused = sub.get("unused") or 0
    if invoices:
        findings.append(_finding(
            abs(assigned + unused - paid) <= 0.05,
            i18n.t("chk_sub", lang, assigned=money(assigned), unused=money(unused),
                   paid=money(paid))))

    if invoices and cur == "?":
        findings.append(_finding(False, i18n.t("chk_no_currency", lang)))

    # 2. The projects add up to the total, for API value and subscription share.
    sum_api = sum(p.get("api_usd") or 0 for p in projects)
    total_api = result.get("api_usd_total") or 0
    sum_sub = sum(p.get("sub_share") or 0 for p in projects)
    findings.append(_finding(
        abs(sum_api - total_api) <= tolerance and abs(sum_sub - assigned) <= tolerance,
        i18n.t("chk_sum", lang, api=money(sum_api, "USD"), sub=money(sum_sub))))

    # 3. Per project: measured plus estimated is the API value.
    off = [p.get("name") for p in projects
           if abs((p.get("measured_usd") or 0) + (p.get("estimated_usd") or 0)
                  - (p.get("api_usd") or 0)) > 2 * CENT]
    findings.append(_finding(
        not off, i18n.t("chk_split_ok", lang) if not off
        else i18n.t("chk_split_bad", lang, names=", ".join(off))))

    # 4. The last subscription invoice is not overdue.
    subs = [inv.as_date(e.get("date")) for e in (invoices or [])
            if isinstance(e, dict) and (e.get("kind") or "subscription") == "subscription"]
    subs = [d for d in subs if d]
    if subs and today:
        last = max(subs)
        age = (today - last).days
        key = "chk_invoice_ok" if age <= INVOICE_DUE_AFTER else "chk_invoice_bad"
        findings.append(_finding(age <= INVOICE_DUE_AFTER,
                                 i18n.t(key, lang, date=_date(last.isoformat(), lang), days=age)))

    # 5. No process counts twice: the measured sessions add up to exactly the
    #    highest counters of their processes.
    if records:
        highest = {}
        total = 0.0
        for record in records:
            procs = record.get("processes") if isinstance(record, dict) else None
            if record.get("estimated") or not isinstance(procs, dict) or not procs:
                continue
            total += record.get("usd") or 0
            for key, value in procs.items():
                if isinstance(value, (int, float)):
                    highest[key] = max(highest.get(key, 0.0), value)
        expected = sum(highest.values())
        ok = abs(total - expected) <= 0.05
        findings.append(_finding(ok, i18n.t("chk_proc_ok", lang, usd=money(total, "USD"))
                                 if ok else i18n.t("chk_proc_bad", lang, usd=money(total, "USD"),
                                                   expected=money(expected, "USD"))))

    # 6. The frozen backfill matches the start of the archive.
    if backfill_meta is not None and backfill_meta.get("provisional"):
        findings.append(_finding(True, i18n.t("chk_backfill_provisional", lang)))
    elif backfill_meta is not None and backfill_meta.get("until"):
        until = backfill_meta.get("until")
        ok = not archive_start or until == archive_start
        findings.append(_finding(ok, i18n.t(
            "chk_backfill_ok", lang, created=_date(backfill_meta.get("created"), lang),
            until=_date(until, lang)) if ok else i18n.t(
            "chk_backfill_bad", lang, until=_date(until, lang),
            start=_date(archive_start, lang))))

    # 7. The logs still carry cost lines. The format is undocumented; if it
    #    changes, nothing else would notice.
    if recent_logs:
        recent, with_cost = recent_logs
        if recent >= MIN_RECENT_LOGS:
            ok = with_cost > 0
            findings.append(_finding(ok, i18n.t(
                "chk_format_ok" if ok else "chk_format_bad", lang,
                recent=recent, with_cost=with_cost)))

    return findings


def read_history(path=None):
    target = Path(path) if path else history_path()
    lines = []
    try:
        with target.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if isinstance(entry, dict) and entry.get("day"):
                    lines.append(entry)
    except OSError:
        return []
    return sorted(lines, key=lambda e: e["day"])


def write_history(path, result, today, findings):
    """Keep this day's state, one line per day."""
    target = Path(path) if path else history_path()
    projects = result.get("projects") or []
    entry = {
        "day": today.isoformat(),
        "total": round(result.get("api_usd_total") or 0, 2),
        "measured": round(sum(p.get("measured_usd") or 0 for p in projects), 2),
        "estimated": round(sum(p.get("estimated_usd") or 0 for p in projects), 2),
        "sub_paid": round((result.get("subscription") or {}).get("paid") or 0, 2),
        "projects": {p["name"]: p.get("api_usd") for p in projects
                     if (p.get("api_usd") or 0) >= 1},
        "findings": [f["text"] for f in findings or [] if not f.get("ok")],
    }
    lines = [x for x in read_history(target) if x["day"] != entry["day"]]
    lines.append(entry)
    lines.sort(key=lambda x: x["day"])
    paths.write_atomic(target, "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines))


def today_local():
    return datetime.now(timezone.utc).astimezone().date()
