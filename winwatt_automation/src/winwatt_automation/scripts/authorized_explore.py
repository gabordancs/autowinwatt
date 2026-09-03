"""CLI entry point for the rooms-first authorized explorer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from winwatt_automation.runtime_mapping.authorized_explorer import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_ROOM_NAME,
    run_authorized_exploration,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Map WinWatt menus and room surfaces without executing unknown leaf commands")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--room-name", default=DEFAULT_ROOM_NAME)
    args = parser.parse_args()
    result = run_authorized_exploration(output_dir=Path(args.output_dir), room_name=args.room_name)
    print(json.dumps({
        "output": str(Path(args.output_dir) / "authorized_exploration.json"),
        "menu_leaves": len(result["menu_leaf_frontier"]),
        "room_tabs": len(result["room_surfaces"]["tabs"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
