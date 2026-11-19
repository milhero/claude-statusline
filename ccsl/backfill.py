"""The time before the archive: an estimate from the git history.

Before the archive there is no cost data, but there is the git history:
changed lines (or commits) per day and project. The rate per line comes from
the measured time of the same project; projects without a measurement of
their own get the average.

Only the user's own commits count. In a team repository the colleagues'
work is not the user's Claude Code usage.

The result is computed once and then FROZEN. Recalibrated every night, the
total would wander with every new measurement, even downwards, although
nothing about the past changed. It is recomputed only on request
(claude-costs --refreeze), for example after the project rules changed.
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import attribution, daily_rates, invoices as inv, paths, rules as rules_mod

AVERAGE = "*"
TIME_LIMIT = 120

# Generated and vendored files say nothing about effort: a lock file with
# 5000 lines comes from a single command.
IGNORED = (
    "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "poetry.lock", "uv.lock",
    "Cargo.lock", "composer.lock", "go.sum", "Gemfile.lock", "bun.lockb",
    "node_modules/", "/dist/", "/build/", "/vendor/", "/.next/", "/target/",
    ".min.js", ".min.css", ".map", ".svg", ".lock",
)

# From this many changed lines in ONE file and ONE commit the change counts
# as generated. Nobody writes that much by hand, Claude neither in one go.
# Found on a tokenizer with 86,166 lines and a text corpus with 23,449.
GENERATED_FROM = 20000


def frozen_path(env=None):
    return paths.data_file("backfill.json", env)


def is_main_repo(path):
    """True only for a repository of its own, not for a worktree.

    In a worktree .git is a file pointing to the main repository. Counting
    worktrees would count the shared history several times.
    """
    return os.path.isdir(os.path.join(str(path), ".git"))


def author_emails(repo, extra=None, run=subprocess.run):
    """The user's own addresses: configured list plus git's user.email."""
    found = [e.strip().lower() for e in (extra or []) if isinstance(e, str) and e.strip()]
    for args in (["git", "config", "--global", "user.email"],
                 ["git", "-C", str(repo), "config", "user.email"]):
        try:
            out = run(args, capture_output=True, text=True, timeout=10)
        except Exception:
            continue
        email = (out.stdout or "").strip().lower()
        if out.returncode == 0 and email and email not in found:
            found.append(email)
    return found


def _author_args(emails):
    # Several --author options are OR-ed by git. The address inside <...> is
    # matched literally and regardless of case: Jane.Doe@Example.com in the
    # history is the same person as jane.doe@example.com in the config.
    if not emails:
        return []
    return ["--fixed-strings", "--regexp-ignore-case"] + \
        ["--author=<{}>".format(e) for e in emails]


def lines_per_day(repo, emails=None, since=None, until=None, run=subprocess.run):
    """Changed lines per day, generated files excluded."""
    cmd = ["git", "-C", str(repo), "log", "--numstat", "--format=%x00%ad", "--date=short"]
    cmd += _author_args(emails or [])
    if since:
        cmd.append("--since={}".format(since))
    if until:
        cmd.append("--until={}".format(until))
    try:
        out = run(cmd, capture_output=True, text=True, timeout=TIME_LIMIT,
                  encoding="utf-8", errors="replace")
    except Exception:
        return {}
    if out.returncode != 0:
        return {}

    counts = {}
    day = None
    for line in out.stdout.splitlines():
        if line.startswith("\x00"):
            day = inv.as_date(line[1:])
            continue
        if day is None or line.count("\t") != 2:
            continue
        added, removed, name = line.split("\t")
        if any(skip in name for skip in IGNORED):
            continue
        try:
            # Binary files show up as "-" and do not count.
            n = int(added) + int(removed)
        except ValueError:
            continue
        if n and n < GENERATED_FROM:
            counts[day] = counts.get(day, 0) + n
    return counts


def commits_per_day(repo, emails=None, since=None, until=None, run=subprocess.run):
    cmd = ["git", "-C", str(repo), "log", "--format=%ad", "--date=short"]
    cmd += _author_args(emails or [])
    if since:
        cmd.append("--since={}".format(since))
    if until:
        cmd.append("--until={}".format(until))
    try:
        out = run(cmd, capture_output=True, text=True, timeout=TIME_LIMIT)
    except Exception:
        return {}
    if out.returncode != 0:
        return {}
    counts = {}
    for line in out.stdout.split():
        day = inv.as_date(line)
        if day:
            counts[day] = counts.get(day, 0) + 1
    return counts


def project_repos(ctx, records, user_rules):
    """{project: repository} from the rules and from the archive's git roots."""
    found = dict(rules_mod.git_repos_from_rules(user_rules))
    for root in sorted(set(attribution.known_roots(records).values())):
        if not is_main_repo(root):
            continue
        name, rank = ctx.classify(root)
        if rank == "project" and name and name not in found:
            found[name] = root
    return found


def rate_per_unit(usd_per_project, units_per_project):
    """Cost per line (or commit), from the measured time.

    One rate per project, because projects differ a lot. The average only
    takes projects that have BOTH cost and lines. Cost without lines (note
    taking, say) has no place in a rate per line: in the numerator without a
    counterpart in the denominator it lifted the average above every single
    project's rate.
    """
    rates = {}
    total_usd = total_units = 0.0
    for name, usd in (usd_per_project or {}).items():
        n = (units_per_project or {}).get(name) or 0
        if n > 0 and usd > 0:
            rates[name] = usd / n
            total_usd += usd
            total_units += n
    if total_units > 0:
        rates[AVERAGE] = total_usd / total_units
    return rates


def daily_values(units_per_project_and_day, rates, until, since=None):
    """Estimated daily values for the time before the archive.

    Same shape as the measured daily values, so the subscription fee of the
    backfill days spreads exactly as precisely.
    """
    per_day = {}
    for project, days in (units_per_project_and_day or {}).items():
        rate = rates.get(project) or rates.get(AVERAGE)
        if not rate:
            continue
        for day, n in (days or {}).items():
            if (until and day >= until) or (since and day < since):
                continue
            per_day.setdefault(day, {})
            per_day[day][project] = per_day[day].get(project, 0.0) + n * rate
    return per_day


def first_use(invoices, history_file=None):
    """The earliest day Claude Code was demonstrably in use.

    Earliest subscription invoice or earliest prompt in history.jsonl.
    Nothing before can have been Claude Code work, however far back the git
    history goes.
    """
    candidates = [day for day, _, _ in inv.ordered(invoices)]
    target = Path(history_file) if history_file else paths.claude_dir() / "history.jsonl"
    try:
        with target.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    stamp = json.loads(line).get("timestamp")
                except (ValueError, AttributeError):
                    continue
                if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
                    try:
                        candidates.append(datetime.fromtimestamp(
                            stamp / 1000, tz=timezone.utc).astimezone().date())
                    except (OverflowError, OSError, ValueError):
                        continue
    except OSError:
        pass
    return min(candidates) if candidates else None


def compute(records, ctx, user_rules, archive_start, invoices, rates, cfg,
            history_file=None, counter=None):
    """Estimated, capped daily values for the time before the archive."""
    meta = {"until": archive_start.isoformat() if archive_start else None}
    repos = project_repos(ctx, records, user_rules)
    if not repos or not archive_start:
        return {}, meta

    measure = cfg.get("backfill_measure", "lines")
    count = counter or (lines_per_day if measure == "lines" else commits_per_day)
    extra = cfg.get("git_author_emails") or []
    begin = first_use(invoices, history_file)
    units, own_only = {}, {}
    for name, repo in repos.items():
        emails = author_emails(repo, extra)
        own_only[name] = bool(emails)
        # Nothing before the first use of Claude Code can count; reading the
        # whole history of a large repository would only cost time.
        units[name] = count(repo, emails, since=begin.isoformat() if begin else None)

    measured = attribution.evaluate(records, ctx, [])
    usd_per_project = {p["name"]: p["api_usd"] for p in measured["projects"]}
    units_measured = {name: sum(n for day, n in days.items() if day >= archive_start)
                      for name, days in units.items()}
    rates_per_unit = rate_per_unit(usd_per_project, units_measured)

    per_day = daily_values(units, rates_per_unit, until=archive_start, since=begin)
    capped = {}
    for day, shares in per_day.items():
        cap = daily_rates.cap_for(day, invoices, rates)
        shares = daily_rates.apply_cap(shares, cap) if cap is not None else shares
        values = {n: v for n, v in shares.items() if v > 0}
        if values:
            capped[day] = values

    plans = {e.get("plan") for e in invoices or []}
    meta.update({
        "since": begin.isoformat() if begin else None,
        "measure": measure,
        "rates_per_unit": {n: round(r, 6) for n, r in rates_per_unit.items()},
        "daily_caps": {n: round(r, 2) for n, r in daily_rates.derive(rates).items()
                       if n in plans},
        "uncapped_usd": round(sum(sum(s.values()) for s in per_day.values()), 2),
        "own_commits_only": sorted(n for n, own in own_only.items() if own),
        "repos": {n: str(r) for n, r in repos.items()},
    })
    return capped, meta


def save_frozen(path, per_day, meta):
    content = dict(meta or {})
    content["days"] = {day.isoformat(): {n: round(v, 6) for n, v in shares.items()}
                       for day, shares in sorted((per_day or {}).items())}
    paths.write_atomic(path, json.dumps(content, indent=1, ensure_ascii=False) + "\n")


def load_frozen(path):
    """(daily values, meta), or (None, None)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None, None
    if not isinstance(data, dict) or not isinstance(data.get("days"), dict):
        return None, None
    days = {}
    for text, shares in data["days"].items():
        day = inv.as_date(text)
        if day is None or not isinstance(shares, dict):
            continue
        days[day] = {n: float(v) for n, v in shares.items()
                     if isinstance(v, (int, float)) and not isinstance(v, bool)}
    meta = {k: v for k, v in data.items() if k != "days"}
    return days, meta


# The rate per line comes from the measured time. With only a day or two
# measured, one unusual day would shape the past for good; until there is a
# week of measurements the estimate stays provisional and is recomputed.
MIN_MEASURED_DAYS = 7


def measured_days(records):
    return len({attribution.day_of(r.get("start_ms")) for r in records or []
                if not r.get("estimated") and attribution.day_of(r.get("start_ms"))})


def get(records, ctx, user_rules, archive_start, invoices, rates, cfg, path=None,
        refreeze=False, compute_fn=None, min_days=MIN_MEASURED_DAYS):
    """The frozen backfill, computed the first time there is enough to go on.

    Once written it stays: new measurements no longer change the past.
    """
    target = Path(path) if path else frozen_path()
    if not refreeze:
        days, meta = load_frozen(target)
        if days is not None:
            return days, meta
    fn = compute_fn or compute
    days, meta = fn(records, ctx, user_rules, archive_start, invoices, rates, cfg)
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    if measured_days(records) < min_days:
        return days, dict(meta, provisional=True, created=now)
    meta = dict(meta, created=now)
    try:
        save_frozen(target, days, meta)
    except OSError:
        pass
    return days, meta


def archive_start(records):
    days = [attribution.day_of(r.get("start_ms")) for r in records or []]
    days = [d for d in days if d]
    return min(days) if days else None


