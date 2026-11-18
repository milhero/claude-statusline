"""Shared test helpers: a sandboxed Claude config folder and log lines."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock


# /var/folders is macOS's temp folder and holds the sandbox there, so it is
# left out like /tmp; the real list is tested on its own.
SAFE_TEMPS = ("/proc", "/sys", "/dev", "/run")


class Sandbox(unittest.TestCase):
    """Every test gets its own home and Claude config folder."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.root), True)
        # The sandbox lives in the system temp folder, which the tracker
        # treats as scratch space that never belongs to a project. Inside the
        # sandbox that rule is switched off; /proc and friends stay.
        temps = mock.patch("ccsl.rules.temp_dirs", lambda env=None: SAFE_TEMPS)
        temps.start()
        self.addCleanup(temps.stop)
        self.home = self.root / "home"
        self.claude = self.home / ".claude"
        (self.claude / "projects").mkdir(parents=True)
        env = {"HOME": str(self.home), "USERPROFILE": str(self.home),
               "CLAUDE_CONFIG_DIR": str(self.claude), "LANG": "en_US.UTF-8"}
        for name in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "NO_COLOR"):
            env[name] = ""
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.data = self.claude / "claude-statusline"

    def repo(self, *parts, worktree_of=None):
        """Create a folder that is a git repository (or a worktree of one)."""
        path = self.root.joinpath(*parts)
        path.mkdir(parents=True, exist_ok=True)
        if worktree_of:
            (path / ".git").write_text(
                "gitdir: {}/.git/worktrees/{}\n".format(worktree_of, path.name),
                encoding="utf-8")
        else:
            (path / ".git").mkdir(exist_ok=True)
        return str(path).replace("\\", "/")

    def log(self, folder, name, lines):
        path = self.claude / "projects" / folder / (name + ".jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
        return path


def answer(out=10, cwd="/work", when="2026-09-16T10:00:00.000Z", command=None,
           file_path=None, request=None, model="claude-opus-5", usage=None):
    content = []
    if command:
        content.append({"type": "tool_use", "name": "Bash", "input": {"command": command}})
    if file_path:
        content.append({"type": "tool_use", "name": "Edit", "input": {"file_path": file_path}})
    record = {"type": "assistant", "cwd": cwd, "timestamp": when,
              "message": {"role": "assistant", "model": model,
                          "usage": usage or {"output_tokens": out}, "content": content}}
    if request:
        record["requestId"] = request
    return record


def cost(usd, start, api=1000, session="s", model="claude-opus-5", out=100):
    return {"type": "cost-state", "sessionId": session, "totalCostUSD": usd,
            "totalDuration": 5000, "totalAPIDuration": api, "startTime": start,
            "modelUsage": {model: {"costUSD": usd, "outputTokens": out}}}
