"""Create the source-exact heating and HMV systems for OENY 10479210."""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from winwatt_automation.version_profile import require_profile, sha256


HEATING_GENERATOR = [
    "Egyedi fűtések",
    "gázkonvektor",
    "szabályozó nélküli, vagy csak folyamatos hőmérsékletszabályozással",
]
HEATING_CONTROL = [
    "Gázkonvektor",
    "saját, segédenergia nélküli termosztatikus szabályozással",
    "külső falnál lehelyezve",
]
HMV_GENERATOR = ["Elektromos", "átfolyós vízmelegítő, tároló"]
HMV_STORAGE = [
    "Elhelyezés a fűtött térben",
    "nappali árammal működő elektromos boyler",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--building-name", default="Üdülő sor 26.")
    args = parser.parse_args()

    profile = require_profile(args.profile)
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = output / "testwwp.wwp"
    shutil.copy2(source, project)

    import os
    from pywinauto import Desktop
    from pywinauto.controls.common_controls import ToolbarWrapper, TreeViewWrapper
    from pywinauto.controls.win32_controls import ComboBoxWrapper, ListBoxWrapper
    from winwatt_automation.runtime_mapping.room_deep_explorer import (
        open_sandbox_building,
        open_sandbox_buildings,
    )
    from winwatt_automation.live_ui.app_connector import WinWattNotRunningError
    from winwatt_automation.services.winwatt_service import WinWattService

    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    report: dict[str, Any] = {
        "schema_version": 1,
        "profile_id": profile["profile_id"],
        "source": str(source),
        "source_sha256": sha256(source),
        "project": str(project),
        "building_name": args.building_name,
        "status": "running",
        "llm_used": False,
        "heating": {
            "name": "Gázkonvektor",
            "generator_path": HEATING_GENERATOR,
            "carrier": "földgáz",
            "control_path": HEATING_CONTROL,
            "storage": ["Nincs"],
            "distribution": [["Nincs"], ["Nincs"], ["Nincs"]],
        },
        "hmv": {
            "name": "Bojler",
            "generator_path": HMV_GENERATOR,
            "carrier": "elektromos áram",
            "distribution": ["Nincs"],
            "circulation": ["nincs segédenergia igény"],
            "storage": HMV_STORAGE,
        },
    }
    process_id: int | None = None

    def checkpoint() -> None:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def native(window: Any) -> Any:
        return Desktop(backend="win32").window(handle=int(window.handle)).wrapper_object()

    def click_unique(window: Any, text: str) -> None:
        found = [
            c for c in window.descendants()
            if c.class_name() == "TButton" and c.window_text().casefold() == text.casefold()
            and c.is_visible() and c.is_enabled()
        ]
        if len(found) != 1:
            raise RuntimeError(f"Expected one enabled {text!r} button, found {len(found)}")
        found[0].click()

    def select_tab(window: Any, caption: str) -> None:
        found = [c for c in window.descendants(control_type="TabItem") if c.window_text() == caption]
        if len(found) != 1:
            raise RuntimeError(f"Expected one {caption!r} tab, found {len(found)}")
        found[0].select()
        time.sleep(.35)

    def wait_window(class_name: str, timeout: float = 12) -> Any:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = [
                w for w in Desktop(backend="uia").windows(top_level_only=True)
                if int(w.process_id()) == process_id and w.class_name() == class_name
                and w.is_visible() and w.is_enabled()
            ]
            if len(found) == 1:
                return found[0]
            time.sleep(.1)
        raise RuntimeError(f"Dialog did not appear: {class_name}")

    def systems_toolbar(editor: Any) -> ToolbarWrapper:
        toolbars = sorted(
            [c for c in native(editor).descendants() if c.class_name() == "TToolBar" and c.is_visible()],
            key=lambda c: c.rectangle().left,
        )
        if len(toolbars) != 3:
            raise RuntimeError(f"Expected three systems toolbars, found {len(toolbars)}")
        toolbar = ToolbarWrapper(toolbars[0].handle)
        if toolbar.button_count() != 8 or int(toolbar.get_button_struct(6).fsStyle) != 1:
            raise RuntimeError("Original-systems toolbar guard mismatch")
        return toolbar

    def open_system(editor: Any, index: int, class_name: str) -> Any:
        toolbar = systems_toolbar(editor)
        rect = toolbar.get_button_rect(index)
        toolbar.click_input(coords=((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2))
        return wait_window(class_name)

    def set_system_name(dialog: Any, old: str, new: str) -> None:
        found = [
            c for c in native(dialog).descendants()
            if c.class_name() == "TEdit" and c.window_text() == old
            and c.is_visible() and c.is_enabled()
        ]
        if len(found) != 1:
            raise RuntimeError(f"System name field is ambiguous: {len(found)}")
        found[0].set_edit_text(new)

    def select_carrier(dialog: Any, carrier: str) -> None:
        found = []
        for control in native(dialog).descendants():
            if control.class_name() != "TComboBox" or not control.is_visible() or not control.is_enabled():
                continue
            combo = ComboBoxWrapper(control.handle)
            if carrier in combo.item_texts():
                found.append(combo)
        if len(found) != 1:
            raise RuntimeError(f"Expected one carrier combo for {carrier!r}, found {len(found)}")
        found[0].select(carrier)
        time.sleep(.25)

    def choose_whole_building(dialog: Any) -> None:
        select_tab(dialog, "Terület megadása")
        found = [
            c for c in native(dialog).descendants()
            if c.class_name() == "TGroupButton" and c.window_text() == "Teljes épület"
            and c.is_visible() and c.is_enabled()
        ]
        if len(found) != 1:
            raise RuntimeError(f"Expected one whole-building selector, found {len(found)}")
        found[0].click_input()
        time.sleep(.2)
        click_unique(native(dialog), "Maradék terület")
        time.sleep(.3)

    def create_heating(editor: Any) -> None:
        dialog = open_system(editor, 0, "THeatingEnergyForm")
        set_system_name(dialog, "Fűtési rendszer", "Gázkonvektor")
        trees = [
            c for c in native(dialog).descendants()
            if c.class_name() == "TTreeView" and c.is_visible() and c.is_enabled()
        ]
        if len(trees) != 1:
            raise RuntimeError(f"Expected one heating generator tree, found {len(trees)}")
        TreeViewWrapper(trees[0].handle).get_item(HEATING_GENERATOR, exact=True).select()
        select_carrier(dialog, "földgáz")
        click_unique(native(dialog), "Hőtermelők listájába újként felvesz")
        choose_whole_building(dialog)

        select_tab(dialog, "A rendszer további elemei")
        controls = []
        for control in native(dialog).descendants():
            if control.class_name() != "TComboBox" or not control.is_visible() or not control.is_enabled():
                continue
            combo = ComboBoxWrapper(control.handle)
            if "Közvetlen helyiséglevegő fűtések" in combo.item_texts():
                controls.append(combo)
        if len(controls) != 1:
            raise RuntimeError(f"Expected one heating-control combo, found {len(controls)}")
        controls[0].select("Közvetlen helyiséglevegő fűtések")
        time.sleep(.3)
        trees = sorted(
            [c for c in native(dialog).descendants() if c.class_name() == "TTreeView" and c.is_visible()],
            key=lambda c: c.rectangle().left,
        )
        if len(trees) != 2:
            raise RuntimeError(f"Expected two heating other-element trees, found {len(trees)}")
        TreeViewWrapper(trees[0].handle).get_item(HEATING_CONTROL, exact=True).select()
        TreeViewWrapper(trees[1].handle).get_item(["Nincs"], exact=True).select()

        select_tab(dialog, "Elosztóvezeték")
        trees = [
            c for c in native(dialog).descendants()
            if c.class_name() == "TTreeView" and c.is_visible() and c.is_enabled()
        ]
        if len(trees) != 3:
            raise RuntimeError(f"Expected three heating distribution trees, found {len(trees)}")
        for tree in trees:
            TreeViewWrapper(tree.handle).get_item(["Nincs"], exact=True).select()
        dialog.capture_as_image().save(str(output / "heating_before_ok.png"))
        click_unique(native(dialog), "OK")
        time.sleep(.6)

    def create_hmv(editor: Any) -> None:
        dialog = open_system(editor, 1, "TWaterHeatingEnergyForm")
        set_system_name(dialog, "Melegvíz-termelő rendszer", "Bojler")
        choose_whole_building(dialog)
        select_tab(dialog, "Fogyasztás")
        houses = [
            c for c in native(dialog).descendants()
            if c.class_name() == "TGroupButton" and c.window_text() == "Családiház"
            and c.is_visible() and c.is_enabled()
        ]
        if len(houses) != 1:
            raise RuntimeError(f"Expected one family-house selector, found {len(houses)}")
        houses[0].click_input()

        select_tab(dialog, "Melegvíztermelők")
        trees = [
            c for c in native(dialog).descendants()
            if c.class_name() == "TTreeView" and c.is_visible() and c.is_enabled()
        ]
        if len(trees) != 1:
            raise RuntimeError(f"Expected one HMV generator tree, found {len(trees)}")
        TreeViewWrapper(trees[0].handle).get_item(HMV_GENERATOR, exact=True).select()
        select_carrier(dialog, "elektromos áram")
        click_unique(native(dialog), "Melegvíztermelők listájába újként felvesz")

        select_tab(dialog, "Tárolás és elosztás")
        trees = sorted(
            [c for c in native(dialog).descendants() if c.class_name() == "TTreeView" and c.is_visible()],
            key=lambda c: (c.rectangle().left, c.rectangle().top),
        )
        if len(trees) != 3:
            raise RuntimeError(f"Expected three HMV storage/distribution trees, found {len(trees)}")
        # Sorting yields distribution, circulation and then storage.
        TreeViewWrapper(trees[0].handle).get_item(["Nincs"], exact=True).select()
        TreeViewWrapper(trees[1].handle).get_item(["nincs segédenergia igény"], exact=True).select()
        TreeViewWrapper(trees[2].handle).get_item(HMV_STORAGE, exact=True).select()
        dialog.capture_as_image().save(str(output / "hmv_before_ok.png"))
        click_unique(native(dialog), "OK")
        time.sleep(.6)

    def system_rows(editor: Any) -> list[list[str]]:
        return [
            ListBoxWrapper(c.handle).item_texts()
            for c in native(editor).descendants()
            if c.class_name() == "TListBox" and c.is_visible()
        ]

    checkpoint()
    try:
        editor = open_sandbox_building(
            project_path=str(project), building_name=args.building_name
        )
        process_id = int(editor.process_id())
        select_tab(editor, "Épülettechnikai rendszerek")
        report["before"] = system_rows(editor)
        create_heating(editor)
        editor = wait_window("TBuildingModifyForm")
        select_tab(editor, "Épülettechnikai rendszerek")
        report["after_heating"] = system_rows(editor)
        create_hmv(editor)
        editor = wait_window("TBuildingModifyForm")
        select_tab(editor, "Épülettechnikai rendszerek")
        report["after_create"] = system_rows(editor)
        editor.capture_as_image().save(str(output / "systems_before_building_commit.png"))
        if not any("Gázkonvektor" in rows for rows in report["after_create"]):
            raise RuntimeError("Heating system is absent before building commit")
        if not any("Bojler" in rows for rows in report["after_create"]):
            raise RuntimeError("HMV system is absent before building commit")
        click_unique(native(editor), "OK")
        service = WinWattService()
        service.save_project()
        report["saved_sha256"] = sha256(project)
        service.close_project_gracefully()

        open_sandbox_buildings(project_path=str(project))
        editor = open_sandbox_building(
            project_path=str(project), building_name=args.building_name
        )
        process_id = int(editor.process_id())
        select_tab(editor, "Épülettechnikai rendszerek")
        report["after_reopen"] = system_rows(editor)
        report["heating_roundtrip_passed"] = any(
            "Gázkonvektor" in rows for rows in report["after_reopen"]
        )
        report["hmv_roundtrip_passed"] = any(
            "Bojler" in rows for rows in report["after_reopen"]
        )
        editor.capture_as_image().save(str(output / "systems_after_reopen.png"))
        click_unique(native(editor), "Elvet")
        service.close_project_gracefully()
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        report["copy_changed"] = sha256(project) != report["source_sha256"]
        report["status"] = "passed" if all((
            report["heating_roundtrip_passed"], report["hmv_roundtrip_passed"],
            report["source_unchanged"], report["copy_changed"],
        )) else "failed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
    finally:
        try:
            WinWattService().close_project_gracefully()
            report["session_closed"] = True
        except WinWattNotRunningError:
            report["session_closed"] = True
        except Exception as cleanup_exc:
            # The connector and service can load the same local exception
            # class through different module identities in the 32-bit worker.
            # A no-window result means the session is already closed.
            if cleanup_exc.__class__.__name__ == "WinWattNotRunningError":
                report["session_closed"] = True
            else:
                report["session_closed"] = False
                report["cleanup_error"] = repr(cleanup_exc)
        checkpoint()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
