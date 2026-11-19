"""Background refresh of the cache, and of the cost archive.

The status line never touches the network itself. It starts a detached
process here and keeps drawing right away. That process takes a file lock so
several open windows do not all ask at once.

The same process keeps the cost archive growing. Claude Code deletes its
logs after 30 days by default; with the tracker on, the archive is updated
at most every few hours, so nobody needs a system timer for it.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

from . import cache, locks, paths, sources

COLLECT_EVERY = 6 * 3600


# How long to stay away after the server said "too many requests" without
# naming a time.
RATE_LIMIT_PAUSE = 300
# A server that keeps saying "too many requests" gets more room each time,
# up to an hour.
RATE_LIMIT_MAX = 3600
# The plan changes rarely; asking once an hour is plenty.
PLAN_EVERY = 3600


def _previous_wait(path):
    try:
        return int(cache.failure_path(path).read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        return 0


def _wait_from(error, previous=0):
    """Seconds to stay away after a rate-limited answer, None for other errors.

    Retry-After is honoured; without it the pause starts at five minutes and
    doubles while the server keeps refusing.
    """
    if getattr(error, "code", None) != 429:
        return None
    try:
        asked = int(error.headers.get("Retry-After") or 0)
    except (AttributeError, TypeError, ValueError):
        asked = 0
    grown = min(RATE_LIMIT_MAX, previous * 2) if previous else RATE_LIMIT_PAUSE
    return max(RATE_LIMIT_PAUSE, asked, grown)


def rate_limited(path):
    """True while a rate-limit pause from the server is running."""
    return _previous_wait(path) > 0 and cache.pause_after_failure(path, 0)


def due(cache_path, seconds):
    """Whether the usage lookup should run now: stale and not pausing."""
    return cache.is_stale(cache_path, seconds) and \
        not cache.pause_after_failure(cache_path, seconds)


def plan_due(plan_file):
    return cache.is_stale(plan_file, PLAN_EVERY) and \
        not cache.pause_after_failure(plan_file, PLAN_EVERY)


def run_once(cache_path, token, fetch=None, timeout=10, fetch_profile=None,
             plan_path=None, seconds=0):
    """Look up what is due and write the cache. Always returns 0.

    The token is passed in explicitly and never read here. Otherwise None
    would mean both "no token" and "go get it yourself", and a test could
    slip onto the network through exactly that.

    For the same reason the profile is only fetched on its own when the
    usage lookup is the real one. Whoever injects `fetch` gets no hidden
    network call for the plan.

    Usage and plan are separate lookups with separate files and separate
    pauses: one failing leaves the other untouched. Both are checked again
    after taking the lock, so a window that waited for it does not repeat
    the lookup another window just made. A rate limit on one means no
    request on the other in the same run.
    """
    if not token:
        return 0

    handle = locks.acquire(cache.lock_path(cache_path))
    if handle is None:
        return 0

    # Both lookups go to the same server: while it asks for a break, neither
    # is made.
    limited = rate_limited(cache_path) or rate_limited(cache_path.with_name("plan.json")
                                                       if plan_path is None else plan_path)
    try:
        if not limited and due(cache_path, seconds):
            try:
                lookup = fetch or sources.fetch_usage
                cache.write(cache_path, sources.reduce_usage(lookup(token, timeout=timeout)))
                cache.forget_failure(cache_path)
            except Exception as error:
                wait = _wait_from(error, _previous_wait(cache_path))
                limited = limited or wait is not None
                cache.remember_failure(cache_path, wait)

        if fetch_profile is None and fetch is None:
            fetch_profile = sources.fetch_profile
        plan_file = plan_path or cache_path.with_name("plan.json")
        if fetch_profile is not None and not limited and plan_due(plan_file):
            try:
                plan = sources.reduce_profile(fetch_profile(token, timeout=timeout))
                if plan:
                    cache.write(plan_file, {"plan": plan})
                cache.forget_failure(plan_file)
            except Exception as error:
                cache.remember_failure(plan_file, _wait_from(error, _previous_wait(plan_file)))
    finally:
        locks.release(handle)
    return 0


def collect_due(env=None, every=COLLECT_EVERY):
    stamp = paths.data_file("collect.stamp", env)
    a = cache.age(stamp)
    return a is None or a > every


def collect_if_due(cfg, env=None, collect=None):
    """Update the cost archive if the tracker is on and the last run is old.

    Runs in the background process with low priority. Any failure is
    swallowed: the archive simply catches up next time.
    """
    if not cfg.get("cost_tracking") or not collect_due(env):
        return False
    stamp = paths.data_file("collect.stamp", env)
    try:
        paths.ensure_data_dir(env)
        stamp.write_text(str(int(time.time())), encoding="utf-8")
    except Exception:
        return False
    try:
        if hasattr(os, "nice"):
            os.nice(10)
    except Exception:
        pass
    try:
        if collect is None:
            from . import report_cli
            collect = report_cli.collect_and_summarize
        collect()
        return True
    except Exception:
        return False


def spawn(python=None, script=None, starter=None):
    """Start the refresh detached. Never raises.

    `starter` can be injected in tests. Without it a test that only wants to
    check that spawn does not raise would really start a process that goes
    onto the network.
    """
    try:
        python = python or sys.executable
        script = Path(script) if script else Path(__file__).resolve().parent.parent / "statusline.py"
        extra = {}
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            extra["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        else:
            extra["start_new_session"] = True
        start = starter or subprocess.Popen
        start(
            [str(python), str(script), "--refresh"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **extra
        )
    except Exception:
        pass
