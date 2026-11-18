#!/usr/bin/env python3
"""Set up claude-statusline for Claude Code.

    python3 install.py                 set up with defaults
    python3 install.py --dry-run       show what would change, change nothing
    python3 install.py --uninstall     remove it again (your data stays)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ccsl import config, installer, sources  # noqa: E402


def parse(argv):
    p = argparse.ArgumentParser(prog="install.py",
                                description="Set up claude-statusline for Claude Code.")
    p.add_argument("--dry-run", action="store_true", help="show what would change, change nothing")
    p.add_argument("--uninstall", action="store_true",
                   help="remove the status line, launcher and command (data stays)")
    p.add_argument("--force", action="store_true",
                   help="replace a status line that is already configured")
    p.add_argument("--theme", choices=config.THEMES, help="layout of the status line")
    p.add_argument("--lang", choices=("auto", "en", "de"), help="language")
    p.add_argument("--costs", choices=("on", "off"), help="cost tracker on or off")
    p.add_argument("--no-command", action="store_true",
                   help="do not create the claude-costs command in ~/.local/bin")
    p.add_argument("--mode", choices=("repo", "plugin"), default="repo",
                   help=argparse.SUPPRESS)
    p.add_argument("--version", action="version", version="claude-statusline " + sources.VERSION)
    return p.parse_args(argv)


def main(argv):
    args = parse(argv)
    if sys.version_info < installer.MIN_PYTHON:
        print("Python {}.{} or newer is needed, found {}.{}.".format(
            *installer.MIN_PYTHON, *sys.version_info[:2]))
        return 1

    if args.uninstall:
        plan = installer.uninstall()
        for line in plan.run(args.dry_run):
            print(("would: " if args.dry_run else "") + line)
        return 0

    version = installer.claude_version()
    if version is None:
        print("Claude Code not found on PATH. Setting up anyway.")
    elif installer.version_at_least(version, installer.MIN_CLAUDE) is False:
        print("Claude Code {} is older than {}.{}.{}: weekly and five-hour limits will be "
              "missing until you update.".format(version, *installer.MIN_CLAUDE))

    choices = {}
    if args.theme:
        choices["theme"] = args.theme
    if args.lang:
        choices["language"] = args.lang
    if args.costs:
        on = args.costs == "on"
        choices["cost_tracking"] = on
        choices["show"] = {"project": on}

    code = Path(__file__).resolve().parent
    try:
        plan, warnings = installer.install(code, mode=args.mode, force=args.force,
                                           commands=not args.no_command, choices=choices)
    except ValueError as error:
        print(error)
        return 1

    for line in plan.run(args.dry_run):
        print(("would: " if args.dry_run else "") + line)
    for warning in warnings:
        print(warning)
    if not args.dry_run:
        print("\nDone. The line appears with your next message in Claude Code.")
        print('Check: "{}" "{}" --diagnose'.format(installer.posix(sys.executable),
                                                   installer.posix(code / "statusline.py")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
