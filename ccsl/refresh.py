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


def run_once(cache_path, token, fetch=None, timeout=10, fetch_profile=None):
    """Look up once and write the cache. Always returns 0.

    The token is passed in explicitly and never read here. Otherwise None
    would mean both "no token" and "go get it yourself", and a test could
    slip onto the network through exactly that.

    For the same reason the profile is only fetched on its own when the
    usage lookup is the real one. Whoever injects `fetch` gets no hidden
    network call for the plan.

    If only the plan lookup fails, the last known plan stays and the usage
    is written anyway.
    """
    if not token:
        return 0

    handle = locks.acquire(cache.lock_path(cache_path))
    if handle is None:
        return 0

    try:
        lookup = fetch or sources.fetch_usage
        data = sources.reduce_usage(lookup(token, timeout=timeout))
        if fetch_profile is None and fetch is None:
            fetch_profile = sources.fetch_profile
        plan = None
        if fetch_profile is not None:
            try:
                plan = sources.reduce_profile(fetch_profile(token, timeout=timeout))
            except Exception:
                plan = None
        if plan is None:
            plan = (cache.read(cache_path, cache.MAX_AGE) or {}).get("plan")
        if plan:
            data["plan"] = plan
        cache.write(cache_path, data)
        cache.forget_failure(cache_path)
    except Exception:
        cache.remember_failure(cache_path)
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
