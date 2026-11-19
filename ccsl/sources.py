"""The data sources.

A  Claude Code's own input: documented, instant, no network.
B  Two undocumented account endpoints, read only by a detached background
   process and always through the cache: the model-scoped weekly limit and
   the plan.
C  The local credentials: the plan as a fallback, and the token for B.

Every function here catches its own errors. If a source fails, exactly its
values are missing and everything else stays visible.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from . import i18n, paths
from .model import Gauge, Status

VERSION = "1.0.1"

# rate_limit_tier as Claude Code and the API name it -> (display, tier).
# It only says how big a Max plan is. The plan itself comes from the
# subscription type, just as in Claude Code.
TIERS = {
    "default_claude_max_20x": ("Max 20x", "max_20x"),
    "default_claude_max_5x": ("Max 5x", "max_5x"),
    "default_claude_pro": ("Pro", "pro"),
    "default_claude_team": ("Team", "team"),
}

# Tiers several plans share. Pro accounts report default_claude_ai, so the
# tier alone must not name the plan ("ai").
GENERIC_TIERS = ("default_claude_ai",)

# subscriptionType in the credentials, organization_type ("claude_pro") in
# the server's profile -> (display, tier). Max and Enterprise keep the tier
# open: the size of a Max plan is only known from the rate limit tier.
SUBSCRIPTIONS = {
    "pro": ("Pro", "pro"),
    "max": ("Max", "unknown"),
    "team": ("Team", "team"),
    "enterprise": ("Enterprise", "unknown"),
    "free": ("Free", "unknown"),
}

# Plan names that decide the tier on their own. Ultra currently shares its
# rate limit tier with Max 20x, so the name is the only thing telling them
# apart.
NAMED_TIERS = (("ultra", "ultra"),)


def _number(value):
    """A number or None. Booleans are refused: True would pass as 1.0."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _from_epoch(value):
    n = _number(value)
    if n is None:
        return None
    try:
        return datetime.fromtimestamp(n, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _from_iso(value):
    if not isinstance(value, str):
        return None
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when


def _window(data, key, gauge_key, label):
    """A gauge from one rate_limits window, or None."""
    if not isinstance(data, dict):
        return None
    raw = data.get(key)
    if not isinstance(raw, dict):
        return None
    pct = _number(raw.get("used_percentage"))
    if pct is None:
        return None
    return Gauge(gauge_key, label, pct, _from_epoch(raw.get("resets_at")))


def shorten_directory(path):
    if not isinstance(path, str) or not path:
        return None
    home = str(paths.home())
    if path == home:
        return "~"
    if path.startswith(home + "/") or path.startswith(home + "\\"):
        return "~/" + path[len(home) + 1:].replace("\\", "/")
    return path


def git_branch(directory, limit=40):
    """The checked-out branch of the repository a folder lives in, or None.

    Read from .git/HEAD instead of running git: this happens on every redraw.
    A worktree's .git is a file pointing to its own HEAD. A detached HEAD
    shows as a short commit id.
    """
    if not isinstance(directory, str) or not directory:
        return None
    current = os.path.abspath(directory)
    for _ in range(limit):
        dotgit = os.path.join(current, ".git")
        try:
            if os.path.isdir(dotgit):
                head = os.path.join(dotgit, "HEAD")
                break
            if os.path.isfile(dotgit):
                with open(dotgit, encoding="utf-8", errors="replace") as f:
                    pointer = f.read().strip()
                if not pointer.startswith("gitdir:"):
                    return None
                gitdir = pointer[len("gitdir:"):].strip()
                if not os.path.isabs(gitdir):
                    gitdir = os.path.join(current, gitdir)
                head = os.path.join(gitdir, "HEAD")
                break
        except OSError:
            return None
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
    else:
        return None
    try:
        with open(head, encoding="utf-8", errors="replace") as f:
            text = f.read().strip()
    except OSError:
        return None
    if text.startswith("ref:"):
        ref = text[4:].strip()
        return ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
    return text[:7] or None


def from_stdin(data, lang="en"):
    """Source A. Survives any missing field and any wrong type."""
    s = Status()
    if not isinstance(data, dict):
        return s

    limits = data.get("rate_limits")
    s.week = _window(limits, "seven_day", "week", i18n.t("week", lang))
    s.five_hour = _window(limits, "five_hour", "five_hour", i18n.t("five_hour", lang))

    window = data.get("context_window")
    if isinstance(window, dict):
        pct = _number(window.get("used_percentage"))
        if pct is not None:
            s.context = Gauge("context", i18n.t("context", lang), pct)
        size = _number(window.get("context_window_size"))
        if size is not None:
            s.context_size = int(size)

    model = data.get("model")
    if isinstance(model, dict):
        name = model.get("display_name")
        s.model = name if isinstance(name, str) and name else None

    workspace = data.get("workspace")
    if isinstance(workspace, dict):
        s.directory = shorten_directory(workspace.get("current_dir"))
        # workspace.git_worktree only names a linked worktree; the branch
        # itself comes from the repository.
        s.branch = git_branch(workspace.get("current_dir"))

    cost = data.get("cost")
    if isinstance(cost, dict):
        s.cost_usd = _number(cost.get("total_cost_usd"))

    effort = data.get("effort")
    if isinstance(effort, dict):
        level = effort.get("level")
        s.effort = level if isinstance(level, str) and level else None

    version = data.get("version")
    s.cc_version = version if isinstance(version, str) else None
    return s


# --- Credentials -----------------------------------------------------------

KEYCHAIN_SERVICE = "Claude Code-credentials"


def _oauth_block(data):
    block = data.get("claudeAiOauth") if isinstance(data, dict) else None
    return block if isinstance(block, dict) else {}


def _keychain(timeout=3):
    """On macOS Claude Code keeps its login in the keychain, not in a file."""
    if sys.platform != "darwin":
        return {}
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=timeout)
    except Exception:
        return {}
    if out.returncode != 0 or not out.stdout.strip():
        return {}
    try:
        return _oauth_block(json.loads(out.stdout.strip()))
    except ValueError:
        return {}


def _oauth(path=None, keychain=True):
    """The OAuth block of the credentials. A failure is not an error."""
    path = path or paths.credentials_file()
    try:
        block = _oauth_block(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        block = {}
    if not block and keychain:
        block = _keychain()
    return block


def credentials_source(path=None):
    """Where the login was found: 'file', 'keychain' or None (for --diagnose)."""
    path = path or paths.credentials_file()
    try:
        if _oauth_block(json.loads(path.read_text(encoding="utf-8"))):
            return "file"
    except Exception:
        pass
    return "keychain" if _keychain() else None


def _subscription(kind):
    """'pro' from 'pro' or 'claude_pro', None for anything else."""
    if not isinstance(kind, str):
        return None
    clean = kind.strip().lower()
    if clean.startswith("claude_"):
        clean = clean[len("claude_"):]
    return clean or None


def tier_from_name(name, tier_id, kind=None):
    """(display, tier) from a plan name, a rate limit tier and a subscription type.

    A known tier wins (it tells Max 5x from Max 20x), then the subscription
    type. An unknown id is not guessed. It is made readable and gets the
    tier "unknown", so the rendering treats it neutrally instead of ranking
    it. A generic tier is never made readable, it names no plan.
    """
    display, tier = None, None
    sub = _subscription(kind)
    if isinstance(tier_id, str) and tier_id in TIERS:
        display, tier = TIERS[tier_id]
    elif sub in SUBSCRIPTIONS:
        display, tier = SUBSCRIPTIONS[sub]
    elif isinstance(tier_id, str) and tier_id and tier_id not in GENERIC_TIERS:
        readable = tier_id.replace("default_claude_", "").replace("_", " ").strip()
        display, tier = (readable or None), "unknown"
    elif sub:
        display, tier = sub.replace("_", " ").capitalize(), "unknown"
    if isinstance(name, str) and name.strip():
        clean = name.strip()
        if clean.lower().endswith(" plan"):
            clean = clean[:-5].strip()
        if clean:
            display = clean
            for word, named in NAMED_TIERS:
                if clean.lower().startswith(word):
                    tier = named
    if display and not tier:
        tier = "unknown"
    return (display, tier) if display else (None, None)


def read_plan(path=None, keychain=False):
    """Source C. (display, tier) from the credentials, e.g. ("Max 20x", "max_20x").

    The file is only written at login and goes stale after a plan change, so
    the server's answer (plan_from_cache) wins whenever it exists.
    """
    block = _oauth(path, keychain=keychain)
    return tier_from_name(None, block.get("rateLimitTier"), block.get("subscriptionType"))


def read_token(path=None):
    """Access token for source B. Never logged, never stored."""
    token = _oauth(path).get("accessToken")
    return token if isinstance(token, str) and token else None


# --- Source B ----------------------------------------------------------------

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
PROFILE_URL = "https://api.anthropic.com/api/oauth/profile"

# These windows are kept. session and weekly_all know the server's state
# across all surfaces and are therefore fresher than Claude Code's input as
# soon as someone works elsewhere.
KEPT_WINDOWS = ("session", "weekly_all", "weekly_scoped")


def scoped_gauge(usage):
    """The model-scoped weekly window.

    Found by kind == "weekly_scoped", not by model name. The label comes from
    the answer itself, so the line stays right when another model takes the
    scoped slot.
    """
    if not isinstance(usage, dict):
        return None
    limits = usage.get("limits")
    if not isinstance(limits, list):
        return None
    for entry in limits:
        if not isinstance(entry, dict) or entry.get("kind") != "weekly_scoped":
            continue
        pct = _number(entry.get("percent"))
        if pct is None:
            continue
        label = "Model"
        scope = entry.get("scope")
        if isinstance(scope, dict) and isinstance(scope.get("model"), dict):
            name = scope["model"].get("display_name")
            if isinstance(name, str) and name:
                label = name
        return Gauge("model_week", label, pct, _from_iso(entry.get("resets_at")))
    return None


def reduce_usage(usage):
    """Keep only what is needed. What is not stored cannot leak."""
    if not isinstance(usage, dict):
        return {"limits": []}
    kept = []
    for entry in usage.get("limits", []) or []:
        if isinstance(entry, dict) and entry.get("kind") in KEPT_WINDOWS:
            kept.append({
                "kind": entry.get("kind"),
                "percent": entry.get("percent"),
                "resets_at": entry.get("resets_at"),
                "scope": entry.get("scope"),
            })
    return {"limits": kept}


def live_gauge(usage, kind, gauge_key, label):
    """One specific window from the lookup, or None."""
    if not isinstance(usage, dict):
        return None
    for entry in usage.get("limits") or []:
        if not isinstance(entry, dict) or entry.get("kind") != kind:
            continue
        pct = _number(entry.get("percent"))
        if pct is None:
            continue
        return Gauge(gauge_key, label, pct, _from_iso(entry.get("resets_at")))
    return None


# Timestamps of both sources differ by fractions of a second. Anything within
# this span counts as the same window.
WINDOW_TOLERANCE = 120


def fresher(a, b):
    """Of two readings of the same window, pick the more recent one.

    Within a window usage only rises, so the higher value is the newer one.
    After a reset it drops, and height would mislead: there the later reset
    time decides.
    """
    if a is None:
        return b
    if b is None:
        return a
    if a.resets_at is not None and b.resets_at is not None:
        gap = abs((a.resets_at - b.resets_at).total_seconds())
        if gap > WINDOW_TOLERANCE:
            return a if a.resets_at > b.resets_at else b
    return a if a.percent >= b.percent else b


def _fetch(url, token, timeout):
    import urllib.request

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "anthropic-beta": "oauth-2025-04-20",
            "Accept": "application/json",
            "User-Agent": "claude-statusline/" + VERSION,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as answer:
        return json.loads(answer.read().decode("utf-8"))


def fetch_usage(token, timeout=10):
    """The usage lookup. Only ever called from the background process."""
    return _fetch(USAGE_URL, token, timeout)


def fetch_profile(token, timeout=10):
    """The account profile. Only ever called from the background process."""
    return _fetch(PROFILE_URL, token, timeout)


def reduce_profile(profile):
    """Keep plan name, tier and subscription type, nothing personal."""
    org = profile.get("organization") if isinstance(profile, dict) else None
    if not isinstance(org, dict):
        return None
    name = org.get("plan_display_label")
    tier = org.get("rate_limit_tier")
    kind = _subscription(org.get("organization_type"))
    if not any(isinstance(v, str) and v for v in (name, tier, kind)):
        return None
    return {"name": name if isinstance(name, str) else None,
            "tier": tier if isinstance(tier, str) else None,
            "kind": kind}


def plan_from_cache(cached):
    """(display, tier) from the cache, or None. The server's name wins."""
    plan = cached.get("plan") if isinstance(cached, dict) else None
    if not isinstance(plan, dict):
        return None
    display, tier = tier_from_name(plan.get("name"), plan.get("tier"), plan.get("kind"))
    return (display, tier) if display else None
