"""Inspect source-exact OENY heating/HMV choices without committing changes."""
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
HMV_GENERATOR = ["Elektromos", "átfolyós vízmelegítő, tároló"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--system", required=True, choices=("heating", "hmv"))
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
    from pywinauto.controls.win32_controls import ComboBoxWrapper
    from winwatt_automation.runtime_mapping.room_deep_explorer import open_sandbox_building
    from winwatt_automation.live_ui.app_connector import WinWattNotRunningError
    from winwatt_automation.services.winwatt_service import WinWattService

    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    report: dict[str, Any] = {
        "schema_version": 1,
        "profile_id": profile["profile_id"],
        "source": str(source),
        "source_sha256": sha256(source),
        "project": str(project),
        "system": args.system,
        "status": "running",
        "llm_used": False,
    }
    process_id: int | None = None

    def checkpoint() -> None:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def native(window: Any) -> Any:
        return Desktop(backend="win32").window(handle=int(window.handle)).wrapper_object()

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

    def click_unique(window: Any, text: str) -> None:
        found = [
            c for c in window.descendants()
            if c.class_name() == "TButton" and c.window_text().casefold() == text.casefold()
            and c.is_visible() and c.is_enabled()
        ]
        if len(found) != 1:
            raise RuntimeError(f"Expected one enabled {text!r} button, found {len(found)}")
        found[0].click()

    def select_tab(dialog: Any, caption: str) -> None:
        found = [c for c in dialog.descendants(control_type="TabItem") if c.window_text() == caption]
        if len(found) != 1:
            raise RuntimeError(f"Expected one {caption!r} tab, found {len(found)}")
        found[0].select()
        time.sleep(.35)

    def tree_paths(tree: TreeViewWrapper) -> list[list[str]]:
        result: list[list[str]] = []

        def visit(item: Any, prefix: list[str]) -> None:
            path = [*prefix, item.text()]
            children = item.children()
            if not children:
                result.append(path)
                return
            item.expand()
            for child in children:
                visit(child, path)

        for root in tree.roots():
            visit(root, [])
        return result

    def capture_state(dialog: Any, label: str) -> dict[str, Any]:
        current = native(dialog)
        state: dict[str, Any] = {"label": label, "combos": [], "trees": [], "edits": []}
        def rect_values(control: Any) -> list[int]:
            rect = control.rectangle()
            return [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)]
        for control in current.descendants():
            if not control.is_visible():
                continue
            if control.class_name() == "TComboBox":
                combo = ComboBoxWrapper(control.handle)
                state["combos"].append({
                    "rect": rect_values(control),
                    "selected": combo.window_text(),
                    "values": combo.item_texts(),
                    "enabled": bool(control.is_enabled()),
                })
            elif control.class_name() == "TTreeView" and control.is_enabled():
                state["trees"].append({
                    "rect": rect_values(control),
                    "paths": tree_paths(TreeViewWrapper(control.handle)),
                })
            elif control.class_name() == "TEdit":
                state["edits"].append({
                    "rect": rect_values(control),
                    "text": control.window_text(),
                    "enabled": bool(control.is_enabled()),
                })
        dialog.capture_as_image().save(str(output / f"{label}.png"))
        return state

    checkpoint()
    try:
        editor = open_sandbox_building(
            project_path=str(project), building_name=args.building_name
        )
        process_id = int(editor.process_id())
        select_tab(editor, "Épülettechnikai rendszerek")
        native_editor = native(editor)
        toolbars = sorted(
            [c for c in native_editor.descendants() if c.class_name() == "TToolBar" and c.is_visible()],
            key=lambda c: c.rectangle().left,
        )
        if len(toolbars) != 3:
            raise RuntimeError(f"Expected three systems toolbars, found {len(toolbars)}")
        toolbar = ToolbarWrapper(toolbars[0].handle)
        button_index = 0 if args.system == "heating" else 1
        rect = toolbar.get_button_rect(button_index)
        toolbar.click_input(coords=((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2))

        dialog = wait_window("THeatingEnergyForm" if args.system == "heating" else "TWaterHeatingEnergyForm")
        if args.system == "hmv":
            select_tab(dialog, "Terület megadása")
            current = native(dialog)
            whole = [
                c for c in current.descendants()
                if c.class_name() == "TGroupButton" and c.window_text() == "Teljes épület"
                and c.is_visible() and c.is_enabled()
            ]
            if len(whole) != 1:
                raise RuntimeError(f"Expected one whole-building selector, found {len(whole)}")
            whole[0].click_input()
            click_unique(native(dialog), "Maradék terület")
            select_tab(dialog, "Fogyasztás")
            current = native(dialog)
            houses = [
                c for c in current.descendants()
                if c.class_name() == "TGroupButton" and c.window_text() == "Családiház"
                and c.is_visible() and c.is_enabled()
            ]
            if len(houses) != 1:
                raise RuntimeError(f"Expected one family-house selector, found {len(houses)}")
            houses[0].click_input()
            select_tab(dialog, "Melegvíztermelők")

        current = native(dialog)
        trees = [
            c for c in current.descendants()
            if c.class_name() == "TTreeView" and c.is_visible() and c.is_enabled()
        ]
        if len(trees) != 1:
            raise RuntimeError(f"Expected one generator tree, found {len(trees)}")
        generator_path = HEATING_GENERATOR if args.system == "heating" else HMV_GENERATOR
        TreeViewWrapper(trees[0].handle).get_item(generator_path, exact=True).select()
        time.sleep(.3)
        current = native(dialog)
        carrier = "földgáz" if args.system == "heating" else "elektromos áram"
        carriers = []
        for control in current.descendants():
            if control.class_name() != "TComboBox" or not control.is_visible() or not control.is_enabled():
                continue
            combo = ComboBoxWrapper(control.handle)
            if carrier in combo.item_texts():
                carriers.append(combo)
        if len(carriers) != 1:
            raise RuntimeError(f"Expected one carrier combo for {carrier!r}, found {len(carriers)}")
        carriers[0].select(carrier)
        click_unique(
            native(dialog),
            "Hőtermelők listájába újként felvesz"
            if args.system == "heating" else "Melegvíztermelők listájába újként felvesz",
        )
        time.sleep(.5)

        report["generator_path"] = generator_path
        report["generator_state"] = capture_state(dialog, "generator_added")
        if args.system == "heating":
            select_tab(dialog, "A rendszer további elemei")
            current = native(dialog)
            controls = []
            for control in current.descendants():
                if control.class_name() != "TComboBox" or not control.is_visible() or not control.is_enabled():
                    continue
                combo = ComboBoxWrapper(control.handle)
                if "Közvetlen helyiséglevegő fűtések" in combo.item_texts():
                    controls.append(combo)
            if len(controls) != 1:
                raise RuntimeError(f"Expected one heating-control combo, found {len(controls)}")
            controls[0].select("Közvetlen helyiséglevegő fűtések")
            time.sleep(.4)
            report["other_elements"] = capture_state(dialog, "heating_other_elements")
            select_tab(dialog, "Elosztóvezeték")
            report["distribution"] = capture_state(dialog, "heating_distribution")
        else:
            select_tab(dialog, "Tárolás és elosztás")
            report["storage_distribution"] = capture_state(dialog, "hmv_storage_distribution")

        click_unique(native(dialog), "Elvet")
        time.sleep(.5)
        editor = wait_window("TBuildingModifyForm")
        click_unique(native(editor), "Elvet")
        time.sleep(.5)
        WinWattService().close_project_gracefully()
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        report["copy_unchanged"] = sha256(project) == report["source_sha256"]
        report["status"] = "passed" if report["source_unchanged"] and report["copy_unchanged"] else "failed"
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
            report["session_closed"] = False
            report["cleanup_error"] = repr(cleanup_exc)
        checkpoint()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
