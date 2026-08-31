"""Replay a discovered catalog-root profile and explore it to full UI depth."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from pywinauto import Application

from winwatt_automation.runtime_mapping.room_deep_explorer import _active_window, explore_room_state_graph
from winwatt_automation.scripts.discover_catalog_root import _open_catalog, _submit_new_group


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--status-popup", action="store_true")
    parser.add_argument("--session-islands", action="store_true")
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    index = int(profile["catalog_index"])
    command = int(profile["element_command"]["index"])
    context = profile.get("context") or {}
    name = str(profile.get("probe_name") or "Auto exploration probe")
    template = PROJECT_ROOT / "tests" / "testwwp.wwp"

    def open_root(project_path: str):
        project = Path(project_path)
        shutil.copy2(template, project)
        main_window, child = _open_catalog(project, index)
        tree = context.get("tree")
        if tree:
            next(item for item in child.descendants(control_type="TreeItem") if item.window_text() == tree).click_input()
            time.sleep(0.2)
        process_id = int(main_window.process_id())
        native = Application(backend="win32").connect(process=process_id).window(handle=int(main_window.handle))
        element = next(item for item in native.menu().items() if item.text().replace("&", "").strip() == "Elem")
        element.click(); time.sleep(0.1)
        element.sub_menu().items()[command].click(); time.sleep(0.35)
        dialog = _active_window(process_id)
        if dialog.class_name() == "TNewGroupForm":
            if not _submit_new_group(dialog, name):
                raise RuntimeError("Profile creation dialog no longer contains an editable name field")
            time.sleep(0.5)
        return _active_window(process_id)

    notifier = None
    if args.status_popup:
        notifier = subprocess.Popen([sys.executable, "-m", "winwatt_automation.scripts.room_progress_popup", "--output-dir", str(args.output_dir)])
    try:
        graph = explore_room_state_graph(project_path=str(args.project.resolve()), output_dir=args.output_dir.resolve(),
                                         session_islands=args.session_islands, root_opener=open_root,
                                         active_resolver=_active_window)
    finally:
        if notifier is not None:
            notifier.terminate()
    print({"states": len(graph["states"]), "edges": len(graph["edges"]), "complete": graph["complete"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
