"""Rebase native XML ETZone room references from a discovery import."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from winwatt_automation.certificates.native_xml import rebase_room_area_ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--readback", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()
    if args.target.exists():
        parser.error(f"target must be new: {args.target}")
    report = rebase_room_area_ids(
        args.source.resolve(strict=True),
        args.readback.resolve(strict=True),
        args.target.resolve(),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
