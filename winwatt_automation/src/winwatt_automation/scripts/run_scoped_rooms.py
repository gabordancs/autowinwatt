"""Run user-selected, evidence-preserving room mapping scopes."""
from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
import time
import unicodedata
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


def _plain(value: str) -> str:
    """Compare native Hungarian captions despite occasional UIA mojibake."""
    try:
        value = value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()


def _visible_button(window, caption: str, timeout: float = 4.0):
    """Wait for a lazily-created Delphi button, then return it."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        buttons = [
            item for item in window.descendants(control_type="Button")
            if item.is_visible() and item.is_enabled() and _plain(item.window_text()) == _plain(caption)
        ]
        if buttons:
            return buttons[0]
        time.sleep(0.1)
    raise LookupError(f"Missing enabled button {caption!r} in {window.class_name()}")


def _visible_window(process_id: int, class_name: str):
    return next(
        item for item in Desktop(backend="uia").windows(top_level_only=True)
        if item.process_id() == process_id and item.class_name() == class_name and item.is_visible() and item.is_enabled()
    )


def _wait_child_dialog(room, timeout: float = 4.0):
    """Wait for a legacy modal which WinWatt may create asynchronously."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        dialogs = [
            item for item in Desktop(backend="uia").windows(top_level_only=True)
            if item.process_id() == room.process_id() and item.handle != room.handle
            and item.is_visible() and item.is_enabled()
        ]
        if dialogs:
            return dialogs[0]
        time.sleep(0.1)
    raise RuntimeError("Timed out waiting for the summer-detail dialog")


def _dismiss(window) -> None:
    window.set_focus()
    keyboard.send_keys("{ESC}")
    time.sleep(0.35)


def _open_boundaries(room):
    button = _visible_button(room, "Szerkezetek...")
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


def _capture_tab_named(room, caption: str, state_id: str, output: Path, parent: dict | None = None) -> dict:
    """Select a top-level room tab by its caption.

    Delphi reports several tab sheets as visible, so ``TTabSheet`` visibility
    is not a valid activation signal.  Callers verify activation through the
    controls unique to the selected sheet instead.
    """
    tab = next(
        item for item in room.descendants(control_type="TabItem")
        if item.rectangle().top < 60 and _plain(item.window_text()) == _plain(caption)
    )
    native_room = Application(backend="win32").connect(process=int(room.process_id())).window(handle=int(room.handle))
    page_control = min(
        (item for item in native_room.descendants() if item.class_name() == "TPageControl" and item.rectangle().top < 60),
        key=lambda item: item.rectangle().top,
    )
    tabs = sorted(
        (item for item in room.descendants(control_type="TabItem") if item.rectangle().top < 60),
        key=lambda item: item.rectangle().left,
    )
    target_index = next(index for index, item in enumerate(tabs) if item.handle == tab.handle)
    # The virtual UIA tab can swallow pointer events during MDI construction.
    # TPageControl's native keyboard navigation is stable: Home selects the
    # first page and Right advances one page at a time.
    page_control.set_focus()
    keyboard.send_keys("{HOME}" + "{RIGHT}" * target_index)
    time.sleep(0.8)
    record, _ = _write_state(
        output_dir=output, state_id=state_id, window=room,
        parent_state=parent["state_id"] if parent else None,
        parent_signature=parent["signature"] if parent else None, path=[],
    )
    return record


def _run_scope(scope: str, project: str, output: Path, room_name: str) -> None:
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
    room = open_sandbox_room(project_path=project, room_name=room_name)
    # ``open_sandbox_room`` returns when the MDI form exists, while Delphi
    # continues creating its tab-page controls for a short time afterwards.
    # Activating a tab in that interval is silently ignored by WinWatt.
    time.sleep(2.0)
    # Reacquire the top-level wrapper after Delphi has completed its MDI
    # construction; the wrapper returned by the opener can have a stale child
    # tree even though the native window is already ready.
    room = _visible_window(int(room.process_id()), "TRoomModifyForm")
    _run_room_scope(scope, room, output)


def _run_room_scope(scope: str, room, output: Path) -> None:
    if scope == "general":
        _capture_tab_named(room, "altalanos adatok", "room_general", output)
    elif scope == "winter":
        _capture_tab_named(room, "teli hoszukseglet", "room_winter_heat_need", output)
    elif scope == "summer":
        parent = _capture_tab_named(room, "nyari hoterheles", "room_summer_heat_load", output)
        for caption, state_id in (
            ("Emberi hőleadás...", "summer_human_heat"), ("Világítás...", "summer_lighting"),
            ("Filtráció...", "summer_filtration"), ("Anyagmozgás...", "summer_material_movement"),
            ("Egyéb hőterhelés...", "summer_other_heat"),
        ):
            # Keep the comparison key ASCII-only; the installed WinWatt UI
            # exposes the long Hungarian captions in more than one encoding.
            caption = {
                "summer_human_heat": "emberi holeadas...",
                "summer_lighting": "vilagitas...",
                "summer_filtration": "filtracio...",
                "summer_material_movement": "anyagmozgas...",
                "summer_other_heat": "egyeb hoterheles...",
            }[state_id]
            print(f"SUMMER_BRANCH_OPEN state_id={state_id} caption={caption}", flush=True)
            button = _visible_button(room, caption)
            print(f"SUMMER_BRANCH_SELECTED state_id={state_id} handle={int(button.handle)}", flush=True)
            # WinWatt's Delphi buttons are most reliable through their native
            # handle; UIA Invoke and keyboard activation can be ignored while
            # the MDI editor owns focus.
            Application(backend="win32").connect(process=int(room.process_id())).window(handle=int(button.handle)).click_input()
            print(f"SUMMER_BRANCH_ACTIVATED state_id={state_id}", flush=True)
            dialog = _wait_child_dialog(room)
            print(f"SUMMER_BRANCH_DIALOG state_id={state_id} class={dialog.class_name()}", flush=True)
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
            # The selector contains both the upper, assigned-boundaries list
            # and the lower construction-library list.  ``children()`` order
            # is unstable, so choose the physically upper list explicitly.
            top_list = min(
                (item for item in native.descendants() if item.class_name() == "TListViewWithHeader"),
                key=lambda item: item.rectangle().top,
            )
            if ctypes.windll.user32.SendMessageW(int(top_list.handle), 0x1004, 0, 0) == 0:
                raise RuntimeError("No boundary item exists; add Külső fal before mapping its detail branch")
            # First select the assigned row through the native list.  The
            # selector keeps Módosít disabled until its own selection state is
            # set; UIA/mouse clicks do not always set that Delphi state.  Its
            # keyboard selection path does.
            top_list.set_focus()
            keyboard.send_keys("{HOME}")
            keyboard.send_keys("{SPACE}")
            time.sleep(0.2)
            modify = next(
                item for item in outer.descendants(control_type="Button")
                if item.is_visible() and item.is_enabled() and item.window_text() == "Módosít..."
            )
            modify.click_input(); time.sleep(0.5)
            process_id = int(room.process_id())
            try:
                detail = _visible_window(process_id, "TWallBoundaryModifyForm")
            except StopIteration:
                detail = _visible_window(process_id, "TBoundaryModifyForm")
            native_detail = Application(backend="win32").connect(process=process_id)
            readback = []
            for edit in detail.descendants(control_type="Edit"):
                if edit.class_name() != "TEdit":
                    continue
                rect = edit.rectangle()
                readback.append({
                    "value": native_detail.window(handle=int(edit.handle)).window_text(),
                    "rect": [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)],
                })
            (output / "external_wall_readback.json").write_text(
                json.dumps({"form_class": detail.class_name(), "fields": readback}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
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
    parser.add_argument("--room-name", default="Room graph explorer")
    parser.add_argument("--scope", action="append", choices=sorted(SCOPES))
    parser.add_argument("--no-status-popup", action="store_true", help="Run without the Tk progress card (useful for focus diagnostics).")
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
    notifier = None if args.no_status_popup else subprocess.Popen(
        [sys.executable, "-m", "winwatt_automation.scripts.room_progress_popup", "--output-dir", str(output)]
    )
    failures = []
    try:
        for index, scope in enumerate(selected, start=1):
            try:
                if scope.startswith("menu:"):
                    _run_top_menus([scope.removeprefix("menu:")], output)
                else:
                    _run_scope(scope, args.project, output, args.room_name)
            except Exception as exc:  # preserve independent scopes after one UI failure
                failures.append({"scope": scope, "error": f"{type(exc).__name__}: {exc}"})
            write_progress(selected_scopes=selected, completed=index, run_root=output)
    finally:
        if notifier is not None:
            notifier.terminate()
    (output / "result.json").write_text(json.dumps({"selected_scopes": selected, "failures": failures}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_manifest(selected_scopes=selected, active_run=output)
    print(json.dumps({"output": str(output), "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
