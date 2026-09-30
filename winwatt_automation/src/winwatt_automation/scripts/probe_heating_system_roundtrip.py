"""Create a minimal electric heating system and verify system plus heated zone."""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from winwatt_automation.version_profile import require_profile, sha256


GENERATOR_PATH = ["Egyedi fűtések", "elektromos hősugárzó, elektromos fűtőfilm"]
ENERGY_CARRIER = "elektromos áram"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--name", default="AUTO_HEATING_ROUNDTRIP")
    parser.add_argument("--expected-zone", default="AUTO_HEATED_ZONE_ROUNDTRIP")
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
        "system_name": args.name,
        "expected_zone": args.expected_zone,
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

    def select_tab(editor: Any, caption: str) -> None:
        tabs = [
            item for item in editor.descendants(control_type="TabItem")
            if item.window_text() == caption
        ]
        if len(tabs) != 1:
            raise RuntimeError(f"Expected one {caption!r} tab, found {len(tabs)}")
        tabs[0].select()
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

    def open_heated_zone(editor: Any) -> Any:
        select_tab(editor, "Zónák")
        click_unique(native(editor), "A fűtött zóna")
        return wait_window("TThermicZoneForm", 10)

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
        rect = toolbar.get_button_rect(0)
        toolbar.click_input(coords=((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2))
        dialog = wait_window("THeatingEnergyForm")
        heating = native(dialog)

        name_edits = [
            item for item in heating.descendants()
            if item.class_name() == "TEdit" and item.window_text() == "Fűtési rendszer"
            and item.is_visible() and item.is_enabled()
        ]
        if len(name_edits) != 1:
            raise RuntimeError(f"Heating name field is ambiguous: {len(name_edits)}")
        name_edits[0].set_edit_text(args.name)
        trees = [
            item for item in heating.descendants()
            if item.class_name() == "TTreeView" and item.is_visible() and item.is_enabled()
        ]
        if len(trees) != 1:
            raise RuntimeError(f"Expected one heating-generator tree, found {len(trees)}")
        tree = TreeViewWrapper(trees[0].handle)
        generator = tree.get_item(GENERATOR_PATH, exact=True)
        generator.select()
        time.sleep(.2)

        carriers = []
        for item in heating.descendants():
            if item.class_name() != "TComboBox" or not item.is_visible() or not item.is_enabled():
                continue
            combo = ComboBoxWrapper(item.handle)
            values = combo.item_texts()
            if ENERGY_CARRIER in values and len(values) > 10:
                carriers.append(combo)
        if len(carriers) != 1:
            raise RuntimeError(f"Expected one energy-carrier combo, found {len(carriers)}")
        carriers[0].select(ENERGY_CARRIER)
        time.sleep(.3)
        heating = native(dialog)
        dialog.capture_as_image().save(str(output / "heating_before_add.png"))
        click_unique(heating, "Hőtermelők listájába újként felvesz")
        time.sleep(.5)
        heating = native(dialog)
        dialog.capture_as_image().save(str(output / "heating_after_add.png"))

        area_tab = [
            item for item in dialog.descendants(control_type="TabItem")
            if item.window_text() == "Terület megadása"
        ]
        if len(area_tab) != 1:
            raise RuntimeError(f"Expected one heating area tab, found {len(area_tab)}")
        area_tab[0].select()
        time.sleep(.3)
        heating = native(dialog)
        whole_building = [
            item for item in heating.descendants()
            if item.class_name() == "TGroupButton" and item.window_text() == "Teljes épület"
            and item.is_visible() and item.is_enabled()
        ]
        if len(whole_building) != 1:
            raise RuntimeError(f"Expected one whole-building selector, found {len(whole_building)}")
        whole_building[0].click_input()
        time.sleep(.2)
        heating = native(dialog)
        click_unique(heating, "Maradék terület")
        time.sleep(.3)
        dialog.capture_as_image().save(str(output / "heating_area_selected.png"))

        other_tab = [
            item for item in dialog.descendants(control_type="TabItem")
            if item.window_text() == "A rendszer további elemei"
        ]
        if len(other_tab) != 1:
            raise RuntimeError(f"Expected one other-elements tab, found {len(other_tab)}")
        other_tab[0].select()
        time.sleep(.3)
        heating = native(dialog)
        control_combos = []
        for item in heating.descendants():
            if item.class_name() != "TComboBox" or not item.is_visible() or not item.is_enabled():
                continue
            combo = ComboBoxWrapper(item.handle)
            if "Villamos fűtés" in combo.item_texts():
                control_combos.append(combo)
        if len(control_combos) != 1:
            raise RuntimeError(f"Expected one system-control combo, found {len(control_combos)}")
        control_combos[0].select("Villamos fűtés")
        time.sleep(.3)
        heating = native(dialog)
        other_trees = sorted(
            [item for item in heating.descendants() if item.class_name() == "TTreeView" and item.is_visible()],
            key=lambda item: item.rectangle().left,
        )
        if len(other_trees) != 2:
            raise RuntimeError(f"Expected two other-elements trees, found {len(other_trees)}")
        TreeViewWrapper(other_trees[0].handle).get_item([
            "Külső fal mellett", "közvetlen elektromos fűtés", "P-szabályozóval (1 K)"
        ], exact=True).select()
        TreeViewWrapper(other_trees[1].handle).get_item(["Nincs"], exact=True).select()
        time.sleep(.3)
        dialog.capture_as_image().save(str(output / "heating_other_elements_selected.png"))

        distribution_tab = [
            item for item in dialog.descendants(control_type="TabItem")
            if item.window_text() == "Elosztóvezeték"
        ]
        if len(distribution_tab) != 1:
            raise RuntimeError(f"Expected one distribution tab, found {len(distribution_tab)}")
        distribution_tab[0].select()
        time.sleep(.3)
        heating = native(dialog)
        distribution_trees = [
            item for item in heating.descendants()
            if item.class_name() == "TTreeView" and item.is_visible() and item.is_enabled()
        ]
        if len(distribution_trees) != 3:
            raise RuntimeError(f"Expected three distribution trees, found {len(distribution_trees)}")
        for item in distribution_trees:
            TreeViewWrapper(item.handle).get_item(["Nincs"], exact=True).select()
        time.sleep(.3)
        heating = native(dialog)
        dialog.capture_as_image().save(str(output / "heating_distribution_selected.png"))
        click_unique(heating, "OK")
        time.sleep(.6)

        editor = Desktop(backend="uia").window(
            process=process_id, class_name="TBuildingModifyForm"
        ).wrapper_object()
        select_tab(editor, "Épülettechnikai rendszerek")
        report["after_create"] = system_rows(editor)
        if not any(args.name in block["rows"] for block in report["after_create"]):
            raise RuntimeError("Created heating system is absent before building commit")
        editor.capture_as_image().save(str(output / "systems_after_create.png"))
        click_unique(native(editor), "OK")
        service = WinWattService()
        service.save_project()
        report["saved_sha256"] = sha256(project)
        service.close_project_gracefully()

        from winwatt_automation.runtime_mapping.room_deep_explorer import open_sandbox_buildings
        open_sandbox_buildings(project_path=str(project))
        editor = open_sandbox_building(project_path=str(project))
        process_id = int(editor.process_id())
        select_tab(editor, "Épülettechnikai rendszerek")
        report["after_reopen"] = system_rows(editor)
        report["system_roundtrip_passed"] = any(
            args.name in block["rows"] for block in report["after_reopen"]
        )
        editor.capture_as_image().save(str(output / "systems_after_reopen.png"))

        zone_dialog = open_heated_zone(editor)
        zone_native = native(zone_dialog)
        zone_edits = [
            item for item in zone_native.descendants()
            if item.class_name() == "TEdit" and item.is_visible() and item.is_enabled()
        ]
        if len(zone_edits) != 1:
            raise RuntimeError(f"Expected one zone-name edit, found {len(zone_edits)}")
        report["reopened_zone_name"] = zone_edits[0].window_text()
        report["zone_roundtrip_passed"] = report["reopened_zone_name"] == args.expected_zone
        click_unique(zone_native, "Elvet")
        time.sleep(.3)
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        report["copy_changed"] = sha256(project) != report["source_sha256"]
        report["status"] = "passed" if all((
            report["system_roundtrip_passed"], report["zone_roundtrip_passed"],
            report["source_unchanged"], report["copy_changed"],
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
                    if window.class_name() not in {"THeatingEnergyForm", "TThermicZoneForm", "TBuildingModifyForm"}:
                        continue
                    window_native = native(window)
                    discards = [
                        item for item in window_native.descendants()
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
