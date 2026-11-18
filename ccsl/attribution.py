"""From archived sessions to costs per project.

Two separate steps: first decide per calendar day which project used how
much, then spread that day's subscription fee accordingly. Only that way
does a plan change take effect exactly where it happened.

What tells neither a directory nor a path (plain text, thinking) is not
weighted at all. It spreads by itself in proportion to the recognised work
instead of falling into a leftover bucket. Without that step 54 percent
stayed unassigned on real data, with it 1.8.
"""

import collections
from datetime import datetime, timedelta, timezone

from . import daily_rates, i18n, invoices as inv

UNASSIGNED = "Unassigned"
SOURCES = ("cwd", "paths", "commands")


def known_roots(records):
    """Git roots the archive resolved while the folders still existed."""
    roots = {}
    for record in records or []:
        found = record.get("git_roots") if isinstance(record, dict) else None
        if isinstance(found, dict):
            roots.update({k: v for k, v in found.items() if isinstance(v, str)})
    return roots


def session_shares(record, ctx):
    """{project: share} for one session. The shares add up to 1.0."""
    main = collections.Counter()
    fallback = collections.Counter()
    for field in SOURCES:
        source = (record or {}).get(field) or {}
        if not isinstance(source, dict):
            continue
        for place, weight in source.items():
            if not isinstance(weight, (int, float)) or weight <= 0:
                continue
            name, rank = ctx.classify(place)
            if rank == "project" and name:
                main[name] += weight
            elif rank == "secondary" and name:
                fallback[name] += weight
    chosen = main or fallback
    total = sum(chosen.values())
    if not total:
        return {UNASSIGNED: 1.0}
    return {name: weight / total for name, weight in chosen.items()}


def day_of(start_ms):
    if not isinstance(start_ms, (int, float)) or isinstance(start_ms, bool):
        return None
    try:
        return datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).astimezone().date()
    except (OverflowError, OSError, ValueError):
        return None


def evaluate(records, ctx, invoices, start=None, end=None, backfill_days=None, rates=None):
    """The balance over the given sessions.

    backfill_days adds estimated daily values for the time before the
    archive, in the same shape as the measured ones. That spreads the fee of
    those days just as precisely, without a second way of computing. The
    amounts are kept apart so measurement and estimate stay distinguishable.
    """
    start = inv.as_date(start)
    end = inv.as_date(end)

    per_day = collections.defaultdict(lambda: collections.defaultdict(float))
    hours = collections.Counter()
    compute = collections.Counter()
    api = collections.Counter()
    recomputed = collections.Counter()
    # Each session's share per project. The status line needs it so it does
    # not count the running session twice once it is in the archive.
    per_session = collections.defaultdict(dict)

    for record in records or []:
        day = day_of((record or {}).get("start_ms"))
        if day is None or (start and day < start) or (end and day > end):
            continue
        usd = record.get("usd")
        if not isinstance(usd, (int, float)) or isinstance(usd, bool):
            continue
        duration = record.get("duration_ms") or 0
        api_ms = record.get("api_ms") or 0
        from_tokens = bool(record.get("estimated"))
        sid = record.get("session")
        for name, share in session_shares(record, ctx).items():
            value = usd * share
            per_day[day][name] += value
            api[name] += value
            if from_tokens:
                recomputed[name] += value
            hours[name] += duration * share / 3_600_000
            compute[name] += api_ms * share / 3_600_000
            if sid:
                per_session[sid][name] = round(per_session[sid].get(name, 0.0) + value, 4)

    # The estimated backfill flows into the same daily structure. Its hours
    # stay unknown: commits tell nothing about working time.
    estimated = collections.Counter()
    for day, shares in (backfill_days or {}).items():
        if (start and day < start) or (end and day > end):
            continue
        # Cap per day: the measured AVERAGE of a working day under the plan
        # of that time. Measured values are facts and stay untouched; the
        # estimate may only fill the rest.
        cap = daily_rates.cap_for(day, invoices, rates)
        if cap is not None:
            already = sum(per_day.get(day, {}).values())
            shares = daily_rates.apply_cap(shares, max(0.0, cap - already))
        for name, value in (shares or {}).items():
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                continue
            per_day[day][name] += value
            api[name] += value
            estimated[name] += value

    sub_per_project = collections.Counter()
    paid = unused = 0.0
    days = sorted(per_day)
    if days and invoices:
        current, last = days[0], days[-1]
        while current <= last:
            fee = inv.daily_fee(current, invoices)
            paid += fee
            assigned, rest = inv.spread(per_day.get(current) or {}, fee)
            for name, amount in assigned.items():
                sub_per_project[name] += amount
            unused += rest
            current += timedelta(days=1)

    api_total = sum(api.values())
    projects = []
    for name, value in api.most_common():
        est = float(estimated.get(name) or 0.0)
        projects.append({
            "name": name,
            "api_usd": round(value, 2),
            "sub_share": round(sub_per_project.get(name, 0.0), 2),
            # Wall clock since session start, idle time and nights included.
            "hours": round(hours.get(name, 0.0), 1),
            # Time the model really spent computing.
            "compute_h": round(compute.get(name, 0.0), 1),
            "share": (value / api_total) if api_total else 0.0,
            "measured_usd": round(value - est, 2),
            # Computed from tokens because the session left no cost line.
            # More precise than the backfill, but not measured by Claude Code.
            "recomputed_usd": round(recomputed.get(name, 0.0), 2),
            "estimated_usd": round(est, 2),
        })

    assigned_total = sum(sub_per_project.values())
    extras = inv.extras_total(invoices, start=days[0] if days else None,
                              end=days[-1] if days else None)
    return {
        "period": {
            "from": days[0].isoformat() if days else None,
            "to": days[-1].isoformat() if days else None,
            "active_days": len(days),
        },
        "projects": projects,
        "subscription": {
            "paid": round(paid, 2),
            "assigned": round(assigned_total, 2),
            "unused": round(unused, 2),
            # Extras are real cost but cover no span, so they stay out of the
            # day-by-day spread.
            "extra": round(extras, 2),
            "total": round(paid + extras, 2),
        },
        # Puts a dollar list price next to an invoice in the user's currency.
        # Meant as an order of magnitude, not as a currency conversion.
        "leverage": round(api_total / assigned_total, 1) if assigned_total else None,
        "hours_total": round(sum(hours.values()), 1),
        "compute_total": round(sum(compute.values()), 1),
        "sessions": dict(per_session),
        "api_usd_total": round(api_total, 2),
    }


def display_name(name, lang):
    """Internal names that the reader sees translated."""
    if name == UNASSIGNED:
        return i18n.t("unassigned", lang)
    return name
