"""Run the network-independent WebWatt PDF/XML certificate intake."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from winwatt_automation.workflows.webwatt_certificate_intake import process_local_intake


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--catalog-xml", type=Path)
    args = parser.parse_args()
    try:
        manifest = process_local_intake(
            source=args.input_file, output_dir=args.output, catalog_xml=args.catalog_xml,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
