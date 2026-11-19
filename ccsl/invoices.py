"""Spread the subscription fee over projects, day by day.

The basis are the real invoices, not an assumed monthly price. Every invoice
covers the time until the next one, and its amount is fixed. That keeps
prorated amounts right when a plan changes mid-month, and a moved billing
day is no trouble.

Days without work carry their fee as unused. That is on purpose: spreading
the fee over active days only would hide exactly the question whether the
plan is worth it.

File format (invoices.json):

    {"currency": "EUR",
     "invoices": [{"date": "2026-01-24", "amount": 21.42, "plan": "Pro"},
                  {"date": "2026-02-02", "amount": 5.00, "kind": "extra"}]}

"kind": "extra" marks a one-off purchase (extra usage) instead of a
subscription invoice.
"""

import json
from datetime import date
from pathlib import Path

from . import paths

# The newest invoice has no successor, so its span is unknown; a usual
# billing month is assumed. The gap before it is no predictor, because
# exactly there sit the prorated invoices of a plan change.
OPEN_SPAN_DAYS = 30


def default_path(env=None):
    return paths.data_file("invoices.json", env)


def as_date(value):
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        y, m, d = (int(x) for x in value.strip().split("-"))
        return date(y, m, d)
    except (ValueError, TypeError):
        return None


def _entries(invoices, kind=None):
    """Valid entries sorted by date, optionally of one kind only.

    Without a kind in the entry it counts as a subscription invoice, the
    usual case.
    """
    valid = []
    for entry in invoices or []:
        if not isinstance(entry, dict):
            continue
        day = as_date(entry.get("date"))
        amount = entry.get("amount")
        if day is None or not isinstance(amount, (int, float)) or isinstance(amount, bool):
            continue
        own = entry.get("kind") or "subscription"
        if kind is not None and own != kind:
            continue
        valid.append((day, float(amount), entry.get("plan")))
    valid.sort(key=lambda e: e[0])
    return valid


def ordered(invoices):
    """Subscription invoices only, one per date. Extras cover no span.

    Two invoices on the same day (an upgrade and the monthly one) are added
    up. Otherwise the first would cover zero days and its amount would drop
    out of every daily fee.
    """
    merged = []
    for day, amount, plan in _entries(invoices, kind="subscription"):
        if merged and merged[-1][0] == day:
            merged[-1] = (day, merged[-1][1] + amount, plan or merged[-1][2])
        else:
            merged.append((day, amount, plan))
    return merged


def extras_total(invoices, start=None, end=None):
    """Sum of one-off purchases in the period. They pay for usage, not time,
    so they are not spread over days."""
    total = 0.0
    for day, amount, _ in _entries(invoices, kind="extra"):
        if start and day < start:
            continue
        if end and day > end:
            continue
        total += amount
    return total


def _covering(day, merged):
    """The invoice covering this day, with its length in days."""
    for i, (when, amount, plan) in enumerate(merged):
        if when > day:
            break
        nxt = merged[i + 1][0] if i + 1 < len(merged) else None
        length = (nxt - when).days if nxt else OPEN_SPAN_DAYS
        if nxt is not None and day >= nxt:
            continue
        return amount, max(1, length), plan
    return None, 0, None


def daily_fee(day, invoices):
    """The part of the invoice that falls on this day."""
    amount, length, _ = _covering(day, ordered(invoices))
    if amount is None or not length:
        return 0.0
    return amount / length


def plan_on(day, invoices):
    """Name of the plan in force on this day, or None."""
    return _covering(day, ordered(invoices))[2]


def spread(shares, fee):
    """Spread a daily fee. Returns (per project, unused rest)."""
    total = sum(v for v in (shares or {}).values() if isinstance(v, (int, float)))
    if total <= 0:
        return {}, fee
    return {name: fee * value / total for name, value in shares.items()}, 0.0


def load(path=None, env=None):
    """(invoices, currency). No file means no subscription share, not an error."""
    target = Path(path) if path else default_path(env)
    try:
        data = json.loads(target.read_text(encoding="utf-8-sig"))
    except Exception:
        return [], None
    if isinstance(data, list):
        return [e for e in data if isinstance(e, dict) and e.get("date")], None
    if not isinstance(data, dict):
        return [], None
    currency = data.get("currency") if isinstance(data.get("currency"), str) else None
    raw = data.get("invoices")
    if not isinstance(raw, list):
        return [], currency
    return [e for e in raw if isinstance(e, dict) and e.get("date")], currency


def save(invoices, currency, path=None, env=None):
    target = Path(path) if path else default_path(env)
    content = {"currency": currency, "invoices": sorted(
        invoices, key=lambda e: str(e.get("date")))}
    paths.write_atomic(target, json.dumps(content, indent=2, ensure_ascii=False) + "\n")
