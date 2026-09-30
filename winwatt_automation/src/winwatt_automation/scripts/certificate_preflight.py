"""Run the local deterministic certificate release gate without WinWatt UI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from winwatt_automation.certificates.preflight import run_preflight


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--readback-xml", type=Path)
    parser.add_argument("--catalog-xml", type=Path)
    parser.add_argument("--scope", choices=("envelope", "g5_calculation", "full_certificate"), default="full_certificate")
    parser.add_argument("--tolerance", type=float, default=0.02)
    args = parser.parse_args()
    if args.tolerance < 0:
        parser.error("--tolerance must not be negative")
    try:
        report = run_preflight(
            model_path=args.model, output_dir=args.output,
            readback_xml=args.readback_xml, catalog_xml=args.catalog_xml,
            scope=args.scope, tolerance=args.tolerance,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
