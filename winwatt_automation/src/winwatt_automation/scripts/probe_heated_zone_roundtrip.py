"""Create one whole-building heated zone on a copy and verify save/reopen."""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from winwatt_automation.version_profile import require_profile, sha256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--name", default="AUTO_HEATED_ZONE_ROUNDTRIP")
    args = parser.parse_args()

    profile = require_profile(args.profile)
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = output / "testwwp.wwp"
    shutil.copy2(source, project)

    import os
    from loguru import logger
    from pywinauto import Desktop
    from pywinauto.controls.win32_controls import ListBoxWrapper
    from winwatt_automation.runtime_mapping.room_deep_explorer import open_sandbox_building
    from winwatt_automation.services.winwatt_service import WinWattService

    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    logger.remove()
    logger.add(str(output / "runtime.log"), level="WARNING")
    report: dict[str, Any] = {
        "schema_version": 1,
        "profile_id": profile["profile_id"],
        "source": str(source),
        "source_sha256": sha256(source),
        "project": str(project),
        "zone_name": args.name,
        "status": "running",
    }

    def checkpoint() -> None:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def click_unique(native: Any, text: str) -> None:
        matches = [
            item for item in native.descendants()
            if item.class_name() == "TButton" and item.window_text().casefold() == text.casefold()
            and item.is_visible() and item.is_enabled()
        ]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one enabled {text!r} button, found {len(matches)}")
        matches[0].click()

    def select_zones_tab(editor: Any) -> None:
        tabs = [
            item for item in editor.descendants(control_type="TabItem")
            if item.window_text() == "Zónák"
        ]
        if len(tabs) != 1:
            raise RuntimeError(f"Expected one Zones tab, found {len(tabs)}")
        tabs[0].select()
        time.sleep(.35)

    def visible_rows(editor: Any) -> list[dict[str, Any]]:
        native = Desktop(backend="win32").window(handle=int(editor.handle)).wrapper_object()
        rows = []
        for item in native.descendants():
            if item.class_name() != "TListBox" or not item.is_visible():
                continue
            rect = item.rectangle()
            rows.append({
                "rectangle": [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)],
                "rows": ListBoxWrapper(item.handle).item_texts(),
            })
        return rows

    def open_heated_zone_dialog(editor: Any) -> Any:
        native_editor = Desktop(backend="win32").window(handle=int(editor.handle)).wrapper_object()
        click_unique(native_editor, "A fűtött zóna")
        process_id = int(editor.process_id())
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            candidates = [
                window for window in Desktop(backend="uia").windows(top_level_only=True)
                if int(window.process_id()) == process_id
                and window.class_name() == "TThermicZoneForm"
                and window.is_visible() and window.is_enabled()
            ]
            if len(candidates) == 1:
                return candidates[0]
            time.sleep(.1)
        raise RuntimeError("Heated-zone dialog did not appear")

    checkpoint()
    try:
        editor = open_sandbox_building(project_path=str(project))
        process_id = int(editor.process_id())
        select_zones_tab(editor)
        report["before"] = visible_rows(editor)
        dialog = open_heated_zone_dialog(editor)
        native = Desktop(backend="win32").window(handle=int(dialog.handle)).wrapper_object()
        edits = [
            item for item in native.descendants()
            if item.class_name() == "TEdit" and item.is_visible() and item.is_enabled()
        ]
        if len(edits) != 1:
            raise RuntimeError(f"Expected one zone-name edit, found {len(edits)}")
        edits[0].set_edit_text(args.name)
        whole_building = [
            item for item in native.descendants()
            if item.class_name() == "TGroupButton" and item.window_text() == "Teljes épület"
            and item.is_visible() and item.is_enabled()
        ]
        if len(whole_building) != 1:
            raise RuntimeError(f"Expected one whole-building selector, found {len(whole_building)}")
        whole_building[0].click()
        dialog.capture_as_image().save(str(output / "heated_zone_before_ok.png"))
        click_unique(native, "Ok")
        time.sleep(.5)

        editor = Desktop(backend="uia").window(
            process=process_id, class_name="TBuildingModifyForm"
        ).wrapper_object()
        select_zones_tab(editor)
        report["after_create"] = visible_rows(editor)
        editor.capture_as_image().save(str(output / "zones_after_create.png"))
        native_editor = Desktop(backend="win32").window(handle=int(editor.handle)).wrapper_object()
        click_unique(native_editor, "OK")
        service = WinWattService()
        service.save_project()
        report["saved_sha256"] = sha256(project)
        service.close_project_gracefully()

        from winwatt_automation.runtime_mapping.room_deep_explorer import open_sandbox_buildings
        open_sandbox_buildings(project_path=str(project))
        editor = open_sandbox_building(project_path=str(project))
        select_zones_tab(editor)
        report["after_reopen"] = visible_rows(editor)
        editor.capture_as_image().save(str(output / "zones_after_reopen.png"))
        dialog = open_heated_zone_dialog(editor)
        native = Desktop(backend="win32").window(handle=int(dialog.handle)).wrapper_object()
        reopened_edits = [
            item for item in native.descendants()
            if item.class_name() == "TEdit" and item.is_visible() and item.is_enabled()
        ]
        if len(reopened_edits) != 1:
            raise RuntimeError(f"Expected one reopened zone-name edit, found {len(reopened_edits)}")
        report["reopened_zone_name"] = reopened_edits[0].window_text()
        report["roundtrip_passed"] = report["reopened_zone_name"] == args.name
        dialog.capture_as_image().save(str(output / "heated_zone_after_reopen.png"))
        click_unique(native, "Elvet")
        time.sleep(.3)
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        report["copy_changed"] = sha256(project) != report["source_sha256"]
        report["status"] = "passed" if (
            report["roundtrip_passed"] and report["source_unchanged"] and report["copy_changed"]
        ) else "failed"
        native_editor = Desktop(backend="win32").window(handle=int(editor.handle)).wrapper_object()
        click_unique(native_editor, "Elvet")
        service.close_project_gracefully()
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
    finally:
        try:
            if "process_id" in locals():
                for window in Desktop(backend="uia").windows(top_level_only=True):
                    if int(window.process_id()) != process_id:
                        continue
                    if window.class_name() not in {"TThermicZoneForm", "TBuildingModifyForm"}:
                        continue
                    native = Desktop(backend="win32").window(handle=int(window.handle)).wrapper_object()
                    discard = [
                        item for item in native.descendants()
                        if item.class_name() == "TButton" and item.window_text().casefold() == "elvet"
                        and item.is_visible() and item.is_enabled()
                    ]
                    if len(discard) == 1:
                        discard[0].click()
                        time.sleep(.3)
                if any(
                    int(window.process_id()) == process_id and window.class_name() == "TMainForm"
                    for window in Desktop(backend="uia").windows(top_level_only=True)
                ):
                    WinWattService().close_project_gracefully()
                report["session_closed"] = True
        except Exception as cleanup_exc:
            report["session_closed"] = False
            report["cleanup_error"] = repr(cleanup_exc)
        checkpoint()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
