"""Where Claude Code and this tool keep their files.

Claude Code honours CLAUDE_CONFIG_DIR, so everything here does too: logs,
credentials, settings.json and our own data all move with it.
"""

import os
import stat
from pathlib import Path

DATA_DIR_NAME = "claude-statusline"


def home():
    """The home directory, or the current one as a last resort.

    Path.home() raises when neither HOME nor USERPROFILE is set, which happens
    in stripped-down Windows environments. The status line must survive that.
    """
    try:
        return Path.home()
    except (RuntimeError, OSError, KeyError):
        return Path(".")


def claude_dir(env=None):
    env = os.environ if env is None else env
    custom = (env.get("CLAUDE_CONFIG_DIR") or "").strip()
    if custom:
        return Path(os.path.expanduser(custom))
    return home() / ".claude"


def data_dir(env=None):
    return claude_dir(env) / DATA_DIR_NAME


def data_file(name, env=None):
    return data_dir(env) / name


def logs_dir(env=None):
    return claude_dir(env) / "projects"


def credentials_file(env=None):
    return claude_dir(env) / ".credentials.json"


def settings_file(env=None):
    return claude_dir(env) / "settings.json"


def ensure_data_dir(env=None):
    d = data_dir(env)
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_atomic(path, text):
    """Write via a temporary file and rename, so readers never see half a file.

    An existing file keeps its permissions: settings.json may hold secrets in
    its env block and be readable by its owner only.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-{}".format(os.getpid()))
    tmp.write_text(text, encoding="utf-8")
    try:
        os.chmod(str(tmp), stat.S_IMODE(os.stat(str(path)).st_mode))
    except OSError:
        pass
    try:
        os.replace(str(tmp), str(path))
    except OSError:
        # Windows refuses the rename while another process has the file
        # open. Leave no temporary file behind; the next run tries again.
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
