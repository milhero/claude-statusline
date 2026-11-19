# Changelog

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
