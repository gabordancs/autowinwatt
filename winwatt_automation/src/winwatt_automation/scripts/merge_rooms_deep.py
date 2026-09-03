"""Merge two deep room-mapping runs into a resumable output run."""

from __future__ import annotations

import argparse
from pathlib import Path

from winwatt_automation.runtime_mapping.room_deep_merge import merge_room_runs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--additional", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    graph = merge_room_runs(base_run=args.base, additional_run=args.additional, output_run=args.output)
    print(f"states={len(graph['states'])} edges={len(graph['edges'])} failures={len(graph['failures'])}")


if __name__ == "__main__":
    main()
