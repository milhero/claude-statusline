"""Drawing helpers: gauges, colours, width, reset times.

Everything here is pure: same input, same output, no clock, environment or
filesystem. That keeps it fully testable.
"""

import re
from datetime import datetime

from . import i18n

ANSI = re.compile(r"\x1b\[[0-9;]*m")
RESET = "\x1b[0m"

# Unremarkable values deliberately get NO colour. They inherit the terminal's
# foreground and blend in. Grey would read as "disabled" and makes every red
# next to it look louder than it is.
COLORS = {
    "ok": "",                     # no colour at all
    "warn": "\x1b[38;5;137m",     # muted ochre
    "crit": "\x1b[38;5;131m",     # muted terracotta
    "accent": "\x1b[38;5;109m",   # calm blue-grey
    "quiet": "\x1b[38;5;242m",    # receded, for labels
    "strong": "\x1b[1m",
}


def level(percent, warn, crit):
    """Level of a reading. Both thresholds are inclusive."""
    try:
        p = float(percent)
    except (TypeError, ValueError):
        return "ok"
    if p >= crit:
        return "crit"
    if p >= warn:
        return "warn"
    return "ok"


def visible_len(text):
    """Length without the invisible colour sequences."""
    return len(ANSI.sub("", text))


def truncate(text, width):
    """Cut to visible characters without splitting a colour sequence."""
    if width <= 0:
        return ""
    if visible_len(text) <= width:
        return text

    out = []
    visible = 0
    open_color = False
    i = 0
    while i < len(text) and visible < width:
        match = ANSI.match(text, i)
        if match:
            out.append(match.group())
            open_color = match.group() != RESET
            i = match.end()
            continue
        out.append(text[i])
        visible += 1
        i += 1

    if open_color:
        out.append(RESET)
    return "".join(out)


def paint(text, kind, enabled):
    """Colour a text. An empty colour explicitly means: leave it alone."""
    if not enabled:
        return text
    color = COLORS.get(kind)
    if not color:
        return text
    return color + text + RESET


def color_enabled(setting, env):
    """Colours only when both the setting and the environment allow it."""
    if setting == "never":
        return False
    if setting == "always":
        return True
    if env.get("NO_COLOR"):
        return False
    if env.get("TERM", "") in ("dumb", ""):
        # Windows terminals often leave TERM unset and still render colour.
        return bool(env.get("WT_SESSION") or env.get("ConEmuANSI") == "ON")
    return True


def format_reset(when, now, lang="en"):
    """When a window resets, in the time zone of `now`.

    The zone comes in with `now` instead of the system clock, so the function
    can be tested without time zone tricks.
    """
    if not isinstance(when, datetime) or not isinstance(now, datetime):
        return ""
    try:
        target = when.astimezone(now.tzinfo)
    except (ValueError, OSError):
        return ""

    if (target - now).total_seconds() <= 0:
        return ""
    # By calendar day, not by 24 hours: on Tuesday evening, Wednesday 08:00 is
    # less than a day away and still "tomorrow".
    days = (target.date() - now.date()).days
    clock = "{:02d}:{:02d}".format(target.hour, target.minute)
    if days == 0:
        return i18n.t("today", lang) + " " + clock
    if days == 1:
        return i18n.t("tomorrow", lang) + " " + clock
    return "{} {}".format(i18n.weekday(target.weekday(), lang), clock)


LINE_FULL = "━"
LINE_REST = "╌"
# Eighth steps, so a block bar ends exactly at the value instead of rounding
EIGHTHS = ("", "▏", "▎", "▍", "▌", "▋", "▊", "▉")
# Circle segments like a clock face
CIRCLES = ("○", "◔", "◑", "◕", "●")
# Column heights: one character carries the whole value
SPARK = ("▁", "▂", "▃", "▄", "▅", "▆", "▇", "█")


def _fraction(percent):
    """Value as a fraction between 0 and 1. Above a hundred percent is capped."""
    try:
        p = float(percent)
    except (TypeError, ValueError):
        p = 0.0
    return max(0.0, min(1.0, p / 100.0))


def _line(percent, width, track):
    share = _fraction(percent)
    # Anything above zero shows at least one segment, so "barely anything"
    # stays visibly different from "nothing".
    full = 0 if share <= 0 else min(width, max(1, int(round(share * width))))
    if track:
        return LINE_FULL * full + LINE_REST * (width - full)
    return LINE_FULL * full


def _block(percent, width, track):
    total = _fraction(percent) * width
    full = int(total)
    eighth = int(round((total - full) * 8))
    if eighth >= 8:
        full += 1
        eighth = 0
    text = "█" * full + EIGHTHS[eighth]
    if not text and _fraction(percent) > 0:
        text = EIGHTHS[1]
    if track:
        text += " " * max(0, width - len(text))
    return text


def _circle(percent):
    """Five steps; each boundary lies halfway between two of them."""
    share = _fraction(percent)
    for i, bound in enumerate((0.125, 0.375, 0.625, 0.875)):
        if share < bound:
            return CIRCLES[i]
    return CIRCLES[4]


def _spark(percent):
    step = int(_fraction(percent) * len(SPARK))
    return SPARK[min(step, len(SPARK) - 1)]


def gauge(percent, width, style="line", track=False):
    """Draw a value in the chosen style.

    circle and spark always take exactly one character, whatever the width.
    An unknown style falls back to the line instead of failing.
    """
    if style == "circle":
        return _circle(percent)
    if style == "spark":
        return _spark(percent)
    if style == "block":
        return _block(percent, max(1, width), track)
    return _line(percent, max(1, width), track)


# Colour families for the plan. Within a family only lightness and saturation
# change, never the hue. A gradient across two hues reads as "colourful", one
# within a single hue reads as a sheen.
#
# violet and terracotta follow Claude's brand colours #d0b4ff and #da7756,
# mapped onto the 256-colour palette.
FAMILIES = {
    "violet": (189, 183, 147, 141, 105, 99),
    "terracotta": (223, 216, 209, 173, 137, 130),
    "blue": (159, 153, 116, 110, 74, 68),
    "green": (194, 151, 114, 108, 72, 65),
    "grey": (253, 250, 246, 243, 240, 237),
}

# How much of its family a plan uses. The effect comes from the span, not
# from loudness: Pro is a short, pale sheen, Ultra runs the whole family.
SPANS = {
    "ultra": 6,
    "max_20x": 5,
    "max_5x": 3,
    "team": 3,
    "pro": 2,
    "unknown": 1,
}


def plan_ramp(family, tier):
    """The colour ramp for a plan within a family."""
    tones = FAMILIES.get(family) or FAMILIES["violet"]
    count = SPANS.get(tier or "", 1)
    return tones[:max(1, min(count, len(tones)))]


# Every model has its own colour family. The effort level picks the span
# within it, just as the plan does. That gives two gradients side by side,
# each in exactly one hue, instead of a rainbow.
#
# Stronger from bottom to top: Haiku, Sonnet, Opus, Fable. Ochre and
# terracotta stay unused, they belong to the warnings; violet belongs to the
# plan.
MODEL_FAMILIES = {
    "fable": (225, 219, 213, 207, 200, 164, 127),
    "opus": (195, 159, 122, 86, 43, 37, 30),
    "sonnet": (189, 153, 111, 75, 69, 33, 26),
    "haiku": (194, 157, 151, 114, 108, 71, 65),
    "unknown": (253, 251, 249, 246, 244, 242, 240),
}

# Which part of the family an effort level takes. The ranges shift instead of
# only growing longer; otherwise every level would start at the same pale
# tone and they would barely differ. low is pale and flat, max is strong
# with no pale end.
EFFORT_RANGES = {
    "low": (0, 1),
    "medium": (0, 2),
    "high": (0, 4),
    "xhigh": (2, 6),
    "max": (3, 7),
}

# Without an effort level, as with Haiku: a short range at the pale end.
# Not a special case, just another range.
RANGE_WITHOUT_EFFORT = (0, 2)

# From these levels on, bold is added. Colour alone no longer separates the
# top levels well enough.
BOLD_LEVELS = ("xhigh", "max")

# Ultracode cannot be detected from outside. Checked on 2.1.278:
# ultracodeActive stays inside the program, the mode lines in the logs always
# say "normal", and settings.json keeps effortLevel and ultracode apart. The
# documentation says the same: ultracode reports itself as xhigh.
#
# Labelling xhigh as ultracode would be a claim, not a measurement, and plain
# wrong for anyone running xhigh by default. Whoever really runs ultracode
# and wants to see it turns it on deliberately.
ULTRACODE_LEVEL = "xhigh"
ULTRACODE_NAME = "ultracode"


def model_family(name):
    """The colour family for a model name."""
    text = (name or "").lower()
    for key in ("fable", "opus", "sonnet", "haiku"):
        if key in text:
            return MODEL_FAMILIES[key]
    return MODEL_FAMILIES["unknown"]


def model_ramp(name, effort):
    """Colour ramp for model and effort together."""
    tones = model_family(name)
    start, end = EFFORT_RANGES.get(effort or "", RANGE_WITHOUT_EFFORT)
    return tones[start:end] or tones[:1]


def effort_bold(effort):
    """True if this level also gets bold."""
    return effort in BOLD_LEVELS


def effort_name(effort, as_ultracode=False):
    """Label of the effort level.

    as_ultracode is off by default: the level is technically xhigh, and
    ultracode cannot be derived from it.
    """
    if as_ultracode and effort == ULTRACODE_LEVEL:
        return ULTRACODE_NAME
    return effort


# The families above are built for dark terminals: their pale end would
# vanish on white. On a light background each tone has a counterpart in the
# same hue, picked by hand: muted, readable on white, and in the same order,
# so a gradient keeps its shape and its span.
LIGHT_FAMILIES = {
    "violet": (104, 98, 62, 56, 55, 54),
    "terracotta": (174, 173, 167, 131, 130, 94),
    "blue": (110, 74, 68, 32, 26, 25),
    "green": (108, 72, 71, 65, 29, 22),
    "grey": (245, 243, 241, 239, 237, 235),
}
LIGHT_MODEL_FAMILIES = {
    "fable": (176, 170, 169, 164, 163, 127, 90),
    "opus": (73, 37, 31, 30, 24, 23, 23),
    "sonnet": (110, 74, 68, 32, 26, 25, 19),
    "haiku": (108, 72, 71, 35, 29, 28, 22),
    "unknown": (245, 244, 243, 241, 239, 237, 235),
}


def _counterpart(family_tones):
    for dark, light in ((FAMILIES, LIGHT_FAMILIES), (MODEL_FAMILIES, LIGHT_MODEL_FAMILIES)):
        for name, tones in dark.items():
            if tones == tuple(family_tones):
                return light[name]
    return tuple(family_tones)


def for_background(ramp, family_tones, light):
    """The ramp as it should look on the current background."""
    if not light:
        return ramp
    mapping = dict(zip(family_tones, _counterpart(family_tones)))
    return tuple(mapping.get(t, t) for t in ramp)


def light_background(setting, theme=None, env=None):
    """Whether the terminal background is light.

    setting is the status line's own choice (auto, dark, light). With auto,
    Claude Code's theme decides; with its own "auto" theme, the COLORFGBG
    variable that many terminals set ("15;0": light text on black).
    """
    if setting in ("dark", "light"):
        return setting == "light"
    theme = (theme or "").lower()
    if theme.startswith("light"):
        return True
    if theme.startswith("dark") or theme.startswith("custom"):
        return False
    try:
        bg = int(((env or {}).get("COLORFGBG") or "").split(";")[-1])
    except ValueError:
        return False
    return bg in (7, 15)


def gradient(text, ramp, enabled):
    """Spread a colour ramp across the characters of a text.

    Spaces stay uncoloured: colour on a space is invisible and only bloats
    the string.
    """
    if not enabled or not ramp or not text:
        return text
    if len(ramp) == 1:
        return "\x1b[38;5;{}m{}{}".format(ramp[0], text, RESET)

    chars = list(text)
    last = max(1, len(chars) - 1)
    parts = []
    for i, ch in enumerate(chars):
        if ch == " ":
            parts.append(ch)
            continue
        position = i / last * (len(ramp) - 1)
        parts.append("\x1b[38;5;{}m{}".format(ramp[int(round(position))], ch))
    return "".join(parts) + RESET
