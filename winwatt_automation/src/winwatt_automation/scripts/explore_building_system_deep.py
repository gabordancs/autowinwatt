"""Map one WinWatt building-services editor deeply in a reusable UI session."""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from pywinauto import Desktop
from pywinauto.controls.common_controls import ToolbarWrapper

from winwatt_automation.runtime_mapping.room_deep_explorer import (
    _active_window,
    explore_room_state_graph,
    open_sandbox_building,
)
from winwatt_automation.version_profile import require_profile


SYSTEMS = {
    "heating": (0, "THeatingEnergyForm"),
    "water_heating": (1, "TWaterHeatingEnergyForm"),
    "lighting": (2, "TLightingEnergyForm"),
    "airing": (3, "TAiringEnergyForm"),
    "cooling": (4, "TCoolingEnergyForm"),
    "gain_or_loss": (5, "TSolarEnergyForm"),
}


def open_system_editor(project_path: str, system: str):
    index, expected_class = SYSTEMS[system]
    editor = open_sandbox_building(project_path=project_path, reuse_session=True)
    tabs = [
        tab for tab in editor.descendants(control_type="TabItem")
        if tab.window_text() == "Épülettechnikai rendszerek"
    ]
    if len(tabs) != 1:
        raise RuntimeError(f"Expected one systems tab, found {len(tabs)}")
    tabs[0].select()
    time.sleep(0.3)
    native = Desktop(backend="win32").window(handle=int(editor.handle)).wrapper_object()
    toolbars = sorted(
        [item for item in native.descendants() if item.class_name() == "TToolBar" and item.is_visible()],
        key=lambda item: item.rectangle().left,
    )
    if len(toolbars) != 3:
        raise RuntimeError(f"Expected three systems toolbars, found {len(toolbars)}")
    toolbar = ToolbarWrapper(toolbars[0].handle)
    if toolbar.button_count() != 8 or int(toolbar.get_button_struct(6).fsStyle) != 1:
        raise RuntimeError("Original-systems toolbar guard mismatch")
    rect = toolbar.get_button_rect(index)
    toolbar.click_input(coords=((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2))
    process_id = int(editor.process_id())
    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline:
        dialog = _active_window(process_id)
        if dialog.class_name() == expected_class:
            return dialog
        time.sleep(0.15)
    raise RuntimeError(f"System {system!r} did not open {expected_class}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--system", required=True, choices=sorted(SYSTEMS))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-failures", action="store_true")
    args = parser.parse_args()
    profile = require_profile(args.profile)
    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]

    graph = explore_room_state_graph(
        project_path=str(args.project.resolve(strict=True)),
        output_dir=args.output_dir.resolve(),
        resume=args.resume,
        retry_failures=args.retry_failures,
        session_islands=True,
        exclude_action_names={"Bezárás", "Elvet", "OK"},
        root_opener=lambda project: open_system_editor(project, args.system),
        active_resolver=_active_window,
    )
    print({"system": args.system, "states": len(graph["states"]), "edges": len(graph["edges"]), "complete": graph["complete"]})
    return 0 if graph["complete"] and bool(graph["states"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
