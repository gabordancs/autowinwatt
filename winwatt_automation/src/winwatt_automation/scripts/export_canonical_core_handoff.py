from __future__ import annotations

import argparse
import json
from pathlib import Path

from winwatt_automation.certificates.canonical_handoff import write_core_handoff


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a reviewed AutoWinWatt model to the shared core/evidence handoff."
    )
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = write_core_handoff(args.model, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
