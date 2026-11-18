#!/usr/bin/env python3
"""claude-costs: what the work with Claude Code cost, per project."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ccsl import report_cli  # noqa: E402

if __name__ == "__main__":
    report_cli.utf8_output()
    try:
        sys.exit(report_cli.main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)
