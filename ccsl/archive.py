"""Condense Claude Code's logs into a lasting archive.

Claude Code deletes its logs after 30 days by default. Whoever wants to look
at costs over longer stretches has to condense them first. One session
becomes one line; a gigabyte of logs becomes a few hundred kilobytes.

What gets stored are the RAW SIGNALS of the attribution, never its result:
how much output went to which working directory and which touched path.
Project rules change, and only this way can the attribution be recomputed
long after the logs are gone.

Costs are read per PROCESS, not per file. Claude Code writes a cost line
with the counter of the process whenever a process ends. Several processes
often write into one session file (a second window, a resume), and one
process can write into two files when work continues under a new id after a
full context. The last cost line of a file is therefore not the session's
total; read naively, real data lost 278 $ and counted 365 $ twice.
"""

import json
from datetime import datetime
from pathlib import Path

from . import locks, paths
from . import rules as rules_mod
from .rules import is_temp, normalize
from .session_project import COMMAND_FIELD, PATH_FIELD, paths_in_command, unescape

# How deep a path is kept. Only WHERE a file lives matters for attribution,
# never its name; the git root is stored separately, so deep repositories
# are covered either way.
PATH_DEPTH = 8
COMMAND_DEPTH = 6

# Weights of the token kinds, after Anthropic's published ratios: output
# costs five times the input, cache reads a tenth, cache writes one and a
# quarter.
#
# Thinking tokens are deliberately absent: they are already part of the
# output tokens.
#
# Only needed when a session has no cost line. Claude Code writes it when a
# process ends; an aborted session would otherwise lose its cost entirely.
WEIGHTS = {"in": 1.0, "out": 5.0, "cache_read": 0.1, "cache_write": 1.25}

AVERAGE = "*"

# Fields of the cost line per model and their name in the archive
MODEL_FIELDS = (("usd", "costUSD"), ("in", "inputTokens"), ("out", "outputTokens"),
                ("thinking", "thinkingTokens"), ("cache_read", "cacheReadInputTokens"),
                ("cache_write", "cacheCreationInputTokens"))


def weighted_tokens(values):
    """Tokens brought to one common measure."""
    return sum((values.get(field) or 0) * w for field, w in WEIGHTS.items())


def archive_path(env=None):
    return paths.data_file("cost-archive.jsonl", env)


def state_path(env=None):
    return paths.data_file("collect-state.json", env)


def _is_absolute(p):
    return p.startswith("/") or (len(p) > 2 and p[1] == ":" and p[2] == "/")


def _split(p):
    """(anchor, parts): '/a/b' -> ('/', [a, b]); 'C:/a' -> ('C:/', [a])."""
    if len(p) > 2 and p[1] == ":":
        return p[:3], [x for x in p[3:].split("/") if x]
    return "/", [x for x in p.split("/") if x]


def shorten_file(path):
    anchor, parts = _split(path)
    parts = parts[:-1]                      # the file name goes
    return anchor + "/".join(parts[:PATH_DEPTH]) if parts else ""


def shorten_command_path(path):
    anchor, parts = _split(path)
    if len(parts) > 1 and "." in parts[-1]:
        parts = parts[:-1]
    parts = parts[:COMMAND_DEPTH]
    return anchor + "/".join(parts) if parts else ""


def _time_ms(text):
    if not isinstance(text, str):
        return None
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000)
    except (ValueError, OverflowError, OSError):
        return None


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _remember_process(processes, line):
    """Keep, per process, the cost line with the highest counter.

    A process is recognised by its start time. A resumed process takes over
    start time and counter of its predecessor and counts on from there, so
    within one process the highest counter is the right one.
    """
    usd = line.get("totalCostUSD")
    if not _num(usd):
        return
    key = str(line.get("startTime") or 0)
    before = processes.get(key)
    if before is None or usd >= before["totalCostUSD"]:
        processes[key] = line


def _sum_models(lines):
    models = {}
    for line in lines:
        for name, values in (line.get("modelUsage") or {}).items():
            if not isinstance(values, dict):
                continue
            entry = models.setdefault(name, {f: 0 for f, _ in MODEL_FIELDS})
            for field, source in MODEL_FIELDS:
                value = values.get(source)
                if _num(value):
                    entry[field] += value
    return models


def _total(lines, field):
    values = [x.get(field) for x in lines if _num(x.get(field))]
    return sum(values) if values else None


class Signals:
    """Collects where a session's output went, filtered and shortened."""

    def __init__(self, ctx=None, temps=None):
        self.ctx = ctx
        self.temps = temps or rules_mod.temp_dirs()
        self.home = normalize(str(paths.home()))
        self.cwd, self.paths, self.commands = {}, {}, {}
        self.roots = {}

    def _note_root(self, p):
        if self.ctx is None or p in self.roots:
            return
        root = self.ctx.git_root(p)
        self.roots[p] = root

    def add_cwd(self, cwd, weight):
        p = normalize(cwd)
        if not p or is_temp(p, self.temps):
            return
        self.cwd[p] = self.cwd.get(p, 0) + weight
        self._note_root(p)

    def add_file(self, path, weight):
        p = normalize(path)
        if not p or not _is_absolute(p) or is_temp(p, self.temps):
            return
        short = shorten_file(p)
        if short:
            self.paths[short] = self.paths.get(short, 0) + weight
            self._note_root(short)

    def add_command(self, command, weight):
        for raw in paths_in_command(command):
            p = normalize(raw)
            if not _is_absolute(p) or is_temp(p, self.temps):
                continue
            short = shorten_command_path(p)
            if not short:
                continue
            # Commands mention plenty of system paths (/usr/bin/env, /etc/...).
            # Keep what can say something about a project: inside the home
            # folder, inside a repository, or covered by a rule or root.
            keep = short == self.home or short.startswith(self.home + "/")
            if not keep and self.ctx is not None:
                keep = bool(self.ctx.git_root(short)) or \
                    self.ctx.classify(short)[1] != "neutral"
            if keep:
                self.commands[short] = self.commands.get(short, 0) + weight
                self._note_root(short)

    def git_roots(self):
        return {p: r for p, r in self.roots.items() if r}


def read_session(file, ctx=None):
    """Condense one session file. None if it has neither cost nor tokens."""
    processes = {}
    session_id = None
    first_ms = None
    signals = Signals(ctx)
    tokens = {}
    # One API answer produces several log lines, and each carries the WHOLE
    # usage of that request. Without this set the same tokens count several
    # times; on real data that was a factor of 2.5.
    counted_requests = set()

    with Path(file).open(encoding="utf-8", errors="replace") as f:
        for line in f:
            record = None
            if "cost-state" in line:
                # The word alone is not enough: a session talking about the
                # tracker mentions it in ordinary messages.
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict) and record.get("type") == "cost-state":
                    _remember_process(processes, record)
                    session_id = session_id or record.get("sessionId")
                    continue
            # A rough pre-filter so not every line gets parsed. It may only
            # sieve out; the parsed object decides below.
            if "assistant" not in line:
                continue
            if record is None:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
            if not isinstance(record, dict) or record.get("type") != "assistant":
                continue
            if first_ms is None:
                first_ms = _time_ms(record.get("timestamp"))
            message = record.get("message") or {}
            usage = message.get("usage") or {}
            out = usage.get("output_tokens") or 0

            request = record.get("requestId")
            already = bool(request) and request in counted_requests
            if request:
                counted_requests.add(request)

            model = message.get("model")
            if model and usage and not already:
                entry = tokens.setdefault(model, {})
                for field, source in (("in", "input_tokens"), ("out", "output_tokens"),
                                      ("cache_read", "cache_read_input_tokens"),
                                      ("cache_write", "cache_creation_input_tokens")):
                    entry[field] = (entry.get(field) or 0) + (usage.get(source) or 0)

            if not out:
                continue
            if record.get("cwd"):
                signals.add_cwd(record["cwd"], out)
            for raw in PATH_FIELD.findall(line):
                signals.add_file(unescape(raw), out)
            # Where the shell worked. For sessions that do everything through
            # commands this is often the only signal.
            for command in COMMAND_FIELD.findall(line):
                signals.add_command(unescape(command), out)

    measured = bool(processes)
    if not measured and not tokens:
        return None

    lines = list(processes.values())
    if measured:
        models = _sum_models(lines)
        usd = sum(x["totalCostUSD"] for x in lines)
        starts = [x.get("startTime") for x in lines if _num(x.get("startTime"))]
        begin = first_ms or (min(starts) if starts else None)
    else:
        # Without a cost line only the counted tokens remain.
        models = {name: dict(values, usd=None) for name, values in tokens.items()}
        usd = None
        begin = first_ms

    file = Path(file)
    return {
        "session": session_id or file.stem,
        "folder": file.parent.name,
        # Start of the work, not of the process: a resumed process takes over
        # the start time of its predecessor but only works from its first
        # answer on.
        "start_ms": begin or int(file.stat().st_mtime * 1000),
        "first_ms": first_ms,
        "usd": usd,
        "estimated": not measured,
        "processes": {k: x["totalCostUSD"] for k, x in processes.items()},
        "duration_ms": _total(lines, "totalDuration"),
        "api_ms": _total(lines, "totalAPIDuration"),
        "lines_added": _total(lines, "totalLinesAdded"),
        "lines_removed": _total(lines, "totalLinesRemoved"),
        "models": models,
        "cwd": signals.cwd,
        "paths": signals.paths,
        "commands": signals.commands,
        "git_roots": signals.git_roots(),
    }


def settle_processes(records):
    """A process that wrote into several sessions counts only once.

    When work continues under a new id after a full context, the process
    takes its counter along. The earlier session keeps its amount, every
    later one only gets the increase. The sum across sessions is then
    exactly the process's highest counter.

    Always computed from the stored raw values, so it can be repeated at
    will. Returns the number of sessions whose amount changed.
    """
    per_process = {}
    for record in records or []:
        if not isinstance(record, dict) or record.get("estimated"):
            continue
        procs = record.get("processes")
        if not isinstance(procs, dict) or not procs:
            continue
        for key, value in procs.items():
            if _num(value):
                per_process.setdefault(key, []).append(record)

    shares = {}
    for key, group in per_process.items():
        group.sort(key=lambda r: r.get("first_ms") or r.get("start_ms") or 0)
        highest = 0.0
        for record in group:
            value = record["processes"][key]
            shares[id(record)] = shares.get(id(record), 0.0) + max(0.0, value - highest)
            highest = max(highest, value)

    changed = 0
    for record in records or []:
        if isinstance(record, dict) and id(record) in shares:
            new = round(shares[id(record)], 6)
            if record.get("usd") != new:
                record["usd"] = new
                changed += 1
    return changed


def derive_prices(records):
    """Price per weighted token, from the measured sessions.

    No external price table: sessions with a cost line carry tokens AND cost
    per model, the price follows from them. That cannot go stale and covers
    models no table knows yet.
    """
    sums = {}
    for record in records or []:
        if record.get("estimated"):
            continue
        for model, values in (record.get("models") or {}).items():
            if not isinstance(values, dict) or not _num(values.get("usd")):
                continue
            entry = sums.setdefault(model, {"usd": 0.0, "tokens": 0.0})
            entry["usd"] += values["usd"]
            entry["tokens"] += weighted_tokens(values)

    prices = {}
    total_usd = total_tokens = 0.0
    for model, entry in sums.items():
        if entry["tokens"] > 0 and entry["usd"] > 0:
            prices[model] = entry["usd"] / entry["tokens"]
            total_usd += entry["usd"]
            total_tokens += entry["tokens"]
    if total_tokens > 0:
        prices[AVERAGE] = total_usd / total_tokens
    return prices


def recompute(records, prices):
    """Compute the cost of sessions without a cost line from their tokens.

    Every time, not only the new ones: the prices come from the archive
    itself and get more precise with every measured session.
    """
    if not prices:
        return 0
    done = 0
    for record in records or []:
        if not record.get("estimated"):
            continue
        total = 0.0
        for model, values in (record.get("models") or {}).items():
            price = prices.get(model) or prices.get(AVERAGE)
            if price:
                total += weighted_tokens(values) * price
        if total > 0:
            record["usd"] = round(total, 6)
            done += 1
    return done


def _token_mass(record):
    return sum(weighted_tokens(v) for v in (record.get("models") or {}).values()
               if isinstance(v, dict))


def should_replace(old, new):
    """True if the freshly read state should replace the archived one.

    Origin comes first: a measured number always replaces an estimated one,
    never the other way round. Among measured ones the file wins, a log does
    not lose lines. Among estimated ones the token mass decides, because the
    archived record already carries dollars and the fresh one does not yet.
    """
    old_est, new_est = bool(old.get("estimated")), bool(new.get("estimated"))
    if old_est != new_est:
        return old_est
    if not new_est:
        return new.get("processes") != old.get("processes")
    return _token_mass(new) > _token_mass(old)


def read(path=None):
    """All archived sessions, oldest first."""
    path = Path(path) if path else archive_path()
    records = []
    if not path.exists():
        return records
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict) and record.get("session"):
                records.append(record)
    return records


def _read_state(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def collect(source=None, target=None, ctx=None, state=None, full=False):
    """Add new or changed sessions to the archive.

    Files that did not change since the last run are skipped. Sessions whose
    log is already deleted stay as they are: the archive is then their only
    source.
    """
    source = Path(source) if source else paths.logs_dir()
    target = Path(target) if target else archive_path()
    state_file = Path(state) if state else target.with_name("collect-state.json")

    handle = locks.acquire(target.with_name(target.name + ".lock"))
    if handle is None:
        return {"new": 0, "replaced": 0, "recomputed": 0, "skipped": 0,
                "total": None, "busy": True}
    try:
        known = {r["session"]: r for r in read(target)}
        before = json.dumps(known, sort_keys=True)
        seen = {} if full else _read_state(state_file)
        now_seen = {}

        new = replaced = skipped = 0
        folders = sorted(source.iterdir()) if source.exists() else []
        for folder in folders:
            if not folder.is_dir():
                continue
            for file in sorted(folder.glob("*.jsonl")):
                try:
                    st = file.stat()
                except OSError:
                    continue
                mark = [int(st.st_mtime), st.st_size]
                now_seen[str(file)] = mark
                if seen.get(str(file)) == mark:
                    continue
                try:
                    record = read_session(file, ctx)
                except Exception:
                    skipped += 1
                    continue
                if record is None:
                    skipped += 1
                    continue
                old = known.get(record["session"])
                if old is not None:
                    if not should_replace(old, record):
                        continue
                    replaced += 1
                else:
                    new += 1
                known[record["session"]] = record

        # Only once every file is read can processes that wrote into several
        # sessions be recognised. Then sessions without a cost line get their
        # cost from the measured prices.
        records = list(known.values())
        settle_processes(records)
        recomputed = recompute(records, derive_prices(records))

        if json.dumps(known, sort_keys=True) != before:
            lines = "".join(json.dumps(r, ensure_ascii=False) + "\n"
                            for r in sorted(records, key=lambda r: r.get("start_ms") or 0))
            paths.write_atomic(target, lines)
        try:
            paths.write_atomic(state_file, json.dumps(now_seen))
        except OSError:
            pass
        return {"new": new, "replaced": replaced, "recomputed": recomputed,
                "skipped": skipped, "total": len(known), "busy": False}
    finally:
        locks.release(handle)


def logs_without_cost_lines(source=None, days=7, now=None):
    """(log files touched in the last days, of those with a cost line).

    Claude Code's log format is undocumented. If it changes, the tracker
    would quietly measure nothing; this is what the self-check looks at.
    """
    import time
    source = Path(source) if source else paths.logs_dir()
    now = now or time.time()
    recent = with_cost = 0
    if not source.exists():
        return 0, 0
    for folder in source.iterdir():
        if not folder.is_dir():
            continue
        for file in folder.glob("*.jsonl"):
            try:
                if now - file.stat().st_mtime > days * 86400:
                    continue
            except OSError:
                continue
            recent += 1
            try:
                with file.open(encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if "cost-state" in line:
                            with_cost += 1
                            break
            except OSError:
                continue
    return recent, with_cost
