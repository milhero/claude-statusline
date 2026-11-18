"""What there is to know before setting up the cost tracker.

The setup assistant (the cost-setup skill) reads this as JSON and talks it
through with the user. Everything here is plain fact-finding; deciding is
left to the user, computing to the rest of the code.
"""

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import (attribution, backfill, cache, config, invoices as inv,
               other_machines, paths, rules as rules_mod, sources)

# How deep below the home folder repositories are looked for. Two levels
# cover ~/project and ~/code/project without crawling the whole disk.
SCAN_DEPTH = 3
SKIP = {"node_modules", "Library", "AppData", ".cache", ".local", ".npm", ".cargo",
        ".rustup", "go", ".git", "Applications", "Pictures", "Music", "Movies",
        "Downloads", ".Trash", "snap"}


def _iso(ts):
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().date().isoformat()
    except (OverflowError, OSError, ValueError, TypeError):
        return None


def logs_info(env=None):
    root = paths.logs_dir(env)
    files, size, oldest, newest = 0, 0, None, None
    if root.exists():
        for folder in root.iterdir():
            if not folder.is_dir():
                continue
            for f in folder.glob("*.jsonl"):
                try:
                    st = f.stat()
                except OSError:
                    continue
                files += 1
                size += st.st_size
                oldest = st.st_mtime if oldest is None else min(oldest, st.st_mtime)
                newest = st.st_mtime if newest is None else max(newest, st.st_mtime)
    return {"dir": str(root), "files": files, "size_mb": round(size / 1e6, 1),
            "oldest": _iso(oldest), "newest": _iso(newest)}


def history_first(env=None):
    path = paths.claude_dir(env) / "history.jsonl"
    first = None
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    stamp = json.loads(line).get("timestamp")
                except (ValueError, AttributeError):
                    continue
                if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
                    first = stamp if first is None else min(first, stamp)
    except OSError:
        return None
    return _iso(first / 1000) if first else None


def cleanup_days(env=None):
    try:
        data = json.loads(paths.settings_file(env).read_text(encoding="utf-8"))
    except Exception:
        return None
    value = data.get("cleanupPeriodDays") if isinstance(data, dict) else None
    return value if isinstance(value, int) else None


def scan_repos(start=None, depth=SCAN_DEPTH):
    """Git repositories below the home folder, a few levels deep."""
    start = Path(start) if start else paths.home()
    found = []

    def walk(folder, level):
        try:
            entries = list(os.scandir(str(folder)))
        except OSError:
            return
        if any(e.name == ".git" for e in entries):
            found.append(rules_mod.normalize(str(folder)))
            return
        if level >= depth:
            return
        for e in entries:
            if e.is_dir(follow_symlinks=False) and e.name not in SKIP and \
                    not e.name.startswith("."):
                walk(e.path, level + 1)

    walk(start, 0)
    return found


def repo_info(repo, emails, run=subprocess.run):
    info = {"path": repo, "first_commit": None, "last_commit": None,
            "commits": 0, "own_commits": None}
    try:
        out = run(["git", "-C", repo, "log", "--format=%ad|%ae", "--date=short"],
                  capture_output=True, text=True, timeout=60, encoding="utf-8",
                  errors="replace")
    except Exception:
        return info
    if out.returncode != 0:
        return info
    days, own = [], 0
    for line in out.stdout.splitlines():
        day, _, email = line.partition("|")
        days.append(day)
        if email.strip().lower() in emails:
            own += 1
    if days:
        info.update(first_commit=min(days), last_commit=max(days), commits=len(days),
                    own_commits=own if emails else None)
    return info


def run(env=None, records=None, cfg=None, scan=True):
    cfg = cfg or config.load(env=env)
    user_rules = rules_mod.load(env=env)
    records = records if records is not None else []
    ctx = rules_mod.Context(user_rules, roots=cfg.get("project_roots"), env=env,
                            known_roots=attribution.known_roots(records))
    issues = []

    # Repositories: the ones sessions worked in, plus a shallow scan.
    worked_in = set(attribution.known_roots(records).values())
    project_usd = {}
    for r in records:
        for name, share in attribution.session_shares(r, ctx).items():
            project_usd[name] = project_usd.get(name, 0.0) + (r.get("usd") or 0) * share
    repos = sorted(worked_in | set(scan_repos() if scan else []))
    emails = set(e.lower() for e in cfg.get("git_author_emails") or [])
    try:
        out = subprocess.run(["git", "config", "--global", "user.email"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            emails.add(out.stdout.strip().lower())
    except Exception:
        pass
    if not emails:
        issues.append("no_git_email")

    repo_list = []
    for repo in repos:
        if not backfill.is_main_repo(repo):
            continue
        name, rank = ctx.classify(repo)
        info = repo_info(repo, emails)
        info["project"] = name if rank == "project" else None
        info["api_usd"] = round(project_usd.get(name or "", 0.0), 2)
        repo_list.append(info)

    # Working directories that ended up unassigned.
    unassigned = {}
    cutoff = datetime.now(timezone.utc).astimezone().date() - timedelta(days=30)
    total_30 = unassigned_30 = 0.0
    for r in records:
        day = attribution.day_of(r.get("start_ms"))
        shares = attribution.session_shares(r, ctx)
        usd = r.get("usd") or 0
        if day and day >= cutoff:
            total_30 += usd
            unassigned_30 += usd * shares.get(attribution.UNASSIGNED, 0.0)
        if attribution.UNASSIGNED in shares:
            for cwd in (r.get("cwd") or {}):
                unassigned[cwd] = unassigned.get(cwd, 0.0) + usd * shares[attribution.UNASSIGNED]
    top_unassigned = sorted(unassigned.items(), key=lambda kv: -kv[1])[:15]
    share_30 = round(unassigned_30 / total_30, 3) if total_30 else None
    if share_30 and share_30 > 0.1:
        issues.append("high_unassigned")

    invoices, currency = inv.load(env=env)
    subs = [d for d, _, _ in inv.ordered(invoices)]
    gaps = [(a.isoformat(), b.isoformat()) for a, b in zip(subs, subs[1:])
            if (b - a).days > 35]
    if not invoices:
        issues.append("no_invoices")
    elif not currency:
        issues.append("no_currency")
    if gaps:
        issues.append("invoice_gaps")

    days = cleanup_days(env)
    if days is None or days < 90:
        issues.append("short_log_retention")

    plan = sources.plan_from_cache(cache.read(cache.default_path(env), cache.MAX_AGE) or {})
    if not plan:
        plan = sources.read_plan()

    return {
        "logs": logs_info(env),
        "archive": {"sessions": len(records),
                    "without_cost_line": sum(1 for r in records if r.get("estimated")),
                    "from": min((attribution.day_of(r.get("start_ms")) for r in records
                                 if attribution.day_of(r.get("start_ms"))), default=None),
                    "path": str(paths.data_file("cost-archive.jsonl", env))},
        "history_first_prompt": history_first(env),
        "cleanup_period_days": days,
        "plan": {"name": plan[0], "tier": plan[1]} if plan and plan[0] else None,
        "git_author_emails": sorted(emails),
        "repos": repo_list,
        "unassigned_last_30_days": share_30,
        "unassigned_top_dirs": [{"dir": d, "usd": round(v, 2)} for d, v in top_unassigned],
        "rules": {"path": str(rules_mod.default_path(env)), "user_rules": user_rules},
        "project_roots": cfg.get("project_roots"),
        "invoices": {"path": str(inv.default_path(env)), "count": len(invoices),
                     "currency": currency,
                     "first": subs[0].isoformat() if subs else None,
                     "last": subs[-1].isoformat() if subs else None,
                     "plans": sorted({e.get("plan") for e in invoices if e.get("plan")}),
                     "gaps": gaps},
        "other_machines": len(other_machines.read()),
        "issues": issues,
    }


def as_json(data):
    def default(o):
        return o.isoformat() if hasattr(o, "isoformat") else str(o)
    return json.dumps(data, indent=2, ensure_ascii=False, default=default)
