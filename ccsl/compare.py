"""How long the same work would have taken on another plan.

Based on the measured daily rates: what really accrued on a working day
under a plan. Plans never used follow the ratio of their names.

Explicitly a rough calculation. It assumes the same work could be stretched
over more weeks, which is wrong with a deadline, and it can only roughly
reflect the limits of the free tier.
"""

import collections

from . import daily_rates

# Order of the rows. Ultra only appears when it was actually measured; by its
# limits it is not distinguishable from Max 20x.
PLANS = ("Ultra", "Max 20x", "Max 5x", "Pro", "Free")
ONLY_IF_MEASURED = ("Ultra",)

# Plans without the large models. The same work there would not only take
# longer, parts of it would not be possible at all.
WITHOUT_LARGE_MODELS = ("Free",)

DAYS_PER_WEEK = 7.0
WEEKS_PER_MONTH = 4.345


def weeks_per_plan(usd_total, rates):
    """Per plan {weeks, months, per_week, measured, without_large_models}."""
    if not usd_total or usd_total <= 0 or not rates:
        return {}
    full = daily_rates.derive(rates)
    if not full:
        return {}
    result = collections.OrderedDict()
    for plan in PLANS:
        rate = full.get(plan)
        measured = plan in rates
        if not rate or (plan in ONLY_IF_MEASURED and not measured):
            continue
        per_week = rate * DAYS_PER_WEEK
        if per_week <= 0:
            continue
        weeks = usd_total / per_week
        result[plan] = {
            "weeks": round(weeks, 1),
            "months": round(weeks / WEEKS_PER_MONTH, 1),
            "per_week": round(per_week, 2),
            "measured": measured,
            "without_large_models": plan in WITHOUT_LARGE_MODELS,
        }
    return result
