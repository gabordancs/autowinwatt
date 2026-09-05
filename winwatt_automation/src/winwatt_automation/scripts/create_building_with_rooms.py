"""Create one sandbox building, three rooms, and one external wall per room.

The workflow intentionally uses a caller-created disposable ``.wwp`` file.
It is an executable verification of the previously mapped creation routes,
not a mutation of a user's working project.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pywinauto import Application, Desktop, keyboard

from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.services.winwatt_service import WinWattService
from winwatt_automation.runtime_mapping.room_deep_explorer import (
    _active_window,
    _room_list_item,
    open_sandbox_building,
    open_sandbox_room,
)


def _wait_window(process_id: int, classes: set[str], timeout: float = 8.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            window = _active_window(process_id)
            if window.class_name() in classes:
                return window
        except Exception:
            pass
        time.sleep(0.15)
    observed = _active_window(process_id)
    raise RuntimeError(f"Expected one of {sorted(classes)!r}, got {observed.class_name()!r}")


def _dismiss_room_validation_warning(process_id: int, timeout: float = 5.0) -> None:
    """Accept WinWatt's modal boundary-area validation warning when present."""
    deadline = time.monotonic() + timeout
    seen_dialog = False
    while time.monotonic() < deadline:
        try:
            dialogs = [
                item for item in Desktop(backend="win32").windows()
                if item.class_name() == "#32770" and item.is_visible()
                and int(item.process_id()) == process_id
            ]
            if not dialogs:
                # The validation dialog is posted shortly after the room
                # editor's default button.  Do not return in that race window.
                if seen_dialog:
                    return
                time.sleep(0.1)
                continue
            active = dialogs[-1]
            seen_dialog = True
            buttons = [item for item in active.descendants() if item.class_name() == "Button" and item.is_visible() and item.is_enabled()]
            ok = next((item for item in buttons if item.window_text().strip() == "OK"), None)
            if ok is None:
                raise RuntimeError(f"Unexpected WinWatt validation dialog: {active.window_text()!r}")
            Application(backend="win32").connect(process=process_id).window(handle=int(ok.handle)).click_input()
            time.sleep(0.2)
        except Exception:
            time.sleep(0.1)


def _find_visible(window: Any, control_type: str, name: str) -> Any:
    for item in window.descendants(control_type=control_type):
        if item.is_visible() and item.is_enabled() and _plain(item.window_text()) == _plain(name):
            return item
    raise LookupError(f"Missing enabled {control_type} {name!r} in {window.class_name()}")


def _find_dialog_button(window: Any, name: str) -> Any:
    """Pick a button physically owned by the dialog, not its MDI parent."""
    bounds = window.rectangle()
    candidates = [
        item for item in window.descendants(control_type="Button")
        if item.is_visible() and item.is_enabled()
        and _plain(item.window_text()) == _plain(name)
        and bounds.left <= item.rectangle().left < bounds.right
        and bounds.top <= item.rectangle().top < bounds.bottom
    ]
    if not candidates:
        raise LookupError(f"Missing dialog button {name!r} in {window.class_name()}")
    return max(candidates, key=lambda item: item.rectangle().left)


def _plain(value: str) -> str:
    # UIA occasionally returns UTF-8 text decoded as Windows-1252.  Treat
    # both that mojibake representation and genuine Hungarian text alike.
    try:
        value = value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()


def select_boundary_structure_reference(selector: Any, display_name: str) -> None:
    """Select an observed catalogue reference through the native list-view model.

    The Delphi list exposes its rows to UIA, but a UIA click leaves its native
    selected-index unset, and therefore keeps ``Felvesz...`` disabled.
    """
    process_id = int(selector.process_id())
    native = Application(backend="win32").connect(process=process_id).window(handle=int(selector.handle))
    libraries = [
        item for item in native.descendants()
        if item.class_name() == "TListViewWithHeader" and item.rectangle().top > 500
    ]
    if len(libraries) != 1:
        raise RuntimeError(f"Expected one lower construction library, found {len(libraries)}")
    library = libraries[0]
    rows = sorted(
        [item for item in selector.descendants(control_type="ListItem") if item.is_visible() and item.rectangle().top >= library.rectangle().top],
        key=lambda item: item.rectangle().top,
    )
    index = next((pos for pos, item in enumerate(rows) if _plain(item.window_text()) == _plain(display_name)), None)
    if index is None:
        raise RuntimeError(f"Structure reference is not present in the selected construction library: {display_name!r}")
    row_height = max(1, (rows[1].rectangle().top - rows[0].rectangle().top) if len(rows) > 1 else 24)
    library.click_input(coords=(30, index * row_height + row_height // 2))
    time.sleep(0.25)
    selected = ctypes.windll.user32.SendMessageW(int(library.handle), 0x100C, -1, 2)
    if selected != index:
        raise RuntimeError(f"Native construction selection failed for {display_name!r}: expected row {index}, got {selected}")


def _select_external_wall_in_library(selector: Any) -> None:
    """Backward-compatible mapped route for the older external-wall workflow."""
    select_boundary_structure_reference(selector, "Külső fal")


def _set_room_area(room: Any, area_m2: float = 10.0) -> None:
    """Set a positive floor area before adding a boundary construction."""
    edits = [item for item in room.descendants(control_type="Edit") if item.class_name() == "TEdit"]
    area = min(edits, key=lambda item: abs(item.rectangle().left - 125) + abs(item.rectangle().top - 99))
    native = Application(backend="win32").connect(process=int(room.process_id())).window(handle=int(area.handle))
    native.set_focus()
    keyboard.send_keys("^a")
    keyboard.send_keys(str(area_m2).replace(".", ","))


def _wall_x_edit(detail: Any) -> Any:
    """Return the actual ``x [m]`` edit in the boundary detail form.

    Runtime inspection proves the former column heuristic selected the nearby
    ``Darabszám`` (count) field.  X is the unique leftmost upper geometry edit;
    Y and count occupy the next column.
    """
    edits = [item for item in detail.descendants(control_type="Edit") if item.class_name() == "TEdit"]
    candidates = [edit for edit in edits if edit.rectangle().left < 160 and edit.rectangle().top < 160]
    if len(candidates) != 1:
        observed = [(item.rectangle().left, item.rectangle().top) for item in edits]
        raise RuntimeError(f"Could not uniquely identify external-wall X edit; observed={observed}")
    return candidates[0]


def _set_wall_x(detail: Any, x_m: float = 1.0) -> None:
    """Set only the requested X geometry value for a new external wall."""
    x_edit = _wall_x_edit(detail)
    app = Application(backend="win32").connect(process=int(detail.process_id()))
    native = app.window(handle=int(x_edit.handle))
    native.set_focus()
    keyboard.send_keys("^a")
    keyboard.send_keys(str(x_m).replace(".", ","))
    # Delphi commits the geometry edit on focus loss. Without this explicit
    # transition the dialog can save its default X=1 after confirmation.
    keyboard.send_keys("{TAB}")
    observed = native.window_text().replace(",", ".").strip()
    try:
        if abs(float(observed) - x_m) >= 0.0001:
            raise RuntimeError(f"External-wall X edit did not retain {x_m}; observed {observed!r}")
    except ValueError as exc:
        raise RuntimeError(f"External-wall X edit is not numeric after write: {observed!r}") from exc


def _save_project() -> None:
    """Keep changes in-session; the final Save-As is the durable commit."""


def add_external_wall(room: Any, x_m: float = 1.0) -> dict[str, Any]:
    """Add the previously verified ``Külső fal`` boundary and commit it."""
    if x_m <= 0:
        raise ValueError("x_m must be positive")
    process_id = int(room.process_id())
    _find_visible(room, "Button", "Szerkezetek...").click_input()
    selector = _wait_window(process_id, {"TSelectBoundarisForm"})

    # The catalog tree determines which construction list is displayed.
    _find_visible(selector, "TreeItem", "Szerkezetek").click_input()
    time.sleep(0.2)
    _find_visible(selector, "TreeItem", "Határoló szerkezetek").click_input()
    time.sleep(0.3)
    _select_external_wall_in_library(selector)
    _find_visible(selector, "Button", "Felvesz...").click_input()

    detail = _wait_window(process_id, {"TWallBoundaryModifyForm", "TBoundaryModifyForm"})
    boundary_form = detail.class_name()
    native_detail = Application(backend="win32").connect(process=process_id)
    fields = []
    for edit in detail.descendants(control_type="Edit"):
        if edit.class_name() != "TEdit":
            continue
        rect = edit.rectangle()
        fields.append({
            "class": edit.class_name(),
            "value": native_detail.window(handle=int(edit.handle)).window_text(),
            "rect": [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)],
        })
    detail_buttons = [
        {"text": item.window_text(), "class": item.class_name(), "enabled": bool(item.is_enabled())}
        for item in detail.descendants(control_type="Button") if item.is_visible()
    ]
    _set_wall_x(detail, x_m)
    fields_after_x = [
        {
            "value": native_detail.window(handle=int(edit.handle)).window_text(),
            "rect": [int(edit.rectangle().left), int(edit.rectangle().top), int(edit.rectangle().right), int(edit.rectangle().bottom)],
        }
        for edit in detail.descendants(control_type="Edit") if edit.class_name() == "TEdit"
    ]
    detail_ok = _find_dialog_button(detail, "OK")
    Application(backend="win32").connect(process=process_id).window(handle=int(detail_ok.handle)).click()
    # The detail form closes back to the selector.  Confirm the selector and
    # finally the room editor, so the new row is committed to the project.
    selector = _wait_window(process_id, {"TSelectBoundarisForm"})
    selector_native = Application(backend="win32").connect(process=process_id).window(handle=int(selector.handle))
    assigned_list = min(
        (item for item in selector_native.descendants() if item.class_name() == "TListViewWithHeader"),
        key=lambda item: item.rectangle().top,
    )
    assigned_count_before_selector_ok = ctypes.windll.user32.SendMessageW(int(assigned_list.handle), 0x1004, 0, 0)
    # This modal Delphi form ignores UIA Invoke in some sessions.  Its
    # default-button accelerator is reliable and must close the selector
    # before the room editor can commit the new boundary.
    ok_button = _find_dialog_button(selector, "OK")
    Application(backend="win32").connect(process=process_id).window(handle=int(ok_button.handle)).click()
    room = _wait_window(process_id, {"TRoomModifyForm"})
    room_ok = _find_dialog_button(room, "OK")
    room_ok.set_focus()
    keyboard.send_keys("{ENTER}")
    _dismiss_room_validation_warning(process_id)
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        main = get_main_window()
        try:
            if main.is_enabled() and _active_window(process_id).class_name() == "TMainForm":
                break
        except Exception:
            pass
        time.sleep(0.15)
    else:
        raise RuntimeError("Room editor did not yield to the main window before Save-As")
    _save_project()
    return {
        "room_form": room.class_name(), "boundary_form": boundary_form, "x_m": x_m,
        "boundary_fields_before_confirm": fields, "boundary_fields_after_x": fields_after_x,
        "boundary_buttons": detail_buttons,
        "assigned_count_before_selector_ok": assigned_count_before_selector_ok,
    }


def read_assigned_boundary_references(selector: Any) -> list[str]:
    """Read the selector's upper assigned list; captions are the UI identity available in v0."""
    native = Application(backend="win32").connect(process=int(selector.process_id())).window(handle=int(selector.handle))
    lists = sorted((item for item in native.descendants() if item.class_name() == "TListViewWithHeader"), key=lambda item: item.rectangle().top)
    if not lists:
        raise RuntimeError("Assigned-boundary list is not available")
    assigned = lists[0]
    rows = sorted(
        [item for item in selector.descendants(control_type="ListItem") if item.is_visible()
         and item.rectangle().top >= assigned.rectangle().top and item.rectangle().bottom <= assigned.rectangle().bottom],
        key=lambda item: item.rectangle().top,
    )
    return [item.window_text().strip() for item in rows if item.window_text().strip()]


def assign_existing_boundary_structure(room: Any, display_name: str, *, x_m: float = 1.0) -> dict[str, Any]:
    """Assign a named catalogue reference and commit it to the current room editor.

    The display name is caller data.  The mapped geometry initialization is a
    detail-form prerequisite, not a reference-name-specific UI route.
    """
    if x_m <= 0:
        raise ValueError("x_m must be positive")
    process_id = int(room.process_id())
    _find_visible(room, "Button", "Szerkezetek...").click_input()
    selector = _wait_window(process_id, {"TSelectBoundarisForm"})
    _find_visible(selector, "TreeItem", "Szerkezetek").click_input(); time.sleep(0.2)
    _find_visible(selector, "TreeItem", "Határoló szerkezetek").click_input(); time.sleep(0.3)
    select_boundary_structure_reference(selector, display_name)
    _find_visible(selector, "Button", "Felvesz...").click_input()
    detail = _wait_window(process_id, {"TWallBoundaryModifyForm", "TBoundaryModifyForm"})
    boundary_form = detail.class_name()
    _set_wall_x(detail, x_m)
    _find_dialog_button(detail, "OK").click_input()
    selector = _wait_window(process_id, {"TSelectBoundarisForm"})
    assigned_before_save = read_assigned_boundary_references(selector)
    _find_dialog_button(selector, "OK").click_input()
    room = _wait_window(process_id, {"TRoomModifyForm"})
    _find_dialog_button(room, "OK").set_focus(); keyboard.send_keys("{ENTER}")
    _dismiss_room_validation_warning(process_id)
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        main = get_main_window()
        if main.is_enabled() and _active_window(process_id).class_name() == "TMainForm":
            break
        time.sleep(0.15)
    else:
        raise RuntimeError("Room editor did not yield to the main window before Save-As")
    return {"structure_reference": display_name, "assigned_references_before_save": assigned_before_save, "boundary_form": boundary_form, "x_m": x_m}


def read_external_wall_x(room: Any) -> float:
    """Read the first assigned external wall's X dimension without editing it.

    This follows the same native selection route used for creation.  It is
    deliberately a UI readback rather than an XML/file inspection: WinWatt's
    editor is the authoritative proof that the persisted record can be used.
    """
    process_id = int(room.process_id())
    _find_visible(room, "Button", "Szerkezetek...").click_input()
    selector = _wait_window(process_id, {"TSelectBoundarisForm"})
    native_selector = Application(backend="win32").connect(process=process_id)
    assigned_list = min(
        (item for item in native_selector.window(handle=int(selector.handle)).descendants()
         if item.class_name() == "TListViewWithHeader"),
        key=lambda item: item.rectangle().top,
    )
    if ctypes.windll.user32.SendMessageW(int(assigned_list.handle), 0x1004, 0, 0) < 1:
        raise RuntimeError("No assigned boundary exists for external-wall readback")
    assigned_list.set_focus()
    keyboard.send_keys("{HOME}{SPACE}")
    time.sleep(0.2)
    _find_dialog_button(selector, "Módosít...").click_input()
    detail = _wait_window(process_id, {"TWallBoundaryModifyForm", "TBoundaryModifyForm"})
    x_edit = _wall_x_edit(detail)
    raw_x = Application(backend="win32").connect(process=process_id).window(handle=int(x_edit.handle)).window_text()
    detail.set_focus(); keyboard.send_keys("{ESC}")
    selector = _wait_window(process_id, {"TSelectBoundarisForm"})
    selector.set_focus(); keyboard.send_keys("{ESC}")
    room = _wait_window(process_id, {"TRoomModifyForm"})
    room.set_focus(); keyboard.send_keys("{ESC}")
    return float(raw_x.replace(",", "."))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--building-name", default="Automation demo building")
    parser.add_argument("--room-prefix", default="Automation demo room")
    parser.add_argument("--room-count", type=int, default=3)
    args = parser.parse_args()
    if args.room_count < 1:
        parser.error("--room-count must be at least 1")
    project = args.project.resolve()
    if "full_authorized_sandbox" not in {part.casefold() for part in project.parts}:
        parser.error("project must be in an explicitly created full_authorized_sandbox directory")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    building = open_sandbox_building(project_path=str(project), building_name=args.building_name)
    building.set_focus()
    keyboard.send_keys("{ENTER}")
    _save_project()
    result: dict[str, Any] = {
        "project": str(project), "building": args.building_name,
        "started_at": datetime.now(timezone.utc).isoformat(), "rooms": [],
    }
    for index in range(1, args.room_count + 1):
        room_name = f"{args.room_prefix} {index}"
        room = open_sandbox_room(project_path=str(project), room_name=room_name)
        _set_room_area(room)
        boundary = add_external_wall(room)
        result["rooms"].append({"name": room_name, "boundary": "Külső fal", **boundary})
    persisted = WinWattService().save_project_as(project.with_name("prepared.wwp"))
    result["project"] = str(persisted)
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
