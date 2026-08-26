"""CLI entry point for the non-generating custom-report probe."""

from __future__ import annotations

import json

from winwatt_automation.workflows.safe_custom_reports_probe import run_safe_custom_reports_probe


if __name__ == "__main__":
    result = run_safe_custom_reports_probe()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["success"] else 1)
