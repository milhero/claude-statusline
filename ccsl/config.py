"""Settings: defaults, then the file, then environment variables.

Nothing in here may raise. A typo in the settings file must never take the
status line down with it; an invalid value simply falls back to its default.
"""

import json
import os
from pathlib import Path

from . import paths

THEMES = ("calm-two-line", "calm-one-line", "expressive", "traffic")
BACKFILL_MEASURES = ("lines", "commits")
GAUGE_STYLES = ("line", "circle", "block", "spark")
PLAN_STYLES = ("violet", "terracotta", "blue", "green", "grey", "plain")
COLOR_MODES = ("auto", "always", "never")
BACKGROUNDS = ("auto", "dark", "light")
LANGUAGES = ("auto", "en", "de")

DEFAULTS = {
    "theme": "calm-one-line",
    "language": "auto",
    "show": {
        "week": True,
        "model_week": True,
        "five_hour": True,
        "context": True,
        "effort": True,
        "cost": False,
        "project": False,
        "plan": True,
        "model": True,
        "directory": True,
        "git_branch": True,
    },
    "thresholds": {"warn": 50, "critical": 80},
    "plan_style": "violet",
    "gauge_style": "line",
    "gauge_track": False,
    "xhigh_as_ultracode": False,
    "cache_seconds": 300,
    "color": "auto",
    "background": "auto",
    "live_lookup": True,
    # Cost tracker
    "cost_tracking": False,
    "backfill_measure": "lines",
    "project_roots": [],
    "git_author_emails": [],
}

TRUE = ("1", "true", "yes", "on")
FALSE = ("0", "false", "no", "off")


def default_path(env=None):
    return paths.data_file("config.json", env)


def _type_fits(value, template):
    """Check a value against the type of its default.

    bool has to be tested before int: bool is a subclass of int in Python,
    and True would otherwise pass as a number.
    """
    if isinstance(template, bool):
        return isinstance(value, bool)
    if isinstance(template, int):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(template, list):
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    return isinstance(value, type(template))


def _as_switch(text):
    t = (text or "").strip().lower()
    if t in TRUE:
        return True
    if t in FALSE:
        return False
    return None


def _as_int(text):
    try:
        return int((text or "").strip())
    except ValueError:
        return None


def _merge(target, source):
    """Take over from source only keys that already exist in target."""
    for key, value in source.items():
        if key not in target:
            continue
        template = target[key]
        if isinstance(template, dict):
            if isinstance(value, dict):
                _merge(template, value)
        elif _type_fits(value, template):
            target[key] = value


def _apply_env(cfg, env):
    for name, key, allowed in (
        ("CCSL_THEME", "theme", THEMES),
        ("CCSL_LANGUAGE", "language", LANGUAGES),
        ("CCSL_PLAN_STYLE", "plan_style", PLAN_STYLES),
        ("CCSL_GAUGE_STYLE", "gauge_style", GAUGE_STYLES),
        ("CCSL_COLOR", "color", COLOR_MODES),
        ("CCSL_BACKGROUND", "background", BACKGROUNDS),
        ("CCSL_BACKFILL_MEASURE", "backfill_measure", BACKFILL_MEASURES),
    ):
        value = env.get(name)
        if value in allowed:
            cfg[key] = value

    for name, key in (
        ("CCSL_GAUGE_TRACK", "gauge_track"),
        ("CCSL_XHIGH_AS_ULTRACODE", "xhigh_as_ultracode"),
        ("CCSL_LIVE_LOOKUP", "live_lookup"),
        ("CCSL_COST_TRACKING", "cost_tracking"),
    ):
        switch = _as_switch(env.get(name))
        if switch is not None:
            cfg[key] = switch

    seconds = _as_int(env.get("CCSL_CACHE_SECONDS"))
    if seconds is not None and seconds >= 0:
        cfg["cache_seconds"] = seconds

    for name, key in (("CCSL_WARN", "warn"), ("CCSL_CRITICAL", "critical")):
        number = _as_int(env.get(name))
        if number is not None:
            cfg["thresholds"][key] = number

    for key in cfg["show"]:
        switch = _as_switch(env.get("CCSL_SHOW_" + key.upper()))
        if switch is not None:
            cfg["show"][key] = switch


def load(path=None, env=None):
    """Always returns a complete settings dict."""
    env = os.environ if env is None else env
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy without importing copy
    if path is None:
        path = default_path(env)

    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            _merge(cfg, raw)
    except Exception:
        pass

    try:
        _apply_env(cfg, env)
    except Exception:
        pass

    for key, allowed in (
        ("theme", THEMES),
        ("language", LANGUAGES),
        ("color", COLOR_MODES),
        ("background", BACKGROUNDS),
        ("gauge_style", GAUGE_STYLES),
        ("plan_style", PLAN_STYLES),
        ("backfill_measure", BACKFILL_MEASURES),
    ):
        if cfg[key] not in allowed:
            cfg[key] = DEFAULTS[key]
    return cfg


def save(changes, path=None, env=None):
    """Merge changes into the settings file, keeping everything else in it."""
    path = Path(path) if path else default_path(env)
    try:
        current = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(current, dict):
            current = {}
    except Exception:
        current = {}

    def deep(target, source):
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                deep(target[key], value)
            else:
                target[key] = value

    deep(current, changes)
    paths.write_atomic(path, json.dumps(current, indent=2, ensure_ascii=False) + "\n")
    return path
