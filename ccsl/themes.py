"""The four layouts.

The core idea is a ladder of variants: instead of cutting a line that is too
long, the first variant that fits the window wins. Going narrower, side
details go first, then labels get shorter, then the gauges. Going wider,
more information appears instead of empty space.
"""

import re
from datetime import datetime, timezone

from . import draw, i18n

# "Max 20x" reads as "Max 20 times". The x is only replaced after a digit,
# otherwise upper() would turn MAX into MA-times.
TIMES = re.compile(r"(?<=\d)[xX]")

PARENS = re.compile(r"\s*\([^)]*\)")

DOTS = {"ok": "○", "warn": "◐", "crit": "●"}

# Header from detailed to terse. The plan is in every step and never drops
# out: it is short, never changes, and is the line's signature.
HEADER_STEPS = (
    ("plan", "model", "project", "directory", "cost"),
    ("plan", "model", "project", "cost"),
    ("plan", "model", "directory", "cost_alone"),
    ("plan", "model", "cost_alone"),
    ("plan", "model"),
    ("plan", "model_short", "cost_alone"),
    ("plan", "model_short"),
    ("plan",),
)

# In the one-line layout every part competes for the same room, so the order
# of sacrifice is spelled out here instead of falling out of nested loops:
# first the side details, then the bracket suffix of the model name, and only
# then do the gauges get shorter.
#
# Per step: (front, back, how the readings look). The reading direction is
# fixed: who I am, what I use, what it costs.
LAYOUT_STEPS = (
    (("plan", "model"), ("project", "directory", "cost"), ("long", 14, True)),
    (("plan", "model"), ("project", "cost"), ("long", 14, True)),
    (("plan", "model"), ("project", "cost"), ("long", 10, True)),
    (("plan", "model"), ("cost_alone",), ("long", 10, True)),
    (("plan", "model"), ("cost_alone",), ("long", 10, False)),
    (("plan", "model"), (), ("long", 10, False)),
    (("plan", "model"), (), ("long", 7, False)),
    (("plan", "model_short"), (), ("long", 7, False)),
    (("plan", "model_short"), (), ("short", 7, False)),
    (("plan", "model_short"), (), ("short", 5, False)),
    (("plan",), (), ("short", 5, False)),
    (("plan",), (), ("short", 0, False)),
)

# Readings row: (labels, gauge width, show reset time)
READING_STEPS = (
    ("long", 14, True),
    ("long", 10, True),
    ("long", 10, False),
    ("long", 7, False),
    ("short", 7, False),
    ("short", 5, False),
    ("short", 0, False),
)


def _lang(cfg):
    return cfg.get("_lang", "en")


def _money(value, cfg, plus=False):
    """Money in the line. From a thousand on the cents go: in five-digit sums
    they are noise and cost room the line does not have.

    plus marks the running session's cost when it stands next to the project
    value it is already part of; without the sign the two numbers would read
    as competing totals instead of part and whole.
    """
    amount = value or 0
    decimals = 0 if abs(amount) >= 1000 else 2
    return i18n.money(amount, "USD", _lang(cfg), decimals, plus=plus)


def _percent(value):
    return "{:.0f}%".format(value)


def _short(gauge, lang):
    if gauge.key == "week":
        return i18n.t("week_short", lang)
    if gauge.key == "context":
        return i18n.t("context_short", lang)
    if gauge.key == "five_hour":
        return gauge.label
    return gauge.label[:1]


def _readings(status, cfg):
    pairs = (("week", status.week), ("model_week", status.scoped),
             ("five_hour", status.five_hour), ("context", status.context))
    show = cfg.get("show", {})
    return [g for key, g in pairs if g is not None and show.get(key, True)]


def _level(gauge, cfg):
    limits = cfg.get("thresholds", {})
    return draw.level(gauge.percent, limits.get("warn", 50), limits.get("critical", 80))


def _plan_text(status, cfg, color, upper=False):
    """The plan as the session's signature.

    Higher plans get a wider colour span, not more loudness. Colour comes
    last: upper() on an already coloured text would break the escape codes.
    """
    if not status.plan:
        return ""
    text = TIMES.sub("×", status.plan.upper() if upper else status.plan)
    if not color:
        return text
    family = cfg.get("plan_style", "violet")
    if family == "plain":
        return draw.paint(text, "accent", True)
    ramp = draw.for_background(draw.plan_ramp(family, status.plan_tier),
                               draw.FAMILIES.get(family, draw.FAMILIES["violet"]),
                               cfg.get("_light"))
    return draw.gradient(text, ramp, True)


def _model_text(status, cfg, color, short=False):
    """Model and effort as one unit, in the model's colour.

    They belong together because together they decide how the session works.
    The model picks the colour family, the effort picks the span within it.
    """
    if not status.model:
        return ""
    name = PARENS.sub("", status.model) if short else status.model
    parts = [name]
    if status.effort and cfg.get("show", {}).get("effort", True):
        parts.append(draw.effort_name(status.effort, cfg.get("xhigh_as_ultracode", False)))
    text = " ".join(parts)
    if not color:
        return text
    if cfg.get("plan_style") == "plain":
        return draw.paint(text, "accent", True)
    ramp = draw.for_background(draw.model_ramp(status.model, status.effort),
                               draw.model_family(status.model), cfg.get("_light"))
    painted = draw.gradient(text, ramp, True)
    return draw.paint(painted, "strong", True) if draw.effort_bold(status.effort) else painted


def _extras(status, cfg, color):
    """The side details, already coloured.

    Colour does not disturb the width maths, visible_len skips it.
    """
    show = cfg.get("show", {})
    parts = {}
    if status.plan and show.get("plan"):
        parts["plan"] = _plan_text(status, cfg, color, upper=True)
    if status.model and show.get("model"):
        parts["model"] = _model_text(status, cfg, color)
        parts["model_short"] = _model_text(status, cfg, color, short=True)
    if status.branch and show.get("git_branch"):
        parts["branch"] = draw.paint(status.branch, "quiet", color)
    if status.directory and show.get("directory"):
        place = status.directory
        if status.branch and show.get("git_branch"):
            place += "  " + status.branch
        parts["directory"] = draw.paint(place, "quiet", color)
    if status.project and show.get("project"):
        text = status.project
        if status.project_usd:
            text += " " + _money(status.project_usd, cfg)
        parts["project"] = draw.paint(text, "quiet", color)
    if status.cost_usd is not None and show.get("cost"):
        # Two versions: "cost" stands next to the project value, "cost_alone"
        # where a step drops the project. A plus without the whole it belongs
        # to would be a sum without a total.
        parts["cost_alone"] = draw.paint(_money(status.cost_usd, cfg), "quiet", color)
        if "project" not in parts or status.project_usd is None:
            parts["cost"] = parts["cost_alone"]
        elif status.project_usd - status.cost_usd >= 0.005:
            parts["cost"] = draw.paint(_money(status.cost_usd, cfg, plus=True), "quiet", color)
        # Otherwise the project consists of this session alone and both
        # numbers would be equal. The same amount twice reads as a bug.
    return parts


def _header(extras, width):
    for step in HEADER_STEPS:
        parts = [extras[k] for k in step if k in extras]
        if not parts:
            continue
        candidate = "  ·  ".join(parts)
        if draw.visible_len(candidate) <= width:
            return candidate
    rest = [extras[k] for k in ("plan", "model") if k in extras]
    return draw.truncate("  ·  ".join(rest), width) if rest else ""


def _now():
    return datetime.now(timezone.utc).astimezone()


def _reset(status, cfg, color):
    source = status.week or status.scoped
    if source is None or source.resets_at is None:
        return ""
    text = draw.format_reset(source.resets_at, _now(), _lang(cfg))
    return draw.paint("↻ " + text, "quiet", color) if text else ""


def _readings_row(readings, status, cfg, color, labels, gauge_width, with_reset,
                  separator="   "):
    style = cfg.get("gauge_style", "line")
    track = bool(cfg.get("gauge_track"))
    lang = _lang(cfg)
    pieces = []
    for g in readings:
        level = _level(g, cfg)
        name = g.label if labels == "long" else _short(g, lang)
        parts = [draw.paint(name, "quiet", color)]
        if gauge_width:
            picture = draw.gauge(g.percent, gauge_width, style, track)
            if picture:
                parts.append(draw.paint(picture, level, color))
        parts.append(draw.paint(_percent(g.percent), level, color))
        pieces.append(" ".join(parts))

    row = separator.join(pieces)
    if with_reset:
        when = _reset(status, cfg, color)
        if when:
            row += "      " + when
    return row


def calm_two_line(status, cfg, width, color):
    readings = _readings(status, cfg)
    line1 = _header(_extras(status, cfg, color), width)

    line2 = ""
    for labels, gauge_width, with_reset in READING_STEPS:
        candidate = _readings_row(readings, status, cfg, color, labels, gauge_width, with_reset)
        if draw.visible_len(candidate) <= width:
            line2 = candidate
            break
    else:
        line2 = draw.truncate(
            _readings_row(readings, status, cfg, color, "short", 0, False, " "), width)

    return "\n".join(line for line in (line1, line2) if line)


def calm_one_line(status, cfg, width, color):
    readings = _readings(status, cfg)
    extras = _extras(status, cfg, color)

    for front, back, (labels, gauge_width, with_reset) in LAYOUT_STEPS:
        # What belongs together sits close, groups are separated by space. A
        # separator between everything would give every part the same weight.
        head = "  ·  ".join(extras[k] for k in front if k in extras)
        tail = "   ".join(extras[k] for k in back if k in extras)
        numbers = _readings_row(readings, status, cfg, color, labels, gauge_width, with_reset)
        candidate = "     ".join(x for x in (head, numbers, tail) if x)
        if draw.visible_len(candidate) <= width:
            return candidate

    # Last resort: the plan always stays, the readings move closer together
    # instead of disappearing.
    terse = _readings_row(readings, status, cfg, color, "short", 0, False, " ")
    return draw.truncate("  ".join(x for x in (extras.get("plan", ""), terse) if x), width)


def expressive(status, cfg, width, color):
    readings = _readings(status, cfg)
    extras = _extras(status, cfg, color)
    now = _now()
    style = cfg.get("gauge_style", "line")

    parts = []
    if "plan" in extras:
        parts.append(_plan_text(status, cfg, color, upper=True))
    # The effort level is already part of the model text.
    for key in ("model", "directory", "cost_alone"):
        if key in extras:
            parts.append(extras[key])
    lines = [draw.truncate("  " + "   ".join(parts), width)] if parts else []

    if readings:
        column = max(len(g.label) for g in readings)
        gauge_width = max(4, min(24, width - column - 26))
        for g in readings:
            level = _level(g, cfg)
            picture = draw.gauge(g.percent, gauge_width, style, track=True)
            line = "  {}  {} {}".format(
                draw.paint(g.label.ljust(column), "quiet", color),
                draw.paint(picture, level, color),
                draw.paint(_percent(g.percent).rjust(4), level, color))
            back = draw.format_reset(g.resets_at, now, _lang(cfg))
            if back:
                line += "  " + draw.paint("↻ " + back, "quiet", color)
            lines.append(draw.truncate(line, width))

    return "\n".join(lines)


def traffic(status, cfg, width, color):
    readings = _readings(status, cfg)
    extras = _extras(status, cfg, color)
    lang = _lang(cfg)

    for step in HEADER_STEPS:
        head = "  ".join(extras[k] for k in step if k in extras)
        for labels in ("long", "short"):
            pieces = []
            for g in readings:
                level = _level(g, cfg)
                name = g.label if labels == "long" else _short(g, lang)
                pieces.append("{} {} {:.0f}".format(
                    draw.paint(DOTS[level], level, color),
                    draw.paint(name, "quiet", color), g.percent))
            candidate = "   ".join(x for x in (head, "  ".join(pieces)) if x)
            if draw.visible_len(candidate) <= width:
                return candidate

    terse = " ".join(
        "{} {:.0f}".format(draw.paint(DOTS[_level(g, cfg)], _level(g, cfg), color), g.percent)
        for g in readings)
    return draw.truncate("  ".join(x for x in (extras.get("plan", ""), terse) if x), width)


LAYOUTS = {
    "calm-two-line": calm_two_line,
    "calm-one-line": calm_one_line,
    "expressive": expressive,
    "traffic": traffic,
}


def render(status, cfg, width, color):
    """Build the status line. Always returns a string."""
    layout = LAYOUTS.get(cfg.get("theme"), calm_two_line)
    text = layout(status, cfg, max(10, int(width)), bool(color))
    return "\n".join(draw.truncate(line, width) for line in text.split("\n"))
