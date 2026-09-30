"""Map the 2023 heating-generator tree without accepting any change.

The probe works on a copied WWP, opens the heating-system dialog, expands the
generator catalogue, and records the control state produced by selecting each
leaf.  It never presses the add or OK buttons and closes the dialog with Elvet.
"""
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
    parser.add_argument("--max-leaves", type=int, default=256)
    args = parser.parse_args()
    if args.max_leaves <= 0:
        parser.error("--max-leaves must be positive")

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
    from pywinauto.controls.win32_controls import ComboBoxWrapper
    from winwatt_automation.runtime_mapping.room_deep_explorer import open_sandbox_building

    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    logger.remove()
    logger.add(str(output / "runtime.log"), level="WARNING")
    report: dict[str, Any] = {
        "schema_version": 1,
        "profile_id": profile["profile_id"],
        "source": str(source),
        "source_sha256": sha256(source),
        "project": str(project),
        "status": "running",
        "scope": "heating generator catalogue; selection only; dialog cancelled",
        "generators": [],
    }

    def checkpoint() -> None:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def visible_state(native: Any) -> dict[str, Any]:
        state: dict[str, Any] = {"edits": [], "combos": [], "buttons": []}
        for control in native.descendants():
            if not control.is_visible():
                continue
            cls = control.class_name()
            if cls == "TEdit":
                state["edits"].append({
                    "control_id": control.control_id(),
                    "text": control.window_text(),
                    "enabled": bool(control.is_enabled()),
                })
            elif cls == "TComboBox":
                combo = ComboBoxWrapper(control.handle)
                state["combos"].append({
                    "control_id": control.control_id(),
                    "values": combo.item_texts(),
                    "selected_index": combo.selected_index(),
                    "enabled": bool(control.is_enabled()),
                })
            elif cls == "TButton":
                state["buttons"].append({
                    "text": control.window_text(), "enabled": bool(control.is_enabled())
                })
        return state

    def collect_leaves(tree: TreeViewWrapper) -> list[tuple[list[str], Any]]:
        leaves: list[tuple[list[str], Any]] = []

        def visit(item: Any, path: list[str]) -> None:
            if len(leaves) >= args.max_leaves:
                return
            text = item.text()
            current = [*path, text]
            children = item.children()
            if not children:
                leaves.append((current, item))
                return
            item.expand()
            for child in children:
                visit(child, current)

        for root in tree.roots():
            visit(root, [])
        return leaves

    checkpoint()
    dialog_handle: int | None = None
    try:
        editor = open_sandbox_building(project_path=str(project))
        tabs = [
            item for item in editor.descendants(control_type="TabItem")
            if item.window_text() == "Épülettechnikai rendszerek"
        ]
        if len(tabs) != 1:
            raise RuntimeError(f"Expected one systems tab, found {len(tabs)}")
        tabs[0].select()
        time.sleep(.4)
        native_editor = Desktop(backend="win32").window(handle=editor.handle).wrapper_object()
        toolbars = sorted(
            [item for item in native_editor.descendants() if item.class_name() == "TToolBar" and item.is_visible()],
            key=lambda item: item.rectangle().left,
        )
        if len(toolbars) != 3:
            raise RuntimeError(f"Expected three systems toolbars, found {len(toolbars)}")
        toolbar = ToolbarWrapper(toolbars[0].handle)
        if toolbar.button_count() != 8 or int(toolbar.get_button_struct(6).fsStyle) != 1:
            raise RuntimeError("Original-systems toolbar guard mismatch")
        rect = toolbar.get_button_rect(0)
        toolbar.click_input(coords=((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2))

        process_id = int(editor.process_id())
        deadline = time.monotonic() + 12
        dialog = None
        while time.monotonic() < deadline:
            candidates = [
                window for window in Desktop(backend="uia").windows(top_level_only=True)
                if int(window.process_id()) == process_id
                and window.class_name() == "THeatingEnergyForm"
                and window.is_visible() and window.is_enabled()
            ]
            if len(candidates) == 1:
                dialog = candidates[0]
                break
            time.sleep(.1)
        if dialog is None:
            raise RuntimeError("Heating dialog did not appear")
        dialog_handle = int(dialog.handle)
        native = Desktop(backend="win32").window(handle=dialog_handle).wrapper_object()
        trees = [
            item for item in native.descendants()
            if item.class_name() == "TTreeView" and item.is_visible() and item.is_enabled()
        ]
        if len(trees) != 1:
            raise RuntimeError(f"Expected one generator tree, found {len(trees)}")
        leaves = collect_leaves(TreeViewWrapper(trees[0].handle))
        report["leaf_count"] = len(leaves)
        report["truncated"] = len(leaves) >= args.max_leaves
        for index, (path, item) in enumerate(leaves):
            item.select()
            time.sleep(.08)
            native = Desktop(backend="win32").window(handle=dialog_handle).wrapper_object()
            report["generators"].append({"index": index, "path": path, "state": visible_state(native)})
            checkpoint()
        dialog.capture_as_image().save(str(output / "heating_catalog_last_selection.png"))

        cancel = [
            item for item in native.descendants()
            if item.class_name() == "TButton" and item.window_text() == "Elvet"
            and item.is_visible() and item.is_enabled()
        ]
        if len(cancel) != 1:
            raise RuntimeError(f"Expected one enabled Elvet button, found {len(cancel)}")
        cancel[0].click()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and any(
            int(window.handle) == dialog_handle
            for window in Desktop(backend="uia").windows(top_level_only=True)
        ):
            time.sleep(.1)
        if any(
            int(window.handle) == dialog_handle
            for window in Desktop(backend="uia").windows(top_level_only=True)
        ):
            raise RuntimeError("Heating dialog did not close after Elvet")
        editors = [
            window for window in Desktop(backend="uia").windows(top_level_only=True)
            if int(window.process_id()) == process_id
            and window.class_name() == "TBuildingModifyForm" and window.is_visible()
        ]
        if len(editors) != 1:
            raise RuntimeError(f"Expected one building editor after heating probe, found {len(editors)}")
        native_editor = Desktop(backend="win32").window(handle=int(editors[0].handle)).wrapper_object()
        discard = [
            item for item in native_editor.descendants()
            if item.class_name() == "TButton" and item.window_text() == "Elvet"
            and item.is_visible() and item.is_enabled()
        ]
        if len(discard) != 1:
            raise RuntimeError(f"Expected one building Elvet button, found {len(discard)}")
        discard[0].click()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and any(
            int(window.handle) == int(editors[0].handle)
            for window in Desktop(backend="uia").windows(top_level_only=True)
        ):
            time.sleep(.1)
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        report["copy_unchanged"] = sha256(project) == report["source_sha256"]
        report["status"] = "passed" if (
            report["generators"] and report["source_unchanged"] and report["copy_unchanged"]
        ) else "failed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
    finally:
        try:
            from winwatt_automation.services.winwatt_service import WinWattService
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
