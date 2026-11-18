---
name: cost-setup
description: Guided setup of claude-statusline's cost tracker - finds projects, subscription invoices and older history, fills the configuration with the user, then checks the result critically. Use when the user wants to set up, complete or audit their cost per project.
disable-model-invocation: true
---

Help the user set up the cost tracker of claude-statusline so that the cost per project is complete and correct. You find and propose; the user decides; the Python code computes. Never invent numbers, never compute totals yourself.

Python: as in the setup (`python3`, `python` or `py -3`). Below, `costs` means `<python> "${CLAUDE_PLUGIN_ROOT}/claude_costs.py"`.

## 1. Take stock

Run `costs --discover`. It prints JSON: logs (how far back), archive, first prompt in `history.jsonl`, `cleanupPeriodDays`, plan, git author emails, repositories with commit ranges and own-commit counts, working folders that ended up unassigned, current rules, invoice status, and a list of `issues`. Summarise it for the user in a few lines: what is covered, what is missing.

## 2. Make sure nothing gets lost

If `cleanup_period_days` is missing or below 90: Claude Code deletes logs after 30 days by default. Suggest setting `"cleanupPeriodDays": 365` in the user's Claude Code `settings.json` (about 1 GB of logs per month of heavy use). Only change it with the user's consent. If cost tracking is off in the settings (`cost_tracking`), turn it on with the user's consent via the setup skill or by setting `"cost_tracking": true` in the data folder's `config.json`.

## 3. Projects

Projects are detected automatically: the git repository a path lives in, worktrees count towards their main repository. Rules are only needed where detection cannot know better. Look at `repos` and `unassigned_top_dirs` and propose rules only for:
- a monorepo the user wants split into parts (rule per subfolder),
- several repositories that are one project,
- folders without git that hold real work (or a `project_roots` entry in `config.json` for a folder that contains many such projects),
- side work that should only count when nothing else was touched (rank `secondary`).

Ask the user to confirm, then write the rules file named in `rules.path` (format: `{"rules": [{"prefix": "...", "project": "...", "rank": "project|secondary|neutral"}]}`; the longest prefix wins, `~` is allowed, a prefix ending in `-` matches the start of a folder name).

If `git_author_emails` is empty or misses addresses the user commits with, add them as `"git_author_emails": [...]` in `config.json`. Only the user's own commits count for the estimate of the time before the archive.

## 4. Subscription invoices

Ask where the user can see their invoices. Usually: claude.ai → Settings → Billing (invoice list with date and amount), or the receipts Anthropic sends by mail. If an email tool is connected in this session, ask for permission before searching it, then search only for receipts from Anthropic. Collect date, amount and plan per invoice, plus the currency. One-off purchases of extra usage get `"kind": "extra"`.

Write the invoices file named in `invoices.path`:
`{"currency": "EUR", "invoices": [{"date": "2026-01-24", "amount": 21.42, "plan": "Pro"}]}`
Plan names: `Pro`, `Max 5x`, `Max 20x`, `Ultra`, `Team`. Read every amount back to the user before writing. Never guess an amount.

## 5. Older history

- Time before the archive is estimated from the git history (own commits, changed lines). After rules and invoices are in place, run `costs --refreeze` once so the estimate uses them.
- Work on other machines can be added as entries in `other-machines.json` in the data folder (tokens per model counted there); offer this only if the user works on several machines.

## 6. Question the result

Run `costs`, `costs --by-source` and `costs --check`. Then look critically and tell the user what stands out, for example:
- "Unassigned" above a few percent: which folders cause it (`--discover` again), and whether a rule fixes it.
- A project with cost but no commits, or many commits but almost no measured cost.
- Large gaps between invoices, or the last invoice older than a month.
- A high estimated share: how far back the logs go, and that `cleanupPeriodDays` keeps the future measured.
- Any failed check, in plain words.

Fix what the user agrees to, then run the report once more and finish with a short summary of what is set up and what (if anything) is still open.
