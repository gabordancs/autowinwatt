"""Create one minimal 2023 lighting system and verify its save/reopen roundtrip."""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from winwatt_automation.version_profile import require_profile, sha256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--name", default="AUTOWINWATT_LIGHTING_ROUNDTRIP")
    args = parser.parse_args()

    profile = require_profile(args.profile)
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = output / "testwwp.wwp"
    shutil.copy2(source, project)

    import os
    from pywinauto import Desktop
    from loguru import logger
    from pywinauto.controls.common_controls import ToolbarWrapper
    from pywinauto.controls.win32_controls import ListBoxWrapper
    from winwatt_automation.runtime_mapping.room_deep_explorer import (
        open_sandbox_building,
        open_sandbox_buildings,
    )
    from winwatt_automation.services.winwatt_service import WinWattService

    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    logger.remove()
    logger.add(str(output / "runtime.log"), level="WARNING")
    report = {
        "schema_version": 1,
        "profile_id": profile["profile_id"],
        "source": str(source),
        "source_sha256": sha256(source),
        "project": str(project),
        "system_name": args.name,
        "status": "running",
    }

    def checkpoint() -> None:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def select_systems_tab(editor):
        choices = [
            tab for tab in editor.descendants(control_type="TabItem")
            if tab.window_text() == "Épülettechnikai rendszerek"
        ]
        if len(choices) != 1:
            raise RuntimeError(f"Expected one systems tab, found {len(choices)}")
        choices[0].select()
        time.sleep(.35)

    def native_editor(editor):
        return Desktop(backend="win32").window(handle=int(editor.handle)).wrapper_object()

    def click_lighting_create(editor) -> None:
        native = native_editor(editor)
        toolbars = sorted(
            [c for c in native.descendants() if c.class_name() == "TToolBar" and c.is_visible()],
            key=lambda c: c.rectangle().left,
        )
        if len(toolbars) != 3:
            raise RuntimeError(f"Expected three system toolbars, found {len(toolbars)}")
        toolbar = ToolbarWrapper(toolbars[0].handle)
        if toolbar.button_count() != 8:
            raise RuntimeError("Original-system toolbar shape changed")
        if int(toolbar.get_button_struct(6).fsStyle) != 1:
            raise RuntimeError("Original-system toolbar separator moved")
        rect = toolbar.get_button_rect(2)
        toolbar.click_input(coords=((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2))

    def wait_dialog(process_id: int, class_name: str, timeout: float = 10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            candidates = [
                w for w in Desktop(backend="uia").windows(top_level_only=True)
                if int(w.process_id()) == process_id and w.class_name() == class_name
                and w.is_visible() and w.is_enabled()
            ]
            if len(candidates) == 1:
                return candidates[0]
            time.sleep(.1)
        raise RuntimeError(f"Dialog did not appear: {class_name}")

    def click_unique_native_button(window, text: str) -> None:
        native = Desktop(backend="win32").window(handle=int(window.handle)).wrapper_object()
        buttons = [
            c for c in native.descendants()
            if c.class_name() == "TButton" and c.window_text() == text
            and c.is_visible() and c.is_enabled()
        ]
        if len(buttons) != 1:
            raise RuntimeError(f"Expected one enabled {text!r} button, found {len(buttons)}")
        buttons[0].click()

    def visible_list_rows(editor) -> list[dict]:
        rows = []
        for control in native_editor(editor).descendants():
            if control.class_name() != "TListBox" or not control.is_visible():
                continue
            values = ListBoxWrapper(control.handle).item_texts()
            rect = control.rectangle()
            rows.append({
                "rectangle": [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)],
                "rows": values,
            })
        return rows

    checkpoint()
    try:
        editor = open_sandbox_building(project_path=str(project))
        process_id = int(editor.process_id())
        select_systems_tab(editor)
        report["before"] = visible_list_rows(editor)
        click_lighting_create(editor)
        dialog = wait_dialog(process_id, "TLightingEnergyForm")
        native = Desktop(backend="win32").window(handle=int(dialog.handle)).wrapper_object()
        name_edits = [
            c for c in native.descendants()
            if c.class_name() == "TEdit" and c.window_text() == "Világítási rendszer"
            and c.is_visible() and c.is_enabled()
        ]
        if len(name_edits) != 1:
            raise RuntimeError(f"Lighting name field is ambiguous: {len(name_edits)} candidates")
        name_edits[0].set_edit_text(args.name)
        dialog.capture_as_image().save(str(output / "lighting_before_ok.png"))
        click_unique_native_button(dialog, "OK")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if not any(
                int(w.process_id()) == process_id and w.class_name() == "TLightingEnergyForm"
                for w in Desktop(backend="uia").windows(top_level_only=True)
            ):
                break
            time.sleep(.1)
        else:
            raise RuntimeError("Lighting dialog did not close after OK")

        editor = Desktop(backend="uia").window(
            process=process_id, class_name="TBuildingModifyForm"
        ).wrapper_object()
        select_systems_tab(editor)
        report["after_create"] = visible_list_rows(editor)
        if not any(args.name in item["rows"] for item in report["after_create"]):
            raise RuntimeError("Created lighting system is absent before building commit")
        editor.capture_as_image().save(str(output / "systems_after_create.png"))
        click_unique_native_button(editor, "OK")
        service = WinWattService()
        service.save_project()
        report["saved_sha256"] = sha256(project)
        service.close_project_gracefully()

        open_sandbox_buildings(project_path=str(project))
        editor = open_sandbox_building(project_path=str(project))
        select_systems_tab(editor)
        report["after_reopen"] = visible_list_rows(editor)
        report["roundtrip_passed"] = any(
            args.name in item["rows"] for item in report["after_reopen"]
        )
        editor.capture_as_image().save(str(output / "systems_after_reopen.png"))
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        report["copy_changed"] = sha256(project) != report["source_sha256"]
        report["status"] = "passed" if (
            report["roundtrip_passed"] and report["source_unchanged"] and report["copy_changed"]
        ) else "failed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
    finally:
        checkpoint()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
