"""What a plan yields on a working day, as a cap for the backfill estimate.

The backfill turns changed lines into dollars, using the cost per line of
the measured time, that is of today's models with large contexts. Applied to
days with very many lines that would give amounts that never occurred on one
day under the plan of that time.

So the cap is the measured AVERAGE of a working day per plan. A careful cap,
not a maximum: above-average days get cut, the estimate rather ends up low.
"""

import math
from datetime import datetime, timezone

from . import invoices as inv

# The plans behave like their names: Max 5x and Max 20x are five and twenty
# times Pro. Ultra currently shares the rate limit tier of Max 20x.
FACTORS = {
    "Ultra": 1.0,
    "Max 20x": 1.0,
    "Max 5x": 1.0 / 4,
    "Team": 1.0 / 4,
    "Pro": 1.0 / 20,
    # The free tier is tight and lacks the large models. A tenth of Pro is a
    # generous assumption.
    "Free": 1.0 / 200,
}


def measured(records, invoices):
    """Measured API value per active day, per plan.

    The obvious route, turning percent of the weekly limit into dollars,
    failed: measured values were 2.7 times above what that conversion
    allowed. The limit counts in a unit of its own. The measurement holds:
    what really accrued on a day under a plan is in Claude Code's cost line.
    """
    per_plan = {}
    for record in records or []:
        start, usd = record.get("start_ms"), record.get("usd")
        if not isinstance(start, (int, float)) or not isinstance(usd, (int, float)):
            continue
        try:
            day = datetime.fromtimestamp(start / 1000, tz=timezone.utc).astimezone().date()
        except (OverflowError, OSError, ValueError):
            continue
        plan = inv.plan_on(day, invoices)
        if not plan:
            continue
        entry = per_plan.setdefault(plan, {"usd": 0.0, "days": set()})
        entry["usd"] += usd
        entry["days"].add(day)
    return {plan: e["usd"] / len(e["days"]) for plan, e in per_plan.items() if e["days"]}


def derive(measured_rates):
    """Fill in never-measured plans through the ratio of their names.

    The reference is always the measured plan closest to the missing one:
    Pro is derived from Max 5x rather than Max 20x, because the step is
    smaller. Before, the order in the archive decided, and Pro ended up at
    23 or at 55 $ a day depending on the reference.
    """
    if not measured_rates:
        return {}
    full = dict(measured_rates)
    refs = [(FACTORS[p], v) for p, v in measured_rates.items()
            if FACTORS.get(p) and isinstance(v, (int, float)) and v > 0]
    if not refs:
        return full
    for plan, factor in FACTORS.items():
        if plan in full:
            continue
        # Distance as a ratio, not a difference: 1/20 to 1/4 is a smaller
        # step than 1/20 to 1.
        ref_factor, ref_value = min(refs, key=lambda r: (abs(math.log(r[0] / factor)), -r[0]))
        full[plan] = ref_value * factor / ref_factor
    return full


def cap_for(day, invoices, rates):
    """The cap for the estimate on this day: the measured rate of its plan."""
    plan = inv.plan_on(day, invoices)
    if not plan or not rates:
        return None
    return derive(rates).get(plan)


def apply_cap(shares, cap):
    """Shrink the day's shares proportionally to the cap."""
    if cap is None or not shares:
        return shares
    total = sum(shares.values())
    if total <= cap:
        return shares
    factor = cap / total
    return {name: value * factor for name, value in shares.items()}
