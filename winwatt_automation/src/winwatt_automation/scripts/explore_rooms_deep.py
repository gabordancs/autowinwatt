"""CLI for unlimited, sandbox-only room state-space mapping."""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path
from winwatt_automation.runtime_mapping.room_deep_explorer import explore_room_state_graph


NON_CORE_ROOM_TABS = {
    "Radiátorok",
    "Felületfűtés-hűtés",
    "Fan-coilok",
    "Radiátor választék",
    "Felületfűtés-hűtés választék",
    "Fan-coil választék",
}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--room-name", default="Room graph explorer")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument(
        "--exclude-tab", action="append", default=[], metavar="TAB",
        help="Do not traverse this Helyiségek tab; repeat for multiple tabs.",
    )
    parser.add_argument(
        "--session-islands", action="store_true",
        help="Reuse a verified parent dialog for its button-child branches; root replay remains the fallback.",
    )
    parser.add_argument(
        "--room-core-only", action="store_true",
        help="Skip the six radiator, surface-heating/cooling and fan-coil tabs without shell Unicode arguments.",
    )
    parser.add_argument("--status-popup", action="store_true", help="Show a non-activating progress card every five minutes.")
    parser.add_argument("--status-interval", type=int, default=300)
    parser.add_argument("--status-visible-seconds", type=int, default=10)
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    notifier: subprocess.Popen[str] | None = None
    if args.status_popup:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        notifier = subprocess.Popen(
            [sys.executable, "-m", "winwatt_automation.scripts.room_progress_popup",
             "--output-dir", str(output_dir), "--interval-seconds", str(args.status_interval),
             "--visible-seconds", str(args.status_visible_seconds)],
            creationflags=creationflags,
        )
    try:
        excluded_tabs = set(args.exclude_tab)
        if args.room_core_only:
            excluded_tabs.update(NON_CORE_ROOM_TABS)
        graph = explore_room_state_graph(
            project_path=args.project, output_dir=output_dir, room_name=args.room_name,
            resume=args.resume, retry_failures=args.retry_failures,
            exclude_tab_names=excluded_tabs,
            session_islands=args.session_islands,
        )
    finally:
        if notifier is not None:
            notifier.terminate()
            try:
                notifier.wait(timeout=3)
            except subprocess.TimeoutExpired:
                notifier.kill()
    print(json.dumps({"complete": graph["complete"], "states": len(graph["states"]), "failures": len(graph["failures"])}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
