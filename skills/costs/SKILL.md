---
name: costs
description: Show what the work with Claude Code cost per project (API list value and share of the subscription), from claude-statusline's cost tracker. Use when the user asks about costs per project, usage value, or the cost report.
---

Show the cost report of claude-statusline and explain it briefly.

Find Python as in the setup (`python3`, `python`, or `py -3`) and run, from any directory:

`<python> "${CLAUDE_PLUGIN_ROOT}/claude_costs.py" $ARGUMENTS`

Useful arguments, pick what fits the question:

| Argument | Shows |
| --- | --- |
| (none) | the table per project |
| `--period 2026-09` | one month (also `2026` or `2026-09-05`) |
| `--project NAME` | one project |
| `--by-source` | measured vs. estimated per project |
| `--formula` | how it is computed, with the rates used |
| `--compare` | how long the same work would have taken on other plans |
| `--check` | the self-check |
| `--history` | totals day by day |

Show the output as it is (it is already formatted), then add at most three sentences: the main takeaway, and anything the output flags (failed checks, a high "Unassigned" share, missing invoices). If the archive is empty or the tracker was never set up, suggest `/calm-statusline:cost-setup`.

Read the numbers correctly:
- "API value" is what the same work would have cost at API list prices, in dollars. It is not what the user paid.
- "Subscription" is the part of the real subscription fee that falls on the project, in the currency of the user's invoices. Only shown when invoices are entered.
- Rows marked `~` are mostly estimated from git history (time before the archive started).
