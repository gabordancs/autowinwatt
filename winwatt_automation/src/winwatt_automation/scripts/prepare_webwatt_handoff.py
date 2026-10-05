"""Validate a WebWatt review handoff and write a reviewed model fragment."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from winwatt_automation.certificates.webwatt_handoff import write_reviewed_model_fragment


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", required=True, type=Path)
    parser.add_argument("--catalog-xml", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("output must be new")
    output.mkdir(parents=True)
    handoff = args.handoff.resolve(strict=True)
    catalog = args.catalog_xml.resolve(strict=True)
    target = output / "reviewed_model_fragment.json"
    report = {
        "schema_version": 1,
        "operation": "webwatt.review_handoff.prepare",
        "handoff": str(handoff), "handoff_sha256": digest(handoff),
        "catalog": str(catalog), "catalog_sha256": digest(catalog),
        "llm_used": False, "winwatt_started": False,
        "started_at": datetime.now(timezone.utc).isoformat(), "status": "failed",
    }
    try:
        report["result"] = write_reviewed_model_fragment(handoff, catalog, target)
        report["target_sha256"] = digest(target)
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = repr(exc)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
