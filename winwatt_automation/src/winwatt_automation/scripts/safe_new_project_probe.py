"""CLI entry point for the non-mutating New Project workflow probe."""

from __future__ import annotations

import json
from pathlib import Path

from winwatt_automation.workflows.safe_new_project_probe import run_safe_new_project_probe

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    result = run_safe_new_project_probe()
    output = PROJECT_ROOT / "data" / "snapshots" / "new_project_dialog_9_60.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Saved dialog evidence to {output}")
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
