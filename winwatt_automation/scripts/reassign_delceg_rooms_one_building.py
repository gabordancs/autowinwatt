"""Move every Délceg room to the existing-building record and save a copy."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path

from winwatt_automation.version_profile import require_profile, sha256


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--target-building", required=True)
    args = parser.parse_args()
    profile = require_profile(args.profile)
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = output / "delceg_one_building_envelope.wwp"
    shutil.copy2(source, project)
    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]

    from pywinauto import Application, Desktop
    from pywinauto.controls.win32_controls import ComboBoxWrapper
    from winwatt_automation.live_ui.app_connector import get_main_window, prepare_main_window_for_menu_interaction
    from winwatt_automation.runtime_mapping.room_deep_explorer import open_sandbox_buildings
    from winwatt_automation.services.winwatt_service import WinWattService

    report = {
        "schema_version": 1,
        "profile_id": profile["profile_id"],
        "source": str(source),
        "source_sha256": sha256(source),
        "project": str(project),
        "target_building": args.target_building,
        "status": "running",
    }

    def checkpoint() -> None:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    checkpoint()
    process_id = None
    try:
        open_sandbox_buildings(project_path=str(project))
        main = get_main_window()
        process_id = int(main.process_id())
        native_main = Application(backend="win32").connect(process=process_id).window(handle=int(main.handle))
        prepare_main_window_for_menu_interaction()
        tools = next(item for item in native_main.menu().items() if int(item.item_id()) == 54)
        tools.click()
        time.sleep(.2)
        next(item for item in tools.sub_menu().items() if int(item.item_id()) == 61).click()
        time.sleep(.8)
        dialogs = [
            item for item in Desktop(backend="win32").windows(top_level_only=True)
            if int(item.process_id()) == process_id and item.class_name() == "TChangeBuildingReferenceForm"
            and item.is_visible() and item.is_enabled()
        ]
        if len(dialogs) != 1:
            raise RuntimeError(f"Expected one reassign dialog, found {len(dialogs)}")
        dialog = dialogs[0]
        dialog.capture_as_image().save(str(output / "reassign_before.png"))
        all_radios = [
            item for item in dialog.descendants()
            if item.class_name() == "TRadioButton" and item.window_text() == "Mind"
            and item.is_visible() and item.is_enabled()
        ]
        if len(all_radios) != 1:
            raise RuntimeError(f"Expected one Mind radio, found {len(all_radios)}")
        all_radios[0].click_input()
        combos = [
            ComboBoxWrapper(item.handle) for item in dialog.descendants()
            if item.class_name() == "TComboBox" and item.is_visible() and item.is_enabled()
        ]
        report["combo_items"] = [combo.item_texts() for combo in combos]
        matching = [
            combo for combo in combos
            if any(value.startswith(args.target_building) for value in combo.item_texts())
        ]
        if len(matching) != 1:
            raise RuntimeError(f"Target building combo is ambiguous: {len(matching)}; {report['combo_items']!r}")
        selected_value = next(
            value for value in matching[0].item_texts() if value.startswith(args.target_building)
        )
        report["selected_building"] = selected_value
        matching[0].select(selected_value)
        time.sleep(.3)
        buttons = [
            item for item in dialog.descendants()
            if item.class_name() == "TButton" and item.window_text() == "OK"
            and item.is_visible() and item.is_enabled()
        ]
        if len(buttons) != 1:
            raise RuntimeError(f"Expected one OK button, found {len(buttons)}")
        dialog.capture_as_image().save(str(output / "reassign_ready.png"))
        buttons[0].click()
        time.sleep(.8)
        service = WinWattService()
        service.save_project()
        report["saved_sha256"] = sha256(project)
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        report["copy_changed"] = report["saved_sha256"] != report["source_sha256"]
        service.close_project_gracefully()
        open_sandbox_buildings(project_path=str(project))
        main = get_main_window()
        report["reopened"] = True
        report["status"] = "passed" if report["source_unchanged"] and report["copy_changed"] else "failed"
        WinWattService().close_project_gracefully()
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
        try:
            WinWattService().close_project_gracefully()
        except Exception:
            pass
    checkpoint()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
