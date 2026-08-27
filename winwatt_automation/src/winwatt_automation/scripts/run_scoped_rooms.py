"""Run user-selected, evidence-preserving room mapping scopes."""
from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pywinauto import Application, Desktop, keyboard

from winwatt_automation.runtime_mapping.room_deep_explorer import _write_state, open_sandbox_room
from winwatt_automation.runtime_mapping.unified_mapping import PROJECT_ROOT, UNIFIED_ROOT, write_manifest, write_progress
from winwatt_automation.scripts.full_authorized_explore import create_execution_sandbox, run_full_authorized_exploration


SCOPES = {
    "main_window": "Főablak: projekt nélküli és projektmegnyitott állapot",
    "full_program": "Teljes program: minden felsőmenü és jegyzék (külön sandbox)",
    "general": "Általános adatok",
    "winter": "Téli hőszükséglet",
    "summer": "Nyári hőterhelés és részablakai",
    "boundaries": "Határoló szerkezetek kiválasztása",
    "external_wall": "Külső fal szerkesztése",
}


def _visible_window(process_id: int, class_name: str):
    return next(
        item for item in Desktop(backend="uia").windows(top_level_only=True)
        if item.process_id() == process_id and item.class_name() == class_name and item.is_visible() and item.is_enabled()
    )


def _dismiss(window) -> None:
    window.set_focus()
    keyboard.send_keys("{ESC}")
    time.sleep(0.35)


def _open_boundaries(room):
    button = next(item for item in room.descendants(control_type="Button") if item.window_text() == "Szerkezetek...")
    button.click_input()
    time.sleep(0.55)
    return _visible_window(int(room.process_id()), "TSelectBoundarisForm")


def _capture_tab(room, index: int, state_id: str, output: Path, parent: dict | None = None) -> dict:
    room.descendants(control_type="TabItem")[index].click_input()
    time.sleep(0.3)
    record, _ = _write_state(
        output_dir=output, state_id=state_id, window=room,
        parent_state=parent["state_id"] if parent else None,
        parent_signature=parent["signature"] if parent else None, path=[],
    )
    return record


def _run_scope(scope: str, project: str, output: Path) -> None:
    if scope == "main_window":
        # The existing full-runtime mapper records both root states before it
        # enters menus.  Blocked mode observes them without executing leaves.
        command = [sys.executable, "-m", "winwatt_automation.scripts.map_full_program", "--project-path", project,
                   "--safe-mode", "blocked", "--output-dir", str(output / "main_window"), "--allow-process-restart"]
        completed = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
        (output / "main_window.log").write_text(completed.stdout + "\n" + completed.stderr, encoding="utf-8")
        if completed.returncode:
            raise RuntimeError(f"main_window_mapper_exit={completed.returncode}")
        return
    if scope == "full_program":
        # Full mapping deliberately starts from the version-controlled source,
        # not the live room sandbox. The mapper creates a fresh disposable
        # sandbox before executing any enabled program command.
        source = PROJECT_ROOT / "tests" / "testwwp.wwp"
        result = run_full_authorized_exploration(source_project=source)
        (output / "full_program_run.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    room = open_sandbox_room(project_path=project, room_name="Room graph explorer")
    _run_room_scope(scope, room, output)


def _run_room_scope(scope: str, room, output: Path) -> None:
    if scope == "general":
        _capture_tab(room, 4, "room_general", output)
    elif scope == "winter":
        _capture_tab(room, 5, "room_winter_heat_need", output)
    elif scope == "summer":
        parent = _capture_tab(room, 6, "room_summer_heat_load", output)
        for caption, state_id in (
            ("Emberi hőleadás...", "summer_human_heat"), ("Világítás...", "summer_lighting"),
            ("Filtráció...", "summer_filtration"), ("Anyagmozgás...", "summer_material_movement"),
            ("Egyéb hőterhelés...", "summer_other_heat"),
        ):
            button = next(item for item in room.descendants(control_type="Button") if item.window_text() == caption)
            button.click_input(); time.sleep(0.45)
            dialog = next(item for item in Desktop(backend="uia").windows(top_level_only=True) if item.process_id() == room.process_id() and item.handle != room.handle and item.is_visible() and item.is_enabled())
            _write_state(output_dir=output, state_id=state_id, window=dialog, parent_state=parent["state_id"], parent_signature=parent["signature"], path=[])
            _dismiss(dialog)
    else:
        outer = _open_boundaries(room)
        if scope == "boundaries":
            root, _ = _write_state(output_dir=output, state_id="boundaries_solid", window=outer, parent_state=None, parent_signature=None, path=[])
            for index, state_id in ((1, "boundaries_glass"), (2, "boundaries_shades")):
                outer.descendants(control_type="TabItem")[index].click_input(); time.sleep(0.3)
                root, _ = _write_state(output_dir=output, state_id=state_id, window=outer, parent_state=root["state_id"], parent_signature=root["signature"], path=[])
        elif scope == "external_wall":
            native = Application(backend="win32").connect(process=int(room.process_id())).window(handle=int(outer.handle))
            top_list = next(item for item in native.children() if item.class_name() == "TListViewWithHeader" and item.rectangle().top < 300)
            if ctypes.windll.user32.SendMessageW(int(top_list.handle), 0x1004, 0, 0) == 0:
                raise RuntimeError("No boundary item exists; add Külső fal before mapping its detail branch")
            top_list.double_click_input(coords=(25, 25)); time.sleep(0.5)
            detail = _visible_window(int(room.process_id()), "TBoundaryModifyForm")
            _write_state(output_dir=output, state_id="external_wall_detail", window=detail, parent_state=None, parent_signature=None, path=[])
            _dismiss(detail)


def _run_top_menus(menus: list[str], output: Path) -> None:
    """Map selected native top menus in their own disposable project copy."""
    run_id = datetime.now(timezone.utc).strftime("menu_%Y%m%dT%H%M%SZ")
    sandbox = create_execution_sandbox(
        source_project=PROJECT_ROOT / "tests" / "testwwp.wwp",
        sandbox_root=PROJECT_ROOT / "data" / "runtime_maps" / "full_authorized_sandbox",
        run_id=run_id,
    )
    command = [sys.executable, "-m", "winwatt_automation.scripts.map_full_program",
               "--project-path", sandbox["sandbox_project"], "--safe-mode", "unsafe",
               "--top-menus", ",".join(menus), "--output-dir", str(output / "selected_top_menus"),
               "--allow-process-restart", "--max-submenu-depth", "-1"]
    completed = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    (output / "selected_top_menus.log").write_text(completed.stdout + "\n" + completed.stderr, encoding="utf-8")
    if completed.returncode:
        raise RuntimeError(f"top_menu_mapper_exit={completed.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--scope", action="append", choices=sorted(SCOPES))
    parser.add_argument("--top-menu", action="append", choices=["Fájl", "Jegyzékek", "Beállítások", "Súgó", "Szerkesztés", "Csoport", "Elem"])
    args = parser.parse_args()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (UNIFIED_ROOT / "scoped_runs" / run_id).resolve()
    output.mkdir(parents=True, exist_ok=True)
    selected = list(dict.fromkeys(args.scope or []))
    selected_menus = list(dict.fromkeys(args.top_menu or []))
    selected.extend(f"menu:{item}" for item in selected_menus)
    if not selected:
        parser.error("choose at least one --scope or --top-menu")
    write_manifest(selected_scopes=selected, active_run=output)
    write_progress(selected_scopes=selected, completed=0, run_root=output)
    notifier = subprocess.Popen([sys.executable, "-m", "winwatt_automation.scripts.room_progress_popup", "--output-dir", str(output)])
    failures = []
    try:
        for index, scope in enumerate(selected, start=1):
            try:
                if scope.startswith("menu:"):
                    _run_top_menus([scope.removeprefix("menu:")], output)
                else:
                    _run_scope(scope, args.project, output)
            except Exception as exc:  # preserve independent scopes after one UI failure
                failures.append({"scope": scope, "error": str(exc)})
            write_progress(selected_scopes=selected, completed=index, run_root=output)
    finally:
        notifier.terminate()
    (output / "result.json").write_text(json.dumps({"selected_scopes": selected, "failures": failures}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_manifest(selected_scopes=selected, active_run=output)
    print(json.dumps({"output": str(output), "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
