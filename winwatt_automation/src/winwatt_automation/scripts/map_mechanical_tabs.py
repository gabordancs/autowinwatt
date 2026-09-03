"""Capture the active room mechanical tabs without entering catalogue tabs.

The resulting snapshots are intentionally a separate evidence set: radiator,
surface heating/cooling and fan-coil record editors are runtime-dependent and
must not be inferred from the adjacent catalogue tabs.
"""
from __future__ import annotations

import argparse
import json
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from pywinauto import Application, Desktop, keyboard

from winwatt_automation.runtime_mapping.room_deep_explorer import _write_state, open_sandbox_room


TABS = (
    ("radiatorok", "mechanical_radiators"),
    ("feluletfutes-hutes", "mechanical_surface_heating_cooling"),
    ("fan-coilok", "mechanical_fan_coils"),
)


def _plain(value: str) -> str:
    try:
        value = value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()


def _activate_top_tab(room, name: str) -> None:
    tabs = sorted(
        [item for item in room.descendants(control_type="TabItem") if item.rectangle().top < 60],
        key=lambda item: item.rectangle().left,
    )
    target = next(index for index, item in enumerate(tabs) if _plain(item.window_text()) == name)
    # Native keyboard navigation is more dependable than UIA Click for the
    # Delphi page control after a fresh MDI editor launch.
    page = min(
        [item for item in room.descendants() if item.class_name() == "TPageControl" and item.rectangle().top < 60],
        key=lambda item: item.rectangle().top,
    )
    page.set_focus()
    keyboard.send_keys("{HOME}" + "{RIGHT}" * target)
    time.sleep(0.8)


def _choice_dialog(process_id: int, room_handle: int):
    # The legacy database-set view opens noticeably later than its button
    # handler returns on this 32-bit WinWatt build.
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        candidates = [
            item for item in Desktop(backend="uia").windows(top_level_only=True)
            if item.process_id() == process_id and item.handle != room_handle
            and item.is_visible() and item.is_enabled()
            and item.class_name() not in {"TMainForm", "TApplication"}
        ]
        if candidates:
            return candidates[0]
        time.sleep(0.1)
    return None


def _active_room(process_id: int):
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        rooms = [
            item for item in Desktop(backend="uia").windows(top_level_only=True)
            if item.process_id() == process_id and item.class_name() == "TRoomModifyForm"
            and item.is_visible() and item.is_enabled()
        ]
        if rooms:
            return rooms[0]
        time.sleep(0.1)
    raise RuntimeError("Room editor did not return after closing a mechanical choice dialog")


def _choice_button(room):
    return next((item for item in room.descendants(control_type="Button")
                 if item.is_visible() and item.is_enabled() and _plain(item.window_text()).startswith("valasztek")), None)


def _dismiss_choice_dialog(dialog) -> None:
    cancel = next(
        (item for item in dialog.descendants(control_type="Button")
         if item.is_visible() and item.is_enabled() and _plain(item.window_text()) == "elvet"),
        None,
    )
    if cancel is None:
        raise RuntimeError(f"Choice dialog has no enabled Elvet button: {dialog.class_name()}")
    Application(backend="win32").connect(process=int(dialog.process_id())).window(handle=int(cancel.handle)).click_input()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--room-name", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tab", choices=[item[0] for item in TABS], help="Map one active mechanical tab only")
    parser.add_argument("--leave-choice-dialog-open", action="store_true",
                        help="Finish immediately after choice-dialog capture; caller terminates the disposable session")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    room = open_sandbox_room(project_path=args.project, room_name=args.room_name)
    process_id = int(room.process_id())
    evidence: list[dict[str, object]] = []
    parent = None
    selected_tabs = [item for item in TABS if args.tab is None or item[0] == args.tab]
    for caption, state_id in selected_tabs:
        room = _active_room(process_id)
        _activate_top_tab(room, caption)
        record, actions = _write_state(
            output_dir=args.output_dir,
            state_id=state_id,
            window=room,
            parent_state=parent["state_id"] if parent else None,
            parent_signature=parent["signature"] if parent else None,
            path=[],
        )
        enabled_buttons = [
            str(control["name"]) for control in record["signature"]["controls"]
            if control["control_type"] == "Button" and control["enabled"] and control["name"]
        ]
        evidence.append({"state_id": state_id, "tab": caption, "enabled_buttons": enabled_buttons})
        choice = _choice_button(room)
        if choice is not None:
            choice.click_input()
            dialog = _choice_dialog(process_id, int(room.handle))
            if dialog is not None:
                if args.leave_choice_dialog_open:
                    # TDeviceDBSetViewForm can expose a huge virtual tree to
                    # UIA. A full state_signature stalls while enumerating it,
                    # so retain a compact, native evidence snapshot instead.
                    dialog_dir = args.output_dir / "states" / f"{state_id}_choice_dialog"
                    dialog_dir.mkdir(parents=True, exist_ok=True)
                    image_path = dialog_dir / "ui.png"
                    dialog.capture_as_image().save(image_path)
                    native = Application(backend="win32").connect(process=process_id).window(handle=int(dialog.handle))
                    controls = [
                        {"class": child.class_name(), "text": child.window_text(),
                         "enabled": bool(child.is_enabled())}
                        for child in native.children()
                    ]
                    compact = {"window": {"class_name": dialog.class_name(), "title": dialog.window_text()},
                               "controls": controls, "screenshot": str(image_path)}
                    (dialog_dir / "state.json").write_text(json.dumps(compact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    evidence[-1]["choice_dialog"] = {
                        "class": compact["window"]["class_name"], "title": compact["window"]["title"],
                        "state_id": f"{state_id}_choice_dialog",
                    }
                    (args.output_dir / "mechanical_tabs_result.json").write_text(
                        json.dumps({"project": args.project, "room": args.room_name, "tabs": evidence,
                                    "finished_at": datetime.now(timezone.utc).isoformat(),
                                    "teardown": "caller_must_terminate_disposable_winwatt_session"},
                                   ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    print(json.dumps(evidence, ensure_ascii=False))
                    return 0
                dialog_record, _ = _write_state(
                    output_dir=args.output_dir,
                    state_id=f"{state_id}_choice_dialog",
                    window=dialog,
                    parent_state=record["state_id"],
                    parent_signature=record["signature"],
                    path=[],
                )
                evidence[-1]["choice_dialog"] = {
                    "class": dialog_record["window"]["class_name"],
                    "title": dialog_record["window"]["title"],
                    "state_id": dialog_record["state_id"],
                }
                _dismiss_choice_dialog(dialog)
                room = _active_room(process_id)
        parent = record
    room.set_focus(); keyboard.send_keys("{ESC}")
    (args.output_dir / "mechanical_tabs_result.json").write_text(
        json.dumps({"project": args.project, "room": args.room_name, "tabs": evidence,
                    "finished_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
