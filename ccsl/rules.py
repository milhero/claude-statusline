"""Which project a path belongs to.

Three ranks keep side work from inflating its own bucket:

  project    counts towards the project.
  secondary  real work, but across projects (notes, agents, skills). It only
             counts when the same session touched no project at all.
  neutral    says nothing about a project and never counts.

A path is classified in this order:

  1. an explicit rule (the longest matching prefix wins),
  2. the git repository the path lives in (a worktree counts towards its
     main repository),
  3. optional project roots: every directory directly below a root is a
     project, for people who keep projects without git in one place,
  4. otherwise it stays unassigned.

That works whatever someone's folder layout looks like. Explicit rules are
there for the cases detection cannot know: a monorepo split into parts, two
repositories that are one project, a renamed folder.
"""

import json
import os
import tempfile
from pathlib import Path

from . import paths

RANKS = ("project", "secondary", "neutral")
CLAUDE_CONFIG = "Claude config"


def normalize(path):
    """One spelling for every system: forward slashes, no trailing slash,
    upper-case drive letter, ~ expanded."""
    if not path:
        return path
    text = str(path).replace("\\", "/")
    if text == "~" or text.startswith("~/"):
        text = str(paths.home()).replace("\\", "/") + text[1:]
    if len(text) >= 2 and text[1] == ":" and text[0].isalpha():
        text = text[0].upper() + text[1:]
    if len(text) > 1 and text.endswith("/") and not text.endswith(":/"):
        text = text.rstrip("/")
    return text


def _home():
    return normalize(str(paths.home()))


def temp_dirs(env=None):
    """Directories whose contents never say anything about a project."""
    env = os.environ if env is None else env
    found = ["/tmp", "/var/tmp", "/var/folders", "/private/var/folders",
             "/private/tmp", "/proc", "/sys", "/dev", "/run"]
    for candidate in (tempfile.gettempdir(), env.get("TEMP"), env.get("TMP"),
                      env.get("TMPDIR")):
        if candidate:
            found.append(normalize(candidate))
    return tuple(sorted(set(normalize(f) for f in found)))


def is_temp(path, temps=None):
    p = normalize(path)
    for t in temps or temp_dirs():
        if p == t or p.startswith(t + "/"):
            return True
    return False


def builtin_rules(env=None):
    """Claude Code's own folders. Applied after the user's rules."""
    c = normalize(str(paths.claude_dir(env)))
    rules = [
        {"prefix": c + "/agents", "project": CLAUDE_CONFIG, "rank": "secondary"},
        {"prefix": c + "/commands", "project": CLAUDE_CONFIG, "rank": "secondary"},
        {"prefix": c + "/skills", "project": CLAUDE_CONFIG, "rank": "secondary"},
        {"prefix": c + "/CLAUDE.md", "project": CLAUDE_CONFIG, "rank": "secondary"},
    ]
    for name in ("projects", "plugins", "todos", "statsig", "shell-snapshots", "ide",
                 "file-history", "jobs", "session-env", "paste-cache", "debug",
                 paths.DATA_DIR_NAME):
        rules.append({"prefix": c + "/" + name, "project": None, "rank": "neutral"})
    return rules


def neutral_exact(env=None):
    """Paths that only say nothing as an exact match.

    The bare home directory is the main case: Claude Code gets started there,
    the work happens elsewhere.
    """
    home = _home()
    found = {home, "/", "/home", "/Users", "/root", "C:/Users", "C:",
             normalize(str(paths.claude_dir(env)))}
    if len(home) > 2 and home[1] == ":":
        found.add(home[:2])
    return found


def default_path(env=None):
    return paths.data_file("cost-rules.json", env)


def load(path=None, env=None):
    """The user's rules from the file. A missing or broken file means none.

    A broken file is left untouched so the user can see and fix the mistake.
    """
    target = Path(path) if path else default_path(env)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return []
    raw = data.get("rules") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return []
    return [r for r in raw if isinstance(r, dict) and r.get("prefix")]


def save(rules, path=None, env=None):
    target = Path(path) if path else default_path(env)
    content = {
        "_help": "prefix, project, rank. rank is project, secondary or neutral. "
                 "The longest matching prefix wins; a prefix ending in '-' matches "
                 "the start of a folder name.",
        "rules": rules,
    }
    paths.write_atomic(target, json.dumps(content, indent=2, ensure_ascii=False) + "\n")


def _matches(path, prefix):
    """Prefix match at a path boundary.

    A prefix that ends in a hyphen is meant as the start of a name
    (worktrees/myapp-) and may match in the middle of a folder name.
    """
    if path == prefix:
        return True
    if prefix.endswith(("-", "/")):
        return path.startswith(prefix)
    return path.startswith(prefix + "/")


def _read_gitdir(dotgit_file):
    try:
        text = Path(dotgit_file).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    return text[len("gitdir:"):].strip()


def _main_repo(candidate, gitdir):
    """The repository a .git file points into.

    A worktree's gitdir is <main>/.git/worktrees/<name>, a submodule's is
    <super>/.git/modules/<name>. Both count towards the outer repository:
    their history and their work belong to it.
    """
    if not gitdir:
        return candidate
    g = normalize(gitdir)
    if not (g.startswith("/") or (len(g) > 2 and g[1] == ":")):
        g = normalize(os.path.normpath(os.path.join(candidate, gitdir)))
    for marker in ("/.git/worktrees/", "/.git/modules/"):
        if marker in g:
            return g.split(marker, 1)[0]
    return candidate


def git_root(path, cache=None):
    """The root of the git repository a path lives in, or None.

    Walks up from the path. The path itself does not need to exist any more:
    the first existing ancestor is checked, so a deleted subfolder still
    belongs to its repository.
    """
    cache = {} if cache is None else cache
    p = normalize(path)
    if not p:
        return None
    walked = []
    current = p
    while current:
        if current in cache:
            root = cache[current]
            break
        walked.append(current)
        dotgit = current + "/.git"
        try:
            if os.path.isdir(dotgit):
                root = current
                break
            if os.path.isfile(dotgit):
                root = _main_repo(current, _read_gitdir(dotgit))
                break
        except OSError:
            pass
        parent = current.rsplit("/", 1)[0]
        if parent == current or not parent or parent.endswith(":"):
            root = None
            break
        current = parent
    else:
        root = None
    for w in walked:
        cache[w] = root
    return root


class Context:
    """Everything classification needs, plus caches for one run.

    The same folders come up thousands of times in one evaluation; going to
    the disk each time would be pure waste.
    """

    def __init__(self, rules=None, roots=None, neutral=None, env=None,
                 check_exists=True, known_roots=None):
        self.rules = [dict(r, prefix=normalize(r.get("prefix"))) for r in (rules or [])]
        self.rules += [dict(r, prefix=normalize(r["prefix"])) for r in builtin_rules(env)]
        self.roots = [normalize(r) for r in (roots or []) if r]
        self.neutral = {normalize(n) for n in (neutral if neutral is not None
                                               else neutral_exact(env))}
        self.temps = temp_dirs(env)
        self.check_exists = check_exists
        self.git_cache = {}
        self.exists_cache = {}
        # Roots resolved when the archive was written. They outlive the
        # folders: a deleted repository still knows where it belonged.
        self.known_roots = dict(known_roots or {})

    def git_root(self, path):
        p = normalize(path)
        if p in self.known_roots:
            return self.known_roots[p]
        return git_root(p, self.git_cache)

    def _from_roots(self, path):
        """(project name, project folder) from the project roots, or (None, None)."""
        best, folder, length = None, None, -1
        for root in self.roots:
            if not path.startswith(root + "/") or len(root) <= length:
                continue
            rest = path[len(root) + 1:].split("/")[0]
            # Hidden folders are storage, not projects. A folder that is a
            # root itself holds projects and is never one: a deleted
            # ~/worktrees/x must not turn into a project called "worktrees".
            if not rest or rest.startswith(".") or root + "/" + rest in self.roots:
                continue
            full = root + "/" + rest
            if self.check_exists:
                if full not in self.exists_cache:
                    self.exists_cache[full] = os.path.isdir(full)
                if not self.exists_cache[full]:
                    # A mistyped path would otherwise become a project of its own.
                    continue
            best, folder, length = rest, full, len(root)
        return best, folder

    def _by_rules(self, p):
        """(project, rank, matched) from the explicit rules."""
        name, rank, length = None, "neutral", -1
        for rule in self.rules:
            prefix = rule.get("prefix")
            if not prefix or not _matches(p, prefix) or len(prefix) <= length:
                continue
            r, project = rule.get("rank"), rule.get("project")
            # An unknown rank or a missing project must not assign anything
            # wrongly, so both count as neutral.
            if r not in RANKS or (r != "neutral" and not project):
                name, rank, length = None, "neutral", len(prefix)
            else:
                name, rank, length = project, r, len(prefix)
        return name, rank, length >= 0

    def classify(self, path):
        """(project, rank) for a path."""
        if not path:
            return None, "neutral"
        p = normalize(path)
        if p in self.neutral or is_temp(p, self.temps):
            return None, "neutral"

        name, rank, matched = self._by_rules(p)
        if matched:
            return name, rank

        root = self.git_root(p)
        # A dotfiles repository in the home folder would otherwise swallow
        # every path below it.
        if root in self.neutral:
            root = None
        found, folder = self._from_roots(p)
        # A repository nested inside a project folder (project/app/.git) is a
        # part of that project, not a project of its own. A worktree whose
        # main repository lives elsewhere is not nested and keeps its repo.
        if found and (root is None or root.startswith(folder + "/")):
            root = folder
        if root:
            # Rules written for a repository apply to its worktrees too.
            name, rank, matched = self._by_rules(root)
            if matched:
                return name, rank
            return root.rsplit("/", 1)[-1], "project"
        return None, "neutral"


def git_repos_from_rules(rules):
    """{project: repo path} for rules that name a repository (or whose prefix is one)."""
    found = {}
    for rule in rules or []:
        if rule.get("rank") != "project":
            continue
        project = rule.get("project")
        candidate = rule.get("repo") or rule.get("prefix")
        if not project or project in found or not candidate:
            continue
        p = normalize(str(candidate).rstrip("-/"))
        if os.path.isdir(p + "/.git"):
            found[project] = p
    return found
