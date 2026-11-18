#!/usr/bin/env python3
"""Status line for Claude Code.

Called on every message with the session state as JSON on stdin. Two
promises hold without exception:

1. It always exits with 0 and always prints something.
2. It never waits for the network. Lookups run detached in the background;
   the line is drawn right away with whatever is there.
"""

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ccsl import (cache, config, draw, i18n, paths, project_costs, refresh,  # noqa: E402
                  session_project, sources, themes)

VERSION = sources.VERSION


def terminal_width(env):
    """Columns of the terminal. COLUMNS first: Claude Code sets it, and the
    script cannot measure the terminal itself because its output is captured."""
    try:
        cols = int(env.get("COLUMNS", "0"))
        if cols > 0:
            return cols
    except (TypeError, ValueError):
        pass
    try:
        return shutil.get_terminal_size((80, 24)).columns
    except Exception:
        return 80


def read_input():
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def claude_theme(env=None):
    """Claude Code's theme: settings.json first, the older ~/.claude.json after."""
    for path in (paths.settings_file(env), paths.home() / ".claude.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8")).get("theme")
        except Exception:
            continue
        if isinstance(value, str):
            return value
    return None


def load_config(env=None):
    cfg = config.load(env=env)
    cfg["_lang"] = i18n.resolve(cfg.get("language"), env)
    cfg["_light"] = draw.light_background(
        cfg.get("background"), claude_theme(env) if cfg.get("background") == "auto" else None,
        os.environ if env is None else env)
    return cfg


def build_status(data, cfg):
    lang = cfg.get("_lang", "en")
    status = sources.from_stdin(data, lang)

    try:
        status.plan, status.plan_tier = sources.read_plan()
    except Exception:
        pass

    if cfg.get("show", {}).get("project"):
        # The status line computes nothing itself, it reads what claude-costs
        # wrote. Which project is being worked on comes from session_project:
        # the working directory wanders during a session, the project does not.
        try:
            workspace = data.get("workspace") or {}
            ctx = session_project.context_for_statusline(cfg)
            name = session_project.determine(
                data.get("session_id"), workspace.get("current_dir"),
                workspace.get("project_dir"), ctx, transcript=data.get("transcript_path"))
            entry = project_costs.for_project(name, session=data.get("session_id"))
            if entry:
                status.project = entry.get("name")
                # What is being produced right now is in cost.total_cost_usd
                # and gets added, so the value grows while working. The part
                # of this session already in the summary comes off first.
                # Without a valid summary the value stays empty: the session
                # cost alone is no total.
                if not entry.get("stale"):
                    status.project_usd = ((entry.get("api_usd") or 0)
                                          - (entry.get("session_usd") or 0)
                                          + (status.cost_usd or 0))
        except Exception:
            pass

    if cfg.get("live_lookup"):
        path = cache.default_path()
        try:
            cached = cache.read(path, cfg.get("cache_seconds", 300))
            if cached is not None:
                status.scoped = sources.scoped_gauge(cached)
                # The server's plan beats the credentials file, which stays
                # stale after a plan change.
                from_server = sources.plan_from_cache(cached)
                if from_server:
                    status.plan, status.plan_tier = from_server
                # The lookup knows the server's state across all surfaces,
                # Claude Code's input only this session. Which is fresher
                # depends on where the last work happened.
                status.week = sources.fresher(status.week, sources.live_gauge(
                    cached, "weekly_all", "week", i18n.t("week", lang)))
                status.five_hour = sources.fresher(status.five_hour, sources.live_gauge(
                    cached, "session", "five_hour", i18n.t("five_hour", lang)))
        except Exception:
            pass

    # Draw first, then kick off: the call never waits for the result.
    try:
        due_lookup = False
        if cfg.get("live_lookup"):
            limit = cfg.get("cache_seconds", 300)
            due_lookup = (cache.is_stale(path, limit)
                          and not cache.pause_after_failure(path, limit))
        if due_lookup or (cfg.get("cost_tracking") and refresh.collect_due()):
            refresh.spawn(sys.executable, Path(__file__).resolve())
    except Exception:
        pass

    return status


def write(text):
    """Write as UTF-8 explicitly. Windows would otherwise fall back to another
    encoding and turn the gauge characters into question marks."""
    try:
        sys.stdout.buffer.write((text + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()
    except Exception:
        try:
            print(text)
        except Exception:
            pass


def fallback_line(data):
    """Last resort when drawing itself fails."""
    try:
        parts = []
        model = data.get("model", {}).get("display_name")
        if model:
            parts.append(str(model))
        place = data.get("workspace", {}).get("current_dir")
        if place:
            parts.append(str(place))
        return "  ".join(parts)
    except Exception:
        return ""


def sample_status(week, scoped, five, context, cost, lang, plan=("Max 20x", "max_20x"),
                  model="Opus 5", effort="high", directory="~/projects/aurora", project=None):
    from datetime import datetime, timedelta, timezone
    from ccsl.model import Gauge, Status

    now = datetime.now(timezone.utc).astimezone()
    later = now + timedelta(days=2, hours=18)
    soon = now + timedelta(hours=5)
    return Status(week=Gauge("week", i18n.t("week", lang), week, later),
                  scoped=Gauge("model_week", "Fable", scoped, later),
                  five_hour=Gauge("five_hour", i18n.t("five_hour", lang), five, soon),
                  context=Gauge("context", i18n.t("context", lang), context),
                  plan=plan[0], plan_tier=plan[1], model=model, effort=effort,
                  directory=directory, branch="main", cost_usd=cost,
                  project=project[0] if project else None,
                  project_usd=project[1] if project else None)


def demo(env=None):
    """All layouts with fixed sample values. No network, no files."""
    env = os.environ if env is None else env
    cfg = config.load(path=Path(os.devnull), env={})
    cfg["_lang"] = i18n.resolve(config.load(env=env).get("language"), env)
    cfg["show"]["cost"] = True
    width = terminal_width(env)
    color = draw.color_enabled(cfg["color"], env)
    lang = cfg["_lang"]

    lines = []
    for name in config.THEMES:
        cfg["theme"] = name
        lines.append(draw.paint("── " + name + " " + "─" * max(0, width - len(name) - 4),
                                "quiet", color))
        lines.append(themes.render(sample_status(91, 100, 0, 14, 2.41, lang), cfg, width, color))
        lines.append("")
        lines.append(themes.render(sample_status(31, 38, 12, 22, 0.38, lang), cfg, width, color))
        lines.append("")
    write("\n".join(lines).rstrip("\n"))
    return 0


def colors(env=None):
    """Every colour family across every plan, side by side."""
    env = os.environ if env is None else env
    color = draw.color_enabled("always", env)
    lang = i18n.resolve(config.load(env=env).get("language"), env)
    tiers = (("ultra", "ULTRA"), ("max_20x", "MAX 20×"), ("max_5x", "MAX 5×"), ("pro", "PRO"))
    head = ("Families for plan_style. The plan sets the span, not the loudness."
            if lang == "en" else
            "Familien für plan_style. Die Stufe bestimmt die Spanne, nicht die Grelle.")
    lines = [head, ""]
    for name in draw.FAMILIES:
        parts = [draw.gradient(text, draw.plan_ramp(name, tier), color) for tier, text in tiers]
        lines.append("  {:<12} {}".format(name, "    ".join(parts)))
    lines.append("")
    lines.append('  "plan_style" in ' + str(config.default_path()))
    lines.append("  CCSL_PLAN_STYLE=terracotta")
    write("\n".join(lines))
    return 0


DIAG = {
    "en": {"settings": "Settings", "present": "present", "defaults": "missing, defaults apply",
           "layout": "Layout: {}, colour: {}, language: {}, lookup: {}, cost tracking: {}",
           "on": "on", "off": "off", "login": "Login", "file": "credentials file",
           "keychain": "macOS keychain", "missing": "MISSING",
           "missing_note": "Without it only the model week and the server plan are missing.",
           "plan_file": "  Plan from login: {} ({})", "plan_server": "  Plan from server: {}",
           "not_yet": "not looked up yet", "cache": "Cache", "none_yet": "none yet",
           "cache_age": "{:.0f} seconds old (usable up to {})",
           "model_week": "  Model week: {}", "not_found": "no entry found",
           "lookup": "Lookup", "skipped": "skipped, no token",
           "ok": "HTTP 200, {} entries", "failed": "failed ({})",
           "summary": "Cost summary", "data": "Data folder"},
    "de": {"settings": "Einstellungen", "present": "vorhanden",
           "defaults": "nicht vorhanden, Standardwerte",
           "layout": "Darstellung: {}, Farbe: {}, Sprache: {}, Abfrage: {}, Kosten-Tracker: {}",
           "on": "an", "off": "aus", "login": "Anmeldung", "file": "Anmeldedatei",
           "keychain": "macOS-Schlüsselbund", "missing": "FEHLT",
           "missing_note": "Ohne sie fehlen nur die Modell-Woche und der Plan vom Server.",
           "plan_file": "  Plan laut Anmeldung: {} ({})", "plan_server": "  Plan laut Server: {}",
           "not_yet": "noch nicht abgefragt", "cache": "Zwischenspeicher",
           "none_yet": "noch keiner", "cache_age": "{:.0f} Sekunden alt (brauchbar bis {})",
           "model_week": "  Modell-Woche: {}", "not_found": "kein Eintrag gefunden",
           "lookup": "Abfrage", "skipped": "übersprungen, kein Token",
           "ok": "HTTP 200, {} Einträge", "failed": "fehlgeschlagen ({})",
           "summary": "Kostenstand", "data": "Datenordner"},
}


def diagnose(env=None):
    """Check the sources one by one. Never prints the token."""
    cfg = load_config(env)
    d = DIAG[cfg["_lang"]]
    lines = ["claude-statusline " + VERSION, "Python {}.{}.{}".format(*sys.version_info[:3]),
             "{}: {}".format(d["data"], paths.data_dir(env))]
    cp = config.default_path(env)
    lines.append("{}: {} ({})".format(d["settings"], cp,
                                      d["present"] if cp.exists() else d["defaults"]))
    lines.append(d["layout"].format(cfg["theme"], cfg["color"], cfg["_lang"],
                                    d["on"] if cfg["live_lookup"] else d["off"],
                                    d["on"] if cfg["cost_tracking"] else d["off"]))

    where = sources.credentials_source()
    lines.append("{}: {}".format(d["login"], d[where] if where else d["missing"]))
    if not where:
        lines.append("  " + d["missing_note"])
    else:
        shown, tier = sources.read_plan(keychain=True)
        lines.append(d["plan_file"].format(shown or "?", tier or "-"))
    server = sources.plan_from_cache(cache.read(cache.default_path(), cache.MAX_AGE) or {})
    lines.append(d["plan_server"].format("{} ({})".format(*server) if server else d["not_yet"]))

    c = cache.default_path()
    age = cache.age(c)
    if age is None:
        lines.append("{}: {}".format(d["cache"], d["none_yet"]))
    else:
        lines.append("{}: {}".format(d["cache"], d["cache_age"].format(
            age, min(cfg["cache_seconds"], cache.MAX_AGE))))
        g = sources.scoped_gauge(cache.read(c, cache.MAX_AGE) or {})
        lines.append(d["model_week"].format(
            "{} {:.0f}%".format(g.label, g.percent) if g else d["not_found"]))

    token = sources.read_token() if cfg["live_lookup"] else None
    if not token:
        lines.append("{}: {}".format(d["lookup"], d["skipped"]))
    else:
        try:
            answer = sources.fetch_usage(token, timeout=10)
            lines.append("{}: {}".format(d["lookup"], d["ok"].format(
                len(answer.get("limits", []) or []))))
        except Exception as error:
            # The error text may contain the URL, never the headers.
            lines.append("{}: {}".format(d["lookup"], d["failed"].format(type(error).__name__)))

    summary = project_costs.summary_path(env)
    age = cache.age(summary)
    lines.append("{}: {}".format(d["summary"], "{} ({:.1f} h)".format(summary, age / 3600)
                                 if age is not None else d["none_yet"]))
    write("\n".join(lines))
    return 0


def main(argv):
    if "--version" in argv:
        write(VERSION)
        return 0
    if "--refresh" in argv:
        cfg = config.load()
        if cfg.get("live_lookup"):
            limit = cfg.get("cache_seconds", 300)
            path = cache.default_path()
            if cache.is_stale(path, limit):
                refresh.run_once(path, sources.read_token())
        refresh.collect_if_due(cfg)
        return 0
    if "--demo" in argv:
        return demo()
    if "--colors" in argv:
        return colors()
    if "--diagnose" in argv:
        return diagnose()

    data = {}
    try:
        data = read_input()
        cfg = load_config()
        status = build_status(data, cfg)
        width = terminal_width(os.environ)
        color = draw.color_enabled(cfg["color"], os.environ)
        write(themes.render(status, cfg, width, color))
    except Exception:
        write(fallback_line(data))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception:
        # Not even an error in main may turn the status line red.
        sys.exit(0)
