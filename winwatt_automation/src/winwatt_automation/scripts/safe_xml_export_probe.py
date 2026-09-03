"""CLI entry point for the non-writing XML Export probe."""
from __future__ import annotations
import json
from winwatt_automation.workflows.safe_xml_export_probe import run_safe_xml_export_probe

if __name__ == "__main__":
    result = run_safe_xml_export_probe()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["success"] else 1)
