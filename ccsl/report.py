"""Tables for the terminal.

Same split as in the status line: this module knows nothing about where the
data comes from, it only shapes it. Colours and width come from ccsl.draw,
so report and status line share one handwriting.
"""

from . import attribution, compare, draw, i18n

# From this share on a row rests mostly on estimates and gets marked. Whoever
# reads the number should not have to guess.
ESTIMATE_MARK = 0.5

# Below this share a project gets no row of its own; automatic detection
# finds every storage folder otherwise. Purely a decision of the DISPLAY: the
# summary file keeps every project.
SMALL_SHARE = 0.005
SUM_FIELDS = ("api_usd", "sub_share", "hours", "compute_h", "share",
              "measured_usd", "estimated_usd", "recomputed_usd")

i18n.add({
    "rep_period": ("{start}  to  {end}   ({days} active {unit})",
                   "{start}  bis  {end}   ({days} {unit})"),
    "rep_day": ("day", "aktiver Tag"),
    "rep_days": ("days", "aktive Tage"),
    "rep_nothing": ("Nothing to evaluate in this period.",
                    "In diesem Zeitraum gibt es nichts auszuwerten."),
    "rep_project": ("Project", "Projekt"),
    "rep_api": ("API value", "API-Wert"),
    "rep_share": ("Share", "Anteil"),
    "rep_sub": ("Subscription", "Abo-Anteil"),
    "rep_compute": ("Compute", "Rechenzeit"),
    "rep_total": ("Total", "Gesamt"),
    "rep_all": ("All projects", "Alle Projekte"),
    "rep_small": ("Smaller projects", "Kleinere Vorhaben"),
    "rep_paid": ("Subscription in this period {paid}, of which {unused} unused "
                 "(days without work).",
                 "Abo im Zeitraum {paid}, davon {unused} ungenutzt (Tage ohne Arbeit)."),
    "rep_extra": ("Plus {extra} in extra purchases, {total} altogether.",
                  "Dazu {extra} an Zusatzkäufen, zusammen {total}."),
    "rep_other": ("Plus from {source}: {usd} for {project}{span}, computed from the "
                  "tokens counted there.",
                  "Dazu von {source}: {usd} für {project}{span}, aus dort gezählten "
                  "Tokens nachgerechnet."),
    "rep_other_note": ("Entries from other machines are not in the table and carry no "
                       "subscription share.",
                       "Nachträge stehen nicht in der Tabelle und tragen keinen Abo-Anteil."),
    "rep_other_machine": ("another machine", "anderem Rechner"),
    "rep_leverage": ("The API value is about {x} times the subscription fee that falls on "
                     "this work. An order of magnitude, not a conversion.",
                     "Der API-Wert ist rund das {x}-fache der Abogebühr, die auf diese "
                     "Arbeit entfällt. Eine Größenordnung, keine Umrechnung."),
    "rep_estimated_share": ("{pct} of the API value is estimated.",
                            "{pct} des API-Werts sind hochgerechnet."),
    "rep_tilde": ("~ marks rows that are mostly estimated. More: --by-source",
                  "~ steht für Zeilen, die überwiegend geschätzt sind. Mehr: --by-source"),
    "rep_compute_note": ("Compute: how long the model actually worked.",
                         "Rechenzeit: wie lange das Modell tatsächlich gerechnet hat."),
    "rep_no_invoices": ("No invoices yet, so no subscription share. Add them with "
                        "/calm-statusline:cost-setup or in {path}.",
                        "Noch keine Rechnungen, deshalb kein Abo-Anteil. Eintragen mit "
                        "/calm-statusline:cost-setup oder in {path}."),
    "src_title": ("Where the numbers come from", "Woher die Zahlen kommen"),
    "src_measured": ("measured", "gemessen"),
    "src_estimated": ("estimated", "geschätzt"),
    "src_none": ("Nothing evaluated yet.", "Noch nichts ausgewertet."),
    "src_recomputed": ("Of that, {usd} computed from tokens: these sessions were aborted "
                       "and left no cost line.",
                       "Davon {usd} aus Tokens nachgerechnet: diese Sitzungen wurden "
                       "abgebrochen und haben keine Kostenzeile hinterlassen."),
    "src_text": (
        "Measured means: from Claude Code's own cost lines, every process counted once.\n"
        "Estimated means: {measure} in the git history before the archive starts (your\n"
        "own commits only), times the cost per {unit} found in the measured time. One\n"
        "rate per project, the average for projects without a measurement. The\n"
        "estimate is frozen{since}; it is only recomputed with claude-costs --refreeze.\n"
        "It stays rough: one {unit} is not always the same amount of work, and before\n"
        "Claude Code part of the work was done with other tools.",
        "Gemessen heißt: aus Claude Codes eigenen Kostenzeilen, je Prozess einmal gezählt.\n"
        "Geschätzt heißt: {measure} der Git-Historie vor Beginn des Archivs (nur eigene\n"
        "Commits), mal den Kosten je {unit}, die sich aus der gemessenen Zeit ergeben. Je\n"
        "Projekt ein eigener Satz, für Projekte ohne Messung der Durchschnitt. Die\n"
        "Schätzung ist festgeschrieben{since}; neu berechnet wird sie nur mit\n"
        "claude-costs --refreeze. Grob bleibt sie trotzdem: eine {unit} ist nicht immer\n"
        "gleich viel Arbeit, und vor Claude Code wurde teils mit anderen Werkzeugen\n"
        "gearbeitet."),
    "src_since": (" since {date}", " seit dem {date}"),
    "measure_lines": ("changed lines", "geänderte Zeilen"),
    "measure_commits": ("commits", "Commits"),
    "unit_lines": ("line", "Zeile"),
    "unit_commits": ("commit", "Commit"),
    "chk_title": ("Self-check", "Selbstprüfung"),
    "hist_none": ("No history yet. It starts with the first full run of claude-costs.",
                  "Noch kein Verlauf. Er entsteht mit dem ersten vollständigen Lauf von "
                  "claude-costs."),
    "hist_day": ("Day", "Tag"),
    "hist_change": ("Change", "Änderung"),
    "hist_check": ("Check", "Prüfung"),
    "hist_ok": ("fine", "in Ordnung"),
    "hist_findings": ("{n} finding(s)", "{n} Befund(e)"),
    "cmp_title": ("How long the same work would have taken on other plans",
                  "Wie lange dieselbe Arbeit mit anderen Stufen gedauert hätte"),
    "cmp_none": ("No project found.", "Kein Projekt gefunden."),
    "cmp_no_rates": ("no measured daily rates yet (needs invoices)",
                     "keine gemessenen Tagessätze vorhanden (braucht Rechnungen)"),
    "cmp_row": ("{weeks} weeks  {months} months  {per_week} per week",
                "{weeks} Wochen  {months} Monate  {per_week} je Woche"),
    "cmp_measured": ("measured", "gemessen"),
    "cmp_derived": ("derived", "abgeleitet"),
    "cmp_no_large": (", without Opus and Fable", ", ohne Opus und Fable"),
    "cmp_note": (
        "Based on the measured daily rates: what accrued on a working day under a plan.\n"
        "Plans never used follow the ratio of their names, relative to the nearest\n"
        "measured plan. A rough calculation: it assumes the same work could be\n"
        "stretched, which is not true with a deadline.",
        "Grundlage sind die gemessenen Tagessätze: was unter einer Stufe an einem\n"
        "Arbeitstag tatsächlich anfiel. Nie genutzte Stufen folgen dem Verhältnis ihrer\n"
        "Namen, bezogen auf die nächste gemessene Stufe. Eine Überschlagsrechnung: sie\n"
        "unterstellt, dass sich dieselbe Arbeit strecken ließe, was bei einem Termin\n"
        "nicht stimmt."),
})


def _q(text, color):
    return draw.paint(text, "quiet", color)


def _date(iso, lang):
    parts = str(iso or "").split("-")
    if lang == "de" and len(parts) == 3:
        return "{}.{}.{}".format(parts[2][:2], parts[1], parts[0])
    return str(iso or "?")


def _money(v, cur, lang, decimals=2):
    return i18n.money(v, cur or "USD", lang, decimals)


def _round_money(v, lang):
    return i18n.money(v, "USD", lang, 0 if abs(v or 0) >= 1000 else 2)


def merge_small(projects, total, lang):
    """Fold tiny items into one row. The total stays the same."""
    if not total:
        return list(projects)
    small = [p for p in projects
             if (p.get("api_usd") or 0) / total < SMALL_SHARE
             and p.get("name") != attribution.UNASSIGNED]
    if len(small) < 2:
        return list(projects)
    merged = {"name": i18n.t("rep_small", lang)}
    for field in SUM_FIELDS:
        merged[field] = round(sum(p.get(field) or 0 for p in small), 6)
    rest = [p for p in projects if p not in small]
    rest.append(merged)
    return sorted(rest, key=lambda p: -(p.get("api_usd") or 0))


def _compute(p, lang):
    """Purely estimated projects have an unknown compute time, not zero."""
    if not p.get("compute_h") and not p.get("measured_usd"):
        return "–"
    return i18n.number(p.get("compute_h") or 0, 1, lang) + " h"


def _header(period, lang):
    start, end = (period.get("requested") or [period.get("from"), period.get("to")])[:2]
    days = period.get("active_days") or 0
    return i18n.t("rep_period", lang, start=start or "?", end=end or "?", days=days,
                  unit=i18n.t("rep_day" if days == 1 else "rep_days", lang))


def table(result, width=100, color=False, currency=None, lang="en"):
    """The main table: API value, subscription share and compute per project."""
    projects = merge_small(result.get("projects") or [], result.get("api_usd_total") or 0, lang)
    period = result.get("period") or {}
    with_sub = bool(currency) and bool((result.get("subscription") or {}).get("paid"))
    lines = [_q(_header(period, lang), color), ""]

    if not projects:
        lines.append(_q(i18n.t("rep_nothing", lang), color))
        return "\n".join(lines)

    names = [attribution.display_name(p["name"], lang) for p in projects]
    name_w = min(max([len(n) for n in names] + [13]), max(13, width - 47))
    cols = [("{:>14}", "rep_api"), ("{:>9}", "rep_share")]
    if with_sub:
        cols.append(("{:>14}", "rep_sub"))
    cols.append(("{:>12}", "rep_compute"))
    pattern = "{:<" + str(name_w) + "}" + "".join(c for c, _ in cols)
    rule = "─" * min(width, name_w + 14 + 9 + (14 if with_sub else 0) + 12)

    lines.append(_q(pattern.format(i18n.t("rep_project", lang),
                                   *[i18n.t(k, lang) for _, k in cols]), color))
    lines.append(_q(rule, color))
    for p, name in zip(projects, names):
        total = p.get("api_usd") or 0
        if total and (p.get("estimated_usd") or 0) / total >= ESTIMATE_MARK:
            name = "~ " + name
        if len(name) > name_w:
            name = name[:name_w - 1] + "…"
        row = [name, _money(p.get("api_usd"), "USD", lang),
               i18n.percent((p.get("share") or 0) * 100, 1, lang)]
        if with_sub:
            row.append(_money(p.get("sub_share"), currency, lang))
        row.append(_compute(p, lang))
        lines.append(pattern.format(*row))
    lines.append(_q(rule, color))
    row = [i18n.t("rep_all" if result.get("only_project") else "rep_total", lang),
           _money(result.get("api_usd_total"), "USD", lang), i18n.percent(100, 1, lang)]
    if with_sub:
        row.append(_money((result.get("subscription") or {}).get("assigned"), currency, lang))
    row.append(i18n.number(result.get("compute_total") or 0, 1, lang) + " h")
    lines.append(pattern.format(*row))

    sub = result.get("subscription") or {}
    if with_sub:
        lines.append("")
        lines.append(_q(i18n.t("rep_paid", lang, paid=_money(sub.get("paid"), currency, lang),
                               unused=_money(sub.get("unused"), currency, lang)), color))
        if sub.get("extra"):
            lines.append(_q(i18n.t("rep_extra", lang,
                                   extra=_money(sub.get("extra"), currency, lang),
                                   total=_money(sub.get("total"), currency, lang)), color))
    others = result.get("other_machines") or []
    if others:
        lines.append("")
        for entry in others:
            span = " – ".join(_date(d, lang) for d in (entry.get("from"), entry.get("to")) if d)
            lines.append(i18n.t("rep_other", lang,
                                source=entry.get("source") or i18n.t("rep_other_machine", lang),
                                usd=_money(entry["usd"], "USD", lang), project=entry["project"],
                                span=" (" + span + ")" if span else ""))
        lines.append(_q(i18n.t("rep_other_note", lang), color))
    if result.get("leverage") and with_sub:
        lines.append(_q(i18n.t("rep_leverage", lang,
                               x=i18n.number(result["leverage"], 0, lang)), color))
    all_projects = result.get("projects") or []
    estimated = sum(p.get("estimated_usd") or 0 for p in all_projects)
    api = sum(p.get("api_usd") or 0 for p in all_projects)
    if api and estimated:
        lines.append(_q(i18n.t("rep_estimated_share", lang,
                               pct=i18n.percent(estimated / api * 100, 1, lang)), color))
        lines.append(_q(i18n.t("rep_tilde", lang), color))
    lines.append(_q(i18n.t("rep_compute_note", lang), color))
    return "\n".join(lines)


def _measure(result, lang):
    m = (result.get("backfill") or {}).get("measure") or "lines"
    key = "commits" if m == "commits" else "lines"
    return i18n.t("measure_" + key, lang), i18n.t("unit_" + key, lang)


def by_source(result, color=False, lang="en"):
    """Per project: what is measured and what is estimated."""
    projects = result.get("projects") or []
    if not projects:
        return _q(i18n.t("src_none", lang), color)
    names = [attribution.display_name(p["name"], lang) for p in projects]
    name_w = max([len(n) for n in names] + [12])
    pattern = "{:<" + str(name_w) + "}{:>15}{:>15}{:>8}"
    lines = [_q(i18n.t("src_title", lang), color), "",
             _q(pattern.format(i18n.t("rep_project", lang), i18n.t("src_measured", lang),
                               i18n.t("src_estimated", lang), "~"), color),
             _q("─" * (name_w + 38), color)]
    for p, name in zip(projects, names):
        total = p.get("api_usd") or 0
        est = p.get("estimated_usd") or 0
        lines.append(pattern.format(name, _money(p.get("measured_usd"), "USD", lang),
                                    _money(est, "USD", lang),
                                    "{:.0f}%".format(est / total * 100 if total else 0)))
    lines.append("")
    recomputed = sum(p.get("recomputed_usd") or 0 for p in projects)
    if recomputed:
        lines.append(_q(i18n.t("src_recomputed", lang,
                               usd=_money(recomputed, "USD", lang)), color))
        lines.append("")
    measure, unit = _measure(result, lang)
    meta = result.get("backfill") or {}
    created = meta.get("created")
    since = i18n.t("src_since", lang, date=_date(str(created)[:10], lang)) \
        if created and not meta.get("provisional") else ""
    for line in i18n.t("src_text", lang, measure=measure, unit=unit, since=since).split("\n"):
        lines.append(_q(line, color))
    return "\n".join(lines)


FORMULA = {
    "en": """How the numbers are computed

API value, measured
  Claude Code writes a cost line whenever a process ends: the list price the
  work would have cost through the API. Per process its highest counter
  counts, a session is the sum of its processes. When work continues under a
  new session id, only the increase counts there. Sessions without a cost
  line (aborted) are computed from their tokens, at the price per model
  derived from the measured ones. A session spanning several projects is
  split in proportion to what was produced in each.
{backfill}
Subscription share
  Every invoice covers the time until the next one; its amount is spread
  evenly over those days. The newest one counts for 30 days and carries on
  until the next is entered. A day's fee goes to the projects worked on that
  day, in proportion to their API value. After a plan change with a credit,
  the old span carries the full amount and the new one the reduced amount:
  the total is right, the split across days only roughly.

  The API value is in dollars because it is a list price. The subscription
  share is in the currency of your invoices.

Extra purchases
  Bought usage pays for no span of time, it gets used up at some point. It is
  therefore not spread over days but shown as a separate sum.

Unused
  On days without work the fee keeps running but belongs to no project.
  Before the archive, work means a commit.""",
    "de": """Wie gerechnet wird

API-Wert, gemessen
  Claude Code schreibt beim Beenden jedes Prozesses eine Kostenzeile mit dem
  Listenpreis, den die Arbeit über die Schnittstelle gekostet hätte. Je
  Prozess zählt sein höchster Stand, eine Sitzung ist die Summe ihrer
  Prozesse. Läuft die Arbeit unter neuer Kennung weiter, zählt dort nur der
  Zuwachs. Sitzungen ohne Kostenzeile (abgebrochen) werden aus ihren Tokens
  nachgerechnet, mit dem Preis je Modell aus den gemessenen. Eine Sitzung an
  mehreren Projekten wird in dem Verhältnis geteilt, in dem dort jeweils
  etwas entstanden ist.
{backfill}
Abo-Anteil
  Jede Rechnung deckt den Zeitraum bis zur nächsten ab, ihr Betrag wird
  gleichmäßig auf diese Tage verteilt. Die jüngste gilt 30 Tage; bis die
  nächste eingetragen ist, wird mit ihrem Betrag weitergerechnet. Die
  Tagesgebühr geht an die Projekte, die an dem Tag gearbeitet haben, im
  Verhältnis ihres API-Werts. Bei einem Stufenwechsel mit Gutschrift trägt
  der alte Zeitraum den vollen Betrag und der neue den verminderten: die
  Summe stimmt, die Verteilung auf die Tage nur ungefähr.

  Der API-Wert steht in Dollar, weil er ein Listenpreis ist. Der Abo-Anteil
  steht in der Währung deiner Rechnungen.

Zusatzkäufe
  Ein gekauftes Kontingent bezahlt kein Zeitfenster, sondern wird irgendwann
  verbraucht. Es wird deshalb nicht auf Tage verteilt, sondern als eigene
  Summe ausgewiesen.

Ungenutzt
  An Tagen ohne Arbeit läuft die Gebühr weiter, lässt sich aber keinem
  Projekt zuordnen. Vor dem Archiv heißt Arbeit: ein Commit.""",
}

BACKFILL_TEXT = {
    "en": ("\nAPI value, estimated\n"
           "  Before {until} there are no cost lines. The measure is {measure} in the\n"
           "  git history (your own commits; lock files, build folders and single files\n"
           "  with 20,000 lines or more per commit do not count), times the cost per {unit}:\n"),
    "de": ("\nAPI-Wert, hochgerechnet\n"
           "  Vor dem {until} gibt es keine Kostenzeilen. Maß sind {measure} der\n"
           "  Git-Historie (nur eigene Commits; Sperrdateien, Build-Ordner und\n"
           "  Einzeldateien ab 20.000 Zeilen je Commit zählen nicht), mal den Kosten je {unit}:\n"),
}


def formula(result, invoices=None, color=False, currency=None, lang="en"):
    """Explain in plain words how it was computed, with the rates used."""
    lang = lang if lang in FORMULA else "en"
    meta = result.get("backfill") or {}
    block = ""
    if meta.get("until"):
        measure, unit = _measure(result, lang)
        block = BACKFILL_TEXT[lang].format(until=_date(meta["until"], lang),
                                           measure=measure, unit=unit)
        rates = meta.get("rates_per_unit") or {}
        avg = "average" if lang == "en" else "Durchschnitt"
        for name, value in sorted(rates.items(), key=lambda kv: kv[0] == "*"):
            block += "    {:<28}{}\n".format(avg if name == "*" else name,
                                             i18n.money(value, "USD", lang, 4))
        if meta.get("since"):
            block += ("  It starts with the first use of Claude Code on {}.\n" if lang == "en"
                      else "  Beginn ist der erste Einsatz von Claude Code am {}.\n").format(
                _date(meta["since"], lang))
        caps = meta.get("daily_caps") or {}
        if caps:
            block += ("  Capped per day at the measured average working day of the plan\n"
                      "  in force then: " if lang == "en" else
                      "  Je Tag gedeckelt mit dem gemessenen Durchschnitt eines Arbeitstags\n"
                      "  der damals gültigen Stufe: ")
            block += ", ".join("{} {}".format(n, _round_money(v, lang))
                               for n, v in caps.items()) + ".\n"
        if meta.get("uncapped_usd"):
            est = sum(p.get("estimated_usd") or 0 for p in result.get("projects") or [])
            block += ("  Without the cap it would be {} instead of {}.\n" if lang == "en" else
                      "  Ohne Deckel wären es {} statt {}.\n").format(
                _round_money(meta["uncapped_usd"], lang), _round_money(est, lang))
        block += ("  Frozen since {}: new measurements no longer change the past.\n"
                  "  Recompute with claude-costs --refreeze\n" if lang == "en" else
                  "  Festgeschrieben seit dem {}: neue Messungen ändern die Vergangenheit\n"
                  "  nicht mehr. Neu berechnen: claude-costs --refreeze\n").format(
            _date(str(meta.get("created") or "?")[:10], lang))
    text = FORMULA[lang].format(backfill=block)
    lines = text.split("\n")
    if invoices:
        lines += ["", "Invoices used" if lang == "en" else "Zugrunde liegende Rechnungen"]
        for e in sorted(invoices, key=lambda x: str(x.get("date"))):
            lines.append("  {}  {}  {}".format(
                e.get("date"), _money(e.get("amount"), currency, lang).rjust(12),
                e.get("plan") or ("extra purchase" if lang == "en" else "Zusatzkauf")))
    sub = result.get("subscription") or {}
    if sub.get("paid") and currency:
        lines += ["", i18n.t("chk_sub", lang,
                             assigned=_money(sub.get("assigned"), currency, lang),
                             unused=_money(sub.get("unused"), currency, lang),
                             paid=_money(sub.get("paid"), currency, lang))]
    return "\n".join(_q(x, color) if x.startswith("  ") else x for x in lines)


def checks(findings, color=False, lang="en"):
    lines = [_q(i18n.t("chk_title", lang), color), ""]
    for f in findings or []:
        if f.get("ok"):
            lines.append("✓ " + f.get("text", ""))
        else:
            lines.append(draw.paint("✗ " + f.get("text", ""), "warn", color))
    return "\n".join(lines)


def history(entries, color=False, lang="en"):
    """The totals day by day, with the change against the day before."""
    if not entries:
        return _q(i18n.t("hist_none", lang), color)
    pattern = "{:<12}{:>12}{:>11}{:>12}{:>12}   {}"
    lines = [_q(pattern.format(i18n.t("hist_day", lang), i18n.t("rep_total", lang),
                               i18n.t("hist_change", lang), i18n.t("src_measured", lang),
                               i18n.t("src_estimated", lang), i18n.t("hist_check", lang)),
                color), _q("─" * 72, color)]
    before = None
    for e in entries:
        total = e.get("total") or 0
        change = "" if before is None else (
            ("+" if total - before >= 0 else "−") + _round_money(abs(total - before), lang))
        findings = e.get("findings") or []
        lines.append(pattern.format(
            e.get("day", "?"), _round_money(total, lang), change,
            _round_money(e.get("measured") or 0, lang),
            _round_money(e.get("estimated") or 0, lang),
            i18n.t("hist_ok", lang) if not findings else draw.paint(
                i18n.t("hist_findings", lang, n=len(findings)), "warn", color)))
        before = total
    return "\n".join(lines)


def comparison(result, project=None, color=False, lang="en"):
    """How long the same work would have taken on another plan."""
    projects = result.get("projects") or []
    if project:
        chosen = [p for p in projects if project.lower() in p["name"].lower()]
    else:
        chosen = [p for p in projects if p["name"] != attribution.UNASSIGNED][:3]
    if not chosen:
        return _q(i18n.t("cmp_none", lang), color)
    rates = result.get("daily_rates") or {}
    lines = [_q(i18n.t("cmp_title", lang), color), ""]
    for p in chosen:
        lines.append("{}  {}".format(attribution.display_name(p["name"], lang),
                                     _money(p.get("api_usd"), "USD", lang)))
        rows = compare.weeks_per_plan(p.get("api_usd"), rates)
        if not rows:
            lines.append(_q("  " + i18n.t("cmp_no_rates", lang), color))
            lines.append("")
            continue
        for plan, w in rows.items():
            note = i18n.t("cmp_measured" if w["measured"] else "cmp_derived", lang)
            if w["without_large_models"]:
                note += i18n.t("cmp_no_large", lang)
            lines.append("  {:<9}{}   {}".format(plan, i18n.t(
                "cmp_row", lang, weeks=i18n.number(w["weeks"], 1, lang).rjust(6),
                months=i18n.number(w["months"], 1, lang).rjust(5),
                per_week=_money(w["per_week"], "USD", lang).rjust(11)), _q(note, color)))
        lines.append("")
    for line in i18n.t("cmp_note", lang).split("\n"):
        lines.append(_q(line, color))
    return "\n".join(lines)
