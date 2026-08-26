"""CLI entry point for the non-mutating Program Options workflow probe."""

from __future__ import annotations

import json

from winwatt_automation.workflows.safe_program_options_probe import run_safe_program_options_probe


def main() -> int:
    result = run_safe_program_options_probe()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
