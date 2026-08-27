"""Create an evidence audit for a room deep-exploration run."""

from __future__ import annotations

import argparse
from pathlib import Path

from winwatt_automation.runtime_mapping.room_deep_audit import audit_room_graph


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    result = audit_room_graph(args.run_dir)
    print(f"states={result['state_count']} evidence_complete={result['evidence_complete']} pending_edges={len(result['pending_edges'])}")


if __name__ == "__main__":
    main()
