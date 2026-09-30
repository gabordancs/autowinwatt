"""Unbounded state-graph discovery rooted in the Buildings MDI child."""
from __future__ import annotations

import argparse
import os
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
    parser.add_argument(
        "--focus-tab", action="append", default=[], metavar="TAB",
        help="Explore only paths below this Building tab; repeat for multiple areas.",
    )
    parser.add_argument("--status-popup", action="store_true")
    parser.add_argument("--version-profile", type=Path, help="Reject changed executable/resources before any UI action")
    args = parser.parse_args()
    if args.version_profile:
        from winwatt_automation.version_profile import require_profile
        profile = require_profile(args.version_profile)
        os.environ['WWA_WINWATT_EXE_PATH'] = profile['exe_path']
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
            focus_tab_names=set(args.focus_tab),
            root_opener=lambda project: open_sandbox_building(
                project_path=project, reuse_session=args.session_islands,
            ),
            active_resolver=active_buildings_window,
        )
    finally:
        if notifier is not None:
            notifier.terminate()
    print({"states": len(result["states"]), "edges": len(result["edges"]), "complete": result["complete"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
