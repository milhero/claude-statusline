"""Setting up and removing claude-statusline.

Used by install.py (clone and run) and by the plugin's setup skill. Before
settings.json is touched, a backup is made, and only the statusLine key is
written; everything else in the file stays as it is.

The status line command points to a small launcher in the data folder,
never into the code itself. A plugin's code lives in a folder per version
that disappears on update; the launcher finds the current one, so an update
never breaks the line.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import config, paths

MIN_PYTHON = (3, 9)
MIN_CLAUDE = (2, 1, 251)
MARK = "claude-statusline"
COMMAND = "claude-costs"

LAUNCHER = r'''#!/usr/bin/env python3
# claude-statusline launcher, written by its setup.
# It finds the installed code, so plugin updates never break the status line.
import json
import os
import re
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def claude_dir():
    custom = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(os.path.expanduser(custom)) if custom else Path.home() / ".claude"


def version_key(path):
    parts = re.split(r"[.+-]", path.parent.name)
    numbers = tuple(int(p) if p.isdigit() else -1 for p in parts)
    try:
        when = path.stat().st_mtime
    except OSError:
        when = 0
    return numbers, when


def find():
    try:
        info = json.loads((HERE / "install.json").read_text(encoding="utf-8"))
    except Exception:
        info = {}
    if info.get("mode") == "plugin":
        found = list(claude_dir().glob("plugins/cache/*/calm-statusline/*/statusline.py"))
        if found:
            return max(found, key=version_key).parent
    code = info.get("code")
    if code and (Path(code) / "statusline.py").exists():
        return Path(code)
    return None


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "statusline"
    code = find()
    if code is None:
        if what == "statusline":
            print("")
            return 0
        print("claude-statusline: code not found, please run the setup again", file=sys.stderr)
        return 1
    script = code / ("statusline.py" if what == "statusline" else "claude_costs.py")
    sys.argv = [str(script)] + sys.argv[2:]
    sys.path.insert(0, str(code))
    runpy.run_path(str(script), run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def posix(path):
    """Forward slashes, on Windows too.

    Git Bash reads a backslash as an escape. A Windows path like C:\\Users loses
    its separators there and the call fails without a visible error.
    """
    return str(path).replace("\\", "/")


def version_at_least(text, minimum):
    """True, False, or None when the version cannot be read."""
    try:
        parts = [int(p) for p in str(text).strip().split(" ")[0].split(".")[:3]]
    except (ValueError, AttributeError):
        return None
    if not parts:
        return None
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts) >= tuple(minimum)


def claude_version():
    exe = shutil.which("claude")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20)
    except Exception:
        return None
    return out.stdout.strip().split(" ")[0] if out.returncode == 0 else None


def read_settings(path):
    path = Path(path)
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ValueError("{} is not valid JSON ({}). It is left untouched.".format(path, error))
    if not isinstance(data, dict):
        raise ValueError("{} does not contain an object.".format(path))
    return data


def backup(path):
    source = Path(path)
    if not source.exists():
        return None
    stamp = source.name + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
    target = source.with_name(stamp)
    n = 1
    while target.exists():
        # Never overwrite an earlier backup: it may hold the only copy of the
        # user's own settings.
        n += 1
        target = source.with_name("{}-{}".format(stamp, n))
    shutil.copyfile(str(source), str(target))
    return target


def write_settings(path, data):
    paths.write_atomic(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def launcher_path(env=None):
    return paths.data_file("run.py", env)


def statusline_command(python, env=None):
    return '"{}" "{}" statusline'.format(posix(python), posix(launcher_path(env)))


def is_ours(entry):
    return isinstance(entry, dict) and MARK in str(entry.get("command", ""))


def bin_dir():
    return paths.home() / ".local" / "bin"


def _command_files(folder):
    """A command without extension is not callable on Windows; a .cmd joins it."""
    files = [(folder / COMMAND, "sh")]
    if os.name == "nt":
        files.append((folder / (COMMAND + ".cmd"), "cmd"))
    return files


def _command_text(kind, python, env=None):
    launcher = posix(launcher_path(env))
    if kind == "cmd":
        return '@echo off\r\nrem {}\r\n"{}" "{}" costs %*\r\n'.format(MARK, python, launcher)
    return '#!/bin/sh\n# {}\nexec "{}" "{}" costs "$@"\n'.format(MARK, posix(python), launcher)


class Plan:
    """What the setup is going to do, so --dry-run can show it unchanged."""

    def __init__(self):
        self.steps = []

    def add(self, text, action=None):
        self.steps.append((text, action))

    def run(self, dry):
        done = []
        for text, action in self.steps:
            if not dry and action is not None:
                result = action()
                if result:
                    text = result
            done.append(text)
        return done


def install(code_dir, python=None, mode="repo", force=False, commands=True,
            settings=None, choices=None, env=None):
    """Plan the installation. Returns (plan, warnings)."""
    python = python or sys.executable
    settings = Path(settings) if settings else paths.settings_file(env)
    plan, warnings = Plan(), []

    current = read_settings(settings)
    existing = current.get("statusLine")
    replace = existing is None or is_ours(existing) or force
    if not replace:
        warnings.append("A status line is already configured ({}). Nothing changed there; "
                        "use --force to replace it (a backup is kept).".format(
                            str(existing.get("command", existing))[:80]
                            if isinstance(existing, dict) else existing))

    data_dir = paths.data_dir(env)
    plan.add("Data folder: {}".format(data_dir), lambda: paths.ensure_data_dir(env) and None)
    plan.add("Launcher: {}".format(launcher_path(env)),
             lambda: paths.write_atomic(launcher_path(env), LAUNCHER))
    info = {"mode": mode, "code": posix(code_dir), "python": posix(python)}
    # A status line that gets replaced comes back on uninstall.
    earlier = _read_record(env).get("previous_statusline")
    if existing is not None and not is_ours(existing) and replace:
        earlier = existing
    if earlier is not None:
        info["previous_statusline"] = earlier
    plan.add("Install record: mode {}, code {}".format(mode, posix(code_dir)),
             lambda: paths.write_atomic(paths.data_file("install.json", env),
                                        json.dumps(info, indent=2) + "\n"))
    if choices:
        plan.add("Settings: {}".format(", ".join("{}={}".format(k, v) for k, v in choices.items())),
                 lambda: config.save(choices, env=env) and None)

    if replace:
        def write_statusline():
            data = read_settings(settings)
            saved = backup(settings)
            entry = {"type": "command", "command": statusline_command(python, env),
                     "padding": 0, "refreshInterval": 60}
            # Spacing and redraw interval are the user's choice; keep them.
            before = data.get("statusLine")
            if isinstance(before, dict):
                for key in ("padding", "refreshInterval"):
                    if isinstance(before.get(key), int) and not isinstance(before.get(key), bool):
                        entry[key] = before[key]
            data["statusLine"] = entry
            write_settings(settings, data)
            return "Status line set in {}{}".format(
                settings, " (backup: {})".format(saved.name) if saved else "")
        plan.add("Status line in {}".format(settings), write_statusline)

    if commands:
        folder = bin_dir()
        files = _command_files(folder)
        foreign = [f for f, _ in files if f.exists() and MARK not in
                   f.read_text(encoding="utf-8", errors="replace")]
        if foreign:
            warnings.append("{} exists and is not ours, left alone.".format(foreign[0]))
        else:
            def write_commands():
                folder.mkdir(parents=True, exist_ok=True)
                for target, kind in files:
                    target.write_text(_command_text(kind, python, env), encoding="utf-8")
                    try:
                        target.chmod(0o755)
                    except (OSError, NotImplementedError):
                        pass
                return "Command: {}".format(files[0][0])
            plan.add("Command: {}".format(files[0][0]), write_commands)
            if str(folder) not in os.environ.get("PATH", ""):
                if os.name == "nt":
                    warnings.append(
                        "{} is not on your PATH. Once in PowerShell, then reopen it:\n"
                        "  [Environment]::SetEnvironmentVariable('Path', $env:Path + ';' + "
                        "$HOME + '\\.local\\bin', 'User')".format(folder))
                else:
                    warnings.append('{} is not on your PATH. Add to your shell profile:\n'
                                    '  export PATH="$HOME/.local/bin:$PATH"'.format(folder))
    return plan, warnings


def _read_record(env=None):
    try:
        data = json.loads(paths.data_file("install.json", env).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def uninstall(settings=None, env=None):
    """Plan the removal. Data (archive, invoices, rules) stays and is named."""
    settings = Path(settings) if settings else paths.settings_file(env)
    plan = Plan()
    current = read_settings(settings)
    earlier = _read_record(env).get("previous_statusline")
    if is_ours(current.get("statusLine")):
        def remove_statusline():
            data = read_settings(settings)
            saved = backup(settings)
            if earlier is not None:
                data["statusLine"] = earlier
            else:
                data.pop("statusLine", None)
            write_settings(settings, data)
            return "{} in {}{}".format(
                "Earlier status line restored" if earlier is not None else "Status line removed",
                settings, " (backup: {})".format(saved.name) if saved else "")
        plan.add("Remove the status line from {}".format(settings), remove_statusline)
    for target, _ in _command_files(bin_dir()):
        if target.exists() and MARK in target.read_text(encoding="utf-8", errors="replace"):
            plan.add("Remove {}".format(target), lambda t=target: t.unlink() and None)
    for name in ("run.py", "install.json"):
        target = paths.data_file(name, env)
        if target.exists():
            plan.add("Remove {}".format(target), lambda t=target: t.unlink() and None)
    plan.add("Your data stays in {} (delete the folder to remove it).".format(
        paths.data_dir(env)))
    return plan
