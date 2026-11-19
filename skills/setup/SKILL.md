---
name: setup
description: Set up, change or remove the claude-statusline status line (layout, language, cost tracker). Use when the user asks to install, configure or uninstall the status line.
disable-model-invocation: true
---

Set up claude-statusline for this user. A plugin cannot register a status line by itself, so this writes the `statusLine` entry in the user's Claude Code settings through the bundled installer. It keeps a backup and touches nothing else in that file.

1. Find a Python 3.9+ interpreter: try `python3 --version`, then `python --version`, then `py -3 --version` (Windows). If none works, tell the user Python 3.9 or newer is needed (python.org, or `xcode-select --install` on macOS) and stop.

2. Show what is there now: run `<python> "${CLAUDE_PLUGIN_ROOT}/install.py" --dry-run --mode plugin`. If it reports a status line that is already configured and not from claude-statusline, ask whether to replace it (it comes back on uninstall).

3. Ask the user, in one question round, with short options:
   - Layout: `calm-one-line` (default, one line), `calm-two-line` (identity on top, readings below), `expressive` (one row per limit with reset times), `traffic` (dots only).
   - Language: automatic (from the system), English, German.
   - Terminal command: whether to add `claude-costs` to `~/.local/bin` (pass `--no-command` if not).
   - Cost tracker: on or off. On means: an archive of the session logs is kept (Claude Code deletes them after 30 days), and the line shows the running project's value. Mention that it can be set up in detail afterwards with `/calm-statusline:cost-setup`.
   If the user wants to see the layouts first, run `<python> "${CLAUDE_PLUGIN_ROOT}/statusline.py" --demo` and show the output.

4. Run the installer with the answers:
   `<python> "${CLAUDE_PLUGIN_ROOT}/install.py" --mode plugin --theme <layout> --lang <auto|en|de> --costs <on|off>` (add `--force` only if the user agreed to replace a foreign status line).

5. Report in two or three sentences what changed and that the line appears with the next message. Point to `<python> "${CLAUDE_PLUGIN_ROOT}/statusline.py" --diagnose` for troubleshooting. If the installer warned that `~/.local/bin` is not on PATH, pass that on: it only matters for the `claude-costs` terminal command, `/calm-statusline:costs` works anyway.

To remove it (for example before uninstalling the plugin): `<python> "${CLAUDE_PLUGIN_ROOT}/install.py" --uninstall`. A status line the user had before comes back. The user's data (archive, invoices, rules) stays in the data folder the command names.
