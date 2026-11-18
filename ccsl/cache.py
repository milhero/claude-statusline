"""Cache for the account lookups.

Writes go through a temporary file and a rename. The rename is atomic on all
three systems, so a reader running at the same moment never sees half a file.
"""

import json
import time
from pathlib import Path

from . import paths

# Upper bound of usefulness. Even with a very high cache_seconds, nothing
# older than this is shown: an hour-old percentage is worse than none.
MAX_AGE = 3600


def default_path(env=None):
    return paths.data_file("cache.json", env)


def lock_path(path=None):
    p = Path(path) if path else default_path()
    return p.with_name(p.name + ".lock")


def failure_path(path=None):
    p = Path(path) if path else default_path()
    return p.with_name(p.name + ".failed")


def remember_failure(path):
    """Note a failed lookup. A failure here has no consequences."""
    try:
        failure_path(path).parent.mkdir(parents=True, exist_ok=True)
        failure_path(path).write_text("", encoding="utf-8")
    except Exception:
        pass


def forget_failure(path):
    try:
        failure_path(path).unlink()
    except Exception:
        pass


def pause_after_failure(path, seconds):
    """True while a failed lookup is younger than the given span.

    Without this pause the cache would stay old and every redraw would start
    the next attempt right away.
    """
    a = age(failure_path(path))
    return a is not None and a < seconds


def age(path):
    """Age in seconds, or None if the file is missing."""
    try:
        return time.time() - Path(path).stat().st_mtime
    except Exception:
        return None


def is_stale(path, seconds):
    a = age(path)
    return a is None or a > seconds


def read(path, max_age):
    """The cached data, or None if missing, broken or too old."""
    a = age(path)
    if a is None or a > min(max_age, MAX_AGE):
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def write(path, data):
    """Write atomically. A failure to write is no reason to stop."""
    try:
        paths.write_atomic(path, json.dumps(data, ensure_ascii=False))
    except Exception:
        pass
