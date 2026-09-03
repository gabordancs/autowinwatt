"""Write the evidence-backed safe command catalog."""

from __future__ import annotations

import json
from pathlib import Path

from winwatt_automation.runtime_mapping.command_catalog import build_runtime_command_catalog

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    output = PROJECT_ROOT / "data" / "runtime_maps" / "command_catalog_9_60.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    catalog = build_runtime_command_catalog()
    output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "command_count": len(catalog["commands"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
