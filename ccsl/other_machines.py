"""Work that ran on another machine.

The tracker only knows the sessions of this machine. Work on a project done
elsewhere can be counted there from the transcripts (tokens per model) and
added here. Its dollar value comes about like that of sessions without a
cost line: tokens times the price per model derived from the measured
sessions. These entries stand apart below the table and carry no
subscription share, because they have no days.

File other-machines.json, a list of entries:

    {"project": "...", "source": "laptop", "from": "2026-09-05", "to": "2026-11-13",
     "models": {"claude-opus-5-5": {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0}}}
"""

import json

from . import archive, paths


def default_path(env=None):
    return paths.data_file("other-machines.json", env)


def read(path=None):
    """The file's entries. Missing or malformed means none."""
    try:
        content = json.loads((path or default_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = content.get("entries") if isinstance(content, dict) else content
    return [e for e in (entries or []) if isinstance(e, dict) and e.get("project")
            and isinstance(e.get("models"), dict)]


def value(entries, prices, project=None, start=None, end=None):
    """Every entry with its dollar value. project, start, end filter like the table."""
    result = []
    for entry in entries:
        if project and project.lower() not in str(entry["project"]).lower():
            continue
        if start and entry.get("to") and str(entry["to"]) < str(start):
            continue
        if end and entry.get("from") and str(entry["from"]) > str(end):
            continue
        usd, tokens, unpriced = 0.0, 0.0, []
        for model, values in entry["models"].items():
            mass = archive.weighted_tokens(values if isinstance(values, dict) else {})
            price = prices.get(model) or prices.get(archive.AVERAGE)
            tokens += mass
            if price:
                usd += mass * price
            if not prices.get(model):
                unpriced.append(model)
        result.append({
            "project": entry["project"], "source": entry.get("source") or "",
            "from": entry.get("from"), "to": entry.get("to"),
            "usd": round(usd, 2), "weighted_tokens": round(tokens),
            "without_own_price": unpriced,
        })
    return result
