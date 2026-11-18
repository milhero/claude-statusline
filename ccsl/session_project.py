"""Which project the running session works on, for the status line.

The working directory wanders during a session: whoever writes a note in the
memory folder stands there for a moment. The project shown must not wander
with it, so the last project recognised is remembered per session id.

The cost attribution is not affected by any of this: it weighs every path a
session touched, not only the current directory.
"""

import json
import re
from pathlib import Path

from . import paths, rules as rules_mod

# Nobody needs more sessions at once. The file stays small without a
# clean-up routine of its own.
MAX_SESSIONS = 60


def default_path(env=None):
    return paths.data_file("sessions.json", env)


def _read(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _remember(path, session, name):
    """Remember a session's project without letting the file grow."""
    known = _read(path)
    if known.get(session) == name:
        return
    known.pop(session, None)
    known[session] = name
    # Keep the newest. dicts keep insertion order, a re-entry moves to the end.
    if len(known) > MAX_SESSIONS:
        for key in list(known)[:len(known) - MAX_SESSIONS]:
            del known[key]
    try:
        paths.write_atomic(path, json.dumps(known, ensure_ascii=False))
    except Exception:
        pass


# Backwards in growing blocks until something turns up. A long session often
# ends in plain text; giving up after 64 KB would lose the project exactly
# where most work happened. A full pass through many megabytes on every
# redraw would not be acceptable either, hence the cap.
BLOCKS = (65536, 524288, 2097152)

PATH_FIELD = re.compile(r'"(?:file_path|notebook_path|cwd)"\s*:\s*"((?:[^"\\]|\\.){3,400})"')

# Only the command field, not the whole text. CLAUDE.md and memory files name
# project paths and sit in every session's prompt; counting them would find
# the same project everywhere.
COMMAND_FIELD = re.compile(r'"command"\s*:\s*"((?:[^"\\]|\\.)*)"')

# Absolute paths in shell commands: POSIX (two parts at least), ~/..., and
# Windows drive paths.
POSIX_PATH = re.compile(r"(?<![\w/.~-])(/[A-Za-z0-9._@+-]+(?:/[A-Za-z0-9._@+-]+)+)")
HOME_PATH = re.compile(r"(?<![\w/])(~/[A-Za-z0-9._@+/-]+)")
WINDOWS_PATH = re.compile(r"(?<![\w])([A-Za-z]:[\\/][^\s\"'<>|;&*?]+)")


def unescape(json_string):
    """The text of a JSON string literal without its escapes."""
    try:
        return json.loads('"' + json_string + '"')
    except ValueError:
        return json_string


def paths_in_command(command):
    found = POSIX_PATH.findall(command) + HOME_PATH.findall(command)
    found += WINDOWS_PATH.findall(command)
    return [p.rstrip(".,:;)") for p in found]


def from_transcript(transcript, ctx):
    """The project from the most recently touched files.

    Whoever starts Claude Code in the home folder and never changes directory
    still works on a project. The directory does not tell, the edited files
    do; they are not in the status line input, but in the transcript whose
    path it carries.
    """
    if not transcript:
        return None
    done = 0
    for block in BLOCKS:
        try:
            with open(str(transcript), "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                if done >= size:
                    break
                f.seek(max(0, size - block))
                text = f.read().decode("utf-8", errors="replace")
        except Exception:
            return None
        done = block

        candidates = [unescape(p) for p in PATH_FIELD.findall(text)]
        for command in COMMAND_FIELD.findall(text):
            candidates += paths_in_command(unescape(command))

        counts = {}
        for hit in candidates:
            name, rank = ctx.classify(hit)
            # Only rank project: secondary would turn note-taking into the
            # session's project.
            if rank == "project" and name:
                counts[name] = counts.get(name, 0) + 1
        if counts:
            return max(counts.items(), key=lambda kv: kv[1])[0]
    return None


def determine(session, current_dir, project_dir, ctx, path=None, transcript=None):
    """The project of this session, in four steps.

    1. The current directory, if it is a project. It gets remembered.
    2. The directory the session started in.
    3. The project last recognised in this session.
    4. The most recently touched files in the transcript (remembered too, so
       the expensive search runs once per session).
    """
    target = Path(path) if path else default_path()

    for directory in (current_dir, project_dir):
        if not directory:
            continue
        name, rank = ctx.classify(directory)
        if rank == "project" and name:
            if session:
                _remember(target, session, name)
            return name

    if session:
        known = _read(target).get(session)
        if known:
            return known

    name = from_transcript(transcript, ctx)
    if name and session:
        _remember(target, session, name)
    return name


def context_for_statusline(cfg, env=None):
    return rules_mod.Context(rules_mod.load(env=env), roots=cfg.get("project_roots"), env=env)
