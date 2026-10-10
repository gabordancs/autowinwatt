"""Inspect or enable a room boundary's winter weak-coupling checkbox."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import shutil
import time
from pathlib import Path

from winwatt_automation.version_profile import require_profile


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--room", required=True)
    parser.add_argument("--structure", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    profile = require_profile(args.profile)
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = output / "testwwp.wwp"
    shutil.copy2(source, project)
    source_hash = sha256(source)

    import os
    from pywinauto import Application, Desktop, keyboard
    from winwatt_automation.live_ui.app_connector import get_main_window
    from winwatt_automation.runtime_mapping.room_deep_explorer import open_sandbox_room, _active_window
    from winwatt_automation.scripts.create_building_with_rooms import _find_visible, _find_dialog_button, _wait_window
    from winwatt_automation.services.winwatt_service import WinWattService

    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    report = {
        "schema_version": 1, "status": "running", "profile_id": profile["profile_id"],
        "source": str(source), "source_sha256": source_hash, "project": str(project),
        "room": args.room, "structure": args.structure, "apply": args.apply,
    }
    process_id = None
    try:
        room = open_sandbox_room(project_path=str(project), room_name=args.room)
        process_id = int(room.process_id())
        time.sleep(1.0)
        _find_visible(room, "Button", "Szerkezetek...").click_input()
        selector = _wait_window(process_id, {"TSelectBoundarisForm"})
        tabs = sorted(
            [item for item in selector.descendants(control_type="TabItem") if item.is_visible()],
            key=lambda item: item.rectangle().left,
        )
        if tabs:
            tabs[0].click_input()
            time.sleep(0.5)
        selector.capture_as_image().save(str(output / "boundary_selector.png"))
        report["selector_tabs"] = [item.window_text() for item in tabs]
        native_selector = Application(backend="win32").connect(process=process_id).window(handle=int(selector.handle))
        from pywinauto.controls.win32_controls import ComboBoxWrapper
        combos = []
        for item in native_selector.descendants():
            if item.class_name() != "TComboBox" or not item.is_visible():
                continue
            combo = ComboBoxWrapper(item.handle)
            try:
                values = combo.item_texts()
            except Exception:
                values = []
            combos.append((item, combo, values))
        report["selector_combos"] = [
            {"selected": combo.selected_text(), "values": values,
             "rectangle": [int(item.rectangle().left), int(item.rectangle().top),
                           int(item.rectangle().right), int(item.rectangle().bottom)]}
            for item, combo, values in combos
        ]
        angle_combos = [(combo, values) for _, combo, values in combos
                        if any("vízszintes" in value.casefold() for value in values)]
        if len(angle_combos) == 1:
            angle_combo, angle_values = angle_combos[0]
            target = next(value for value in angle_values if "vízszintes" in value.casefold())
            angle_combo.select(angle_values.index(target))
            time.sleep(0.6)
            report["inclination_selected"] = angle_combo.selected_text()
            selector.capture_as_image().save(str(output / "boundary_selector_downward.png"))
        assigned = min(
            (item for item in native_selector.descendants() if item.class_name() == "TListViewWithHeader"),
            key=lambda item: item.rectangle().top,
        )
        count = ctypes.windll.user32.SendMessageW(int(assigned.handle), 0x1004, 0, 0)
        rows = sorted(
            [item for item in selector.descendants(control_type="ListItem") if item.is_visible()
             and assigned.rectangle().top <= item.rectangle().top < assigned.rectangle().bottom],
            key=lambda item: item.rectangle().top,
        )
        report["assigned_rows"] = [item.window_text() for item in rows]
        matches = [index for index, value in enumerate(report["assigned_rows"])
                   if args.structure.casefold() in value.casefold()]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one assigned row containing {args.structure!r}, found {matches}; rows={report['assigned_rows']!r}")
        assigned.set_focus()
        keyboard.send_keys("{HOME}" + "{DOWN}" * matches[0] + "{SPACE}")
        time.sleep(0.3)
        _find_dialog_button(selector, "Módosít...").click_input()
        detail = _wait_window(process_id, {"TWallBoundaryModifyForm", "TBoundaryModifyForm"})
        detail.capture_as_image().save(str(output / "boundary_detail.png"))
        native_detail = Application(backend="win32").connect(process=process_id).window(handle=int(detail.handle))
        controls = []
        for item in native_detail.descendants():
            if not item.is_visible():
                continue
            rect = item.rectangle()
            controls.append({
                "class": item.class_name(), "text": item.window_text(),
                "control_id": int(item.control_id()),
                "enabled": bool(item.is_enabled()),
                "rectangle": [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)],
                "check_state": int(item.get_check_state()) if item.class_name() in {"TCheckBox", "Button"}
                    and hasattr(item, "get_check_state") else None,
            })
        report["detail_class"] = detail.class_name()
        report["controls"] = controls
        winter = [item for item in native_detail.descendants()
                  if item.class_name() == "TCheckBox" and item.window_text().strip().casefold() == "télen"]
        report["winter_checkbox_count"] = len(winter)
        if len(winter) == 1:
            report["winter_before"] = int(winter[0].get_check_state())
            if args.apply and not report["winter_before"]:
                winter[0].click()
                time.sleep(0.3)
            report["winter_after"] = int(winter[0].get_check_state())
        if args.apply:
            if len(winter) != 1 or report.get("winter_after") != 1:
                raise RuntimeError("Winter weak-coupling checkbox was not uniquely enabled")
            _find_dialog_button(detail, "OK").click_input()
            selector = _wait_window(process_id, {"TSelectBoundarisForm"})
            _find_dialog_button(selector, "OK").click_input()
            room = _wait_window(process_id, {"TRoomModifyForm"})
            _find_dialog_button(room, "OK").set_focus(); keyboard.send_keys("{ENTER}")
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline and not get_main_window().is_enabled():
                time.sleep(0.1)
            saved = WinWattService().save_project_as(output / "project_with_weak_coupling.wwp")
            report["saved_project"] = str(saved)
        else:
            detail.set_focus(); keyboard.send_keys("{ESC}")
            selector = _wait_window(process_id, {"TSelectBoundarisForm"})
            selector.set_focus(); keyboard.send_keys("{ESC}")
            room = _wait_window(process_id, {"TRoomModifyForm"})
            room.set_focus(); keyboard.send_keys("{ESC}")
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"; report["error"] = repr(exc)
    finally:
        try:
            WinWattService().close_project_gracefully()
        except Exception as exc:
            report["close_error"] = repr(exc)
        report["source_unchanged"] = sha256(source) == source_hash
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "winter_checkbox_count": report.get("winter_checkbox_count")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
