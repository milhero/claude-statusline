"""The running project's cost for the status line.

The status line computes nothing itself. It reads what claude-costs wrote,
and only when that is fresh enough. A week-old number would be worse than
none, because it would be quietly wrong.
"""

import json
import time
from pathlib import Path

from . import paths

# Older than this, the summary is no longer fit for a running display.
MAX_AGE = 26 * 3600


def summary_path(env=None):
    return paths.data_file("cost-summary.json", env)


def for_project(name, path=None, session=None):
    """The summary entry for a project name, as a copy.

    session_usd is the part of the project value that already comes from the
    running session. The summary contains it once the session was archived
    or when it was resumed; whoever adds the session's cost has to take it
    off first.

    A project without history gets 0 $. A missing or stale summary gives an
    entry with the name only and stale=True: a zero there would be a false
    statement, the total is not zero but unknown.
    """
    if not name:
        return None
    unknown = {"name": name, "stale": True}
    target = Path(path) if path else summary_path()
    try:
        if time.time() - target.stat().st_mtime > MAX_AGE:
            return unknown
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return unknown
    if not isinstance(data, dict):
        return unknown

    for entry in data.get("projects") or []:
        if isinstance(entry, dict) and entry.get("name") == name:
            result = dict(entry)
            break
    else:
        result = {"name": name, "api_usd": 0.0}

    shares = (data.get("sessions") or {}).get(session) if session else None
    value = (shares or {}).get(name) if isinstance(shares, dict) else None
    result["session_usd"] = float(value) if isinstance(value, (int, float)) else 0.0
    return result
