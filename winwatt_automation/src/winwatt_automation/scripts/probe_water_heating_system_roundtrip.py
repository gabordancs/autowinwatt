"""Create a minimal 2023 HMV system and verify its save/reopen roundtrip."""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from winwatt_automation.version_profile import require_profile, sha256


GENERATOR_PATH = ["Elektromos", "átfolyós vízmelegítő, tároló"]
ENERGY_CARRIER = "elektromos áram"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--name", default="AUTO_HMV_ROUNDTRIP")
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
    from pywinauto.controls.common_controls import ToolbarWrapper, TreeViewWrapper
    from pywinauto.controls.win32_controls import ComboBoxWrapper, ListBoxWrapper
    from winwatt_automation.runtime_mapping.room_deep_explorer import (
        open_sandbox_building,
        open_sandbox_buildings,
    )
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
        "system_name": args.name,
        "generator_path": GENERATOR_PATH,
        "energy_carrier": ENERGY_CARRIER,
        "status": "running",
    }
    process_id: int | None = None

    def checkpoint() -> None:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def native(window: Any) -> Any:
        return Desktop(backend="win32").window(handle=int(window.handle)).wrapper_object()

    def click_unique(window: Any, text: str) -> None:
        matches = [
            item for item in window.descendants()
            if item.class_name() == "TButton" and item.window_text().casefold() == text.casefold()
            and item.is_visible() and item.is_enabled()
        ]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one enabled {text!r} button, found {len(matches)}")
        matches[0].click()

    def select_tab(dialog: Any, caption: str) -> None:
        matches = [
            item for item in dialog.descendants(control_type="TabItem")
            if item.window_text() == caption
        ]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one {caption!r} tab, found {len(matches)}")
        matches[0].select()
        time.sleep(.35)

    def system_rows(editor: Any) -> list[dict[str, Any]]:
        rows = []
        for item in native(editor).descendants():
            if item.class_name() != "TListBox" or not item.is_visible():
                continue
            rect = item.rectangle()
            rows.append({
                "rectangle": [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)],
                "rows": ListBoxWrapper(item.handle).item_texts(),
            })
        return rows

    def wait_window(class_name: str, timeout: float = 12) -> Any:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            candidates = [
                window for window in Desktop(backend="uia").windows(top_level_only=True)
                if int(window.process_id()) == process_id and window.class_name() == class_name
                and window.is_visible() and window.is_enabled()
            ]
            if len(candidates) == 1:
                return candidates[0]
            time.sleep(.1)
        raise RuntimeError(f"Dialog did not appear: {class_name}")

    checkpoint()
    try:
        editor = open_sandbox_building(project_path=str(project))
        process_id = int(editor.process_id())
        select_tab(editor, "Épülettechnikai rendszerek")
        report["before"] = system_rows(editor)
        toolbars = sorted(
            [item for item in native(editor).descendants() if item.class_name() == "TToolBar" and item.is_visible()],
            key=lambda item: item.rectangle().left,
        )
        if len(toolbars) != 3:
            raise RuntimeError(f"Expected three systems toolbars, found {len(toolbars)}")
        toolbar = ToolbarWrapper(toolbars[0].handle)
        if toolbar.button_count() != 8 or int(toolbar.get_button_struct(6).fsStyle) != 1:
            raise RuntimeError("Original-systems toolbar guard mismatch")
        rect = toolbar.get_button_rect(1)
        toolbar.click_input(coords=((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2))
        dialog = wait_window("TWaterHeatingEnergyForm")
        hmv = native(dialog)

        name_edits = [
            item for item in hmv.descendants()
            if item.class_name() == "TEdit" and item.window_text() == "Melegvíz-termelő rendszer"
            and item.is_visible() and item.is_enabled()
        ]
        if len(name_edits) != 1:
            raise RuntimeError(f"HMV name field is ambiguous: {len(name_edits)}")
        name_edits[0].set_edit_text(args.name)

        select_tab(dialog, "Terület megadása")
        hmv = native(dialog)
        whole = [
            item for item in hmv.descendants()
            if item.class_name() == "TGroupButton" and item.window_text() == "Teljes épület"
            and item.is_visible() and item.is_enabled()
        ]
        if len(whole) != 1:
            raise RuntimeError(f"Expected one whole-building selector, found {len(whole)}")
        whole[0].click_input()
        time.sleep(.2)
        click_unique(native(dialog), "Maradék terület")

        select_tab(dialog, "Fogyasztás")
        hmv = native(dialog)
        houses = [
            item for item in hmv.descendants()
            if item.class_name() == "TGroupButton" and item.window_text() == "Családiház"
            and item.is_visible() and item.is_enabled()
        ]
        if len(houses) != 1:
            raise RuntimeError(f"Expected one family-house selector, found {len(houses)}")
        houses[0].click_input()
        time.sleep(.3)

        select_tab(dialog, "Melegvíztermelők")
        hmv = native(dialog)
        trees = [
            item for item in hmv.descendants()
            if item.class_name() == "TTreeView" and item.is_visible() and item.is_enabled()
        ]
        if len(trees) != 1:
            raise RuntimeError(f"Expected one HMV-generator tree, found {len(trees)}")
        TreeViewWrapper(trees[0].handle).get_item(GENERATOR_PATH, exact=True).select()
        time.sleep(.25)
        hmv = native(dialog)
        carriers = []
        for item in hmv.descendants():
            if item.class_name() != "TComboBox" or not item.is_visible() or not item.is_enabled():
                continue
            combo = ComboBoxWrapper(item.handle)
            if ENERGY_CARRIER in combo.item_texts():
                carriers.append(combo)
        if len(carriers) != 1:
            raise RuntimeError(f"Expected one HMV energy-carrier combo, found {len(carriers)}")
        carriers[0].select(ENERGY_CARRIER)
        time.sleep(.25)
        dialog.capture_as_image().save(str(output / "hmv_before_add.png"))
        click_unique(native(dialog), "Melegvíztermelők listájába újként felvesz")
        time.sleep(.4)

        select_tab(dialog, "Tárolás és elosztás")
        hmv = native(dialog)
        distribution_trees = sorted(
            [item for item in hmv.descendants() if item.class_name() == "TTreeView" and item.is_visible()],
            key=lambda item: (item.rectangle().left, item.rectangle().top),
        )
        if len(distribution_trees) != 3:
            raise RuntimeError(f"Expected three HMV distribution trees, found {len(distribution_trees)}")
        TreeViewWrapper(distribution_trees[0].handle).get_item(["Nincs"], exact=True).select()
        TreeViewWrapper(distribution_trees[1].handle).get_item(["nincs segédenergia igény"], exact=True).select()
        TreeViewWrapper(distribution_trees[2].handle).get_item(["Nincs"], exact=True).select()
        time.sleep(.3)
        dialog.capture_as_image().save(str(output / "hmv_before_ok.png"))
        click_unique(native(dialog), "OK")
        time.sleep(.6)

        editor = Desktop(backend="uia").window(process=process_id, class_name="TBuildingModifyForm").wrapper_object()
        select_tab(editor, "Épülettechnikai rendszerek")
        report["after_create"] = system_rows(editor)
        if not any(args.name in block["rows"] for block in report["after_create"]):
            raise RuntimeError("Created HMV system is absent before building commit")
        editor.capture_as_image().save(str(output / "systems_after_create.png"))
        click_unique(native(editor), "OK")
        service = WinWattService()
        service.save_project()
        report["saved_sha256"] = sha256(project)
        service.close_project_gracefully()

        open_sandbox_buildings(project_path=str(project))
        editor = open_sandbox_building(project_path=str(project))
        process_id = int(editor.process_id())
        select_tab(editor, "Épülettechnikai rendszerek")
        report["after_reopen"] = system_rows(editor)
        report["roundtrip_passed"] = any(args.name in block["rows"] for block in report["after_reopen"])
        editor.capture_as_image().save(str(output / "systems_after_reopen.png"))
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        report["copy_changed"] = sha256(project) != report["source_sha256"]
        report["status"] = "passed" if all((
            report["roundtrip_passed"], report["source_unchanged"], report["copy_changed"],
        )) else "failed"
        click_unique(native(editor), "Elvet")
        service.close_project_gracefully()
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
    finally:
        try:
            if process_id is not None:
                for window in Desktop(backend="uia").windows(top_level_only=True):
                    if int(window.process_id()) != process_id:
                        continue
                    if window.class_name() not in {"TWaterHeatingEnergyForm", "TBuildingModifyForm"}:
                        continue
                    discards = [
                        item for item in native(window).descendants()
                        if item.class_name() == "TButton" and item.window_text().casefold() == "elvet"
                        and item.is_visible() and item.is_enabled()
                    ]
                    if len(discards) == 1:
                        discards[0].click()
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
