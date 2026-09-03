"""Evidence-preserving deep mapper for a room's Nyári hőterhelés branches."""
from __future__ import annotations

import argparse
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from pywinauto import Desktop, keyboard

from winwatt_automation.runtime_mapping.room_deep_explorer import _write_state, open_sandbox_room


BRANCHES = (
    ("emberi holeadas...", "summer_human_heat"),
    ("vilagitas...", "summer_lighting"),
    ("filtracio...", "summer_filtration"),
    ("anyagmozgas...", "summer_material_movement"),
    ("egyeb hoterheles...", "summer_other_heat"),
)


def _plain(value: str) -> str:
    try:
        value = value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()


def _room(process_id: int):
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        rooms = [
            item for item in Desktop(backend="uia").windows(top_level_only=True)
            if item.process_id() == process_id and item.class_name() == "TRoomModifyForm"
            and item.is_visible() and item.is_enabled()
        ]
        if rooms:
            return rooms[0]
        time.sleep(0.1)
    raise RuntimeError("No enabled room editor is available")


def _summer_tab(room):
    return next(
        item for item in room.descendants(control_type="TabItem")
        if item.rectangle().top < 60 and _plain(item.window_text()) == "nyari hoterheles"
    )


def _button(room, name: str):
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        buttons = [
            item for item in room.descendants(control_type="Button")
            if item.is_visible() and item.is_enabled() and _plain(item.window_text()) == name
        ]
        if buttons:
            return buttons[0]
        time.sleep(0.1)
    raise RuntimeError(f"Summer button is missing after tab activation: {name}")


def _dialog(process_id: int, room_handle: int):
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        dialogs = [
            item for item in Desktop(backend="uia").windows(top_level_only=True)
            if item.process_id() == process_id and item.handle != room_handle
            and item.is_visible() and item.is_enabled()
        ]
        if dialogs:
            return dialogs[0]
        time.sleep(0.1)
    raise RuntimeError("Summer branch did not open a child window")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--room-name", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    opened = open_sandbox_room(project_path=args.project, room_name=args.room_name)
    process_id = int(opened.process_id())
    # The form exists before its nested pages are fully built.
    time.sleep(2.0)
    room = _room(process_id)
    _summer_tab(room).click_input()
    time.sleep(0.8)
    # A real branch button is the activation proof; TTabSheet visibility is
    # not reliable in this Delphi MDI application.
    _button(room, BRANCHES[0][0])
    root, _ = _write_state(
        output_dir=args.output_dir, state_id="room_summer_heat_load", window=room,
        parent_state=None, parent_signature=None, path=[],
    )
    results = []
    for caption, state_id in BRANCHES:
        room = _room(process_id)
        button = _button(room, caption)
        button.click_input()
        dialog = _dialog(process_id, int(room.handle))
        _write_state(
            output_dir=args.output_dir, state_id=state_id, window=dialog,
            parent_state=root["state_id"], parent_signature=root["signature"], path=[],
        )
        results.append({"state_id": state_id, "dialog_class": dialog.class_name(), "title": dialog.window_text()})
        dialog.set_focus()
        keyboard.send_keys("{ESC}")
        time.sleep(0.4)
    (args.output_dir / "summer_branch_result.json").write_text(
        __import__("json").dumps({"project": args.project, "room": args.room_name, "branches": results,
                                   "finished_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Mapped {len(results)} summer branches to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
