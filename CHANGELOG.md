# Changelog

## 1.0.2

- macOS with an own `CLAUDE_CONFIG_DIR`: the login is found again. Claude Code names its keychain entry after the config folder in that case, the status line asked for the default entry and got neither plan nor limits from the server.
- The model week only shows a window that belongs to a model. A scoped window can also stand for a surface; that one no longer shows up as the model week. With several model windows the current model's comes first, otherwise the fullest.
- Plan names in `invoices.json` are recognised in the usual spellings ("Claude Max (20x)", "Max20x", "claude pro"), so the rates of unmeasured plans can still be derived.

## 1.0.1

- Pro plans showed as "ai" (#1). The plan now comes from the subscription type, as in Claude Code; the rate limit tier only tells Max 5x from Max 20x. A tier several plans share, like `default_claude_ai`, no longer turns into a plan name.

## 1.0.0

First public release.

- Status line with weekly, model-specific weekly and five-hour limits, context, plan, model and effort, in four layouts.
- Plan signature as a gradient within one hue; Ultra gets the full span.
- Readable on light terminal themes.
- English and German.
- Cost per project: archive of Claude Code's logs, attribution by git repository, subscription share from real invoices, frozen estimate for the time before the archive, self-check.
- Guided setup inside Claude Code (`/calm-statusline:setup`, `/calm-statusline:cost-setup`).
- Installer with `--dry-run` and a complete `--uninstall`.
