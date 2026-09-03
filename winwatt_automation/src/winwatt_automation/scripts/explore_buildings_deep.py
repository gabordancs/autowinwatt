"""Unbounded state-graph discovery rooted in the Buildings MDI child."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from winwatt_automation.runtime_mapping.room_deep_explorer import (
    active_buildings_window,
    explore_room_state_graph,
    open_sandbox_building,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument("--session-islands", action="store_true")
    parser.add_argument("--status-popup", action="store_true")
    args = parser.parse_args()
    notifier = None
    if args.status_popup:
        notifier = subprocess.Popen([
            sys.executable, "-m", "winwatt_automation.scripts.room_progress_popup",
            "--output-dir", str(args.output_dir), "--interval-seconds", "300",
        ])
    try:
        result = explore_room_state_graph(
            project_path=args.project, output_dir=args.output_dir, resume=args.resume,
            retry_failures=args.retry_failures, session_islands=args.session_islands,
            root_opener=lambda project: open_sandbox_building(project_path=project),
            active_resolver=active_buildings_window,
        )
    finally:
        if notifier is not None:
            notifier.terminate()
    print({"states": len(result["states"]), "edges": len(result["edges"]), "complete": result["complete"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
