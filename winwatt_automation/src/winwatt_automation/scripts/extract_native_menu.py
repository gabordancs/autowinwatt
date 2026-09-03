"""Export a non-invasive native Win32 menu snapshot for a running WinWatt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from winwatt_automation.live_ui.native_menu import enumerate_native_menu


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export WinWatt native menu IDs without clicking menu commands")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "data" / "snapshots" / "native_menu.json"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output = Path(args.output)
    payload = enumerate_native_menu()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved native menu snapshot to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
