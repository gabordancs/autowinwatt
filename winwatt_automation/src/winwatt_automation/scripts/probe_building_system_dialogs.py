"""Bounded local inventory of 2023 building-system creation dialogs.

The script copies the source WWP, opens the copied test building, invokes each
creation icon from the original-systems toolbar, captures the resulting dialog,
and cancels it.  It never accepts a system and never touches the source WWP.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from winwatt_automation.version_profile import require_profile, sha256


# Verified visually against SystemsFrame icons and then checked against the
# dialog title returned by every probe. Index 6 is a separator; index 7 delete.
EXPECTED_ACTIONS = (
    "heating",
    "water_heating",
    "lighting",
    "airing",
    "cooling",
    "gain_or_loss",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    profile = require_profile(args.profile)
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    if source.suffix.casefold() != ".wwp":
        raise ValueError("Source must be a WWP project")
    output.mkdir(parents=True, exist_ok=False)
    project = output / "testwwp.wwp"
    shutil.copy2(source, project)
    (output / "version_profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    import os
    from loguru import logger
    from pywinauto import Desktop
    from pywinauto.controls.common_controls import ToolbarWrapper
    from pywinauto.controls.win32_controls import ComboBoxWrapper
    from winwatt_automation.runtime_mapping.room_deep_explorer import open_sandbox_building

    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    logger.remove()
    logger.add(str(output / "runtime.log"), level="WARNING")
    report = {
        "schema_version": 1,
        "profile_id": profile["profile_id"],
        "source": str(source),
        "source_sha256": sha256(source),
        "project": str(project),
        "status": "running",
        "scope": "original 2023 systems frame; create dialogs opened and cancelled",
        "dialogs": [],
    }

    def checkpoint() -> None:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    checkpoint()
    try:
        editor = open_sandbox_building(project_path=str(project))
        tabs = [
            tab for tab in editor.descendants(control_type="TabItem")
            if tab.window_text() == "Épülettechnikai rendszerek"
        ]
        if len(tabs) != 1:
            raise RuntimeError(f"Expected one systems tab, found {len(tabs)}")
        tabs[0].select()
        time.sleep(.4)
        native_editor = Desktop(backend="win32").window(handle=editor.handle).wrapper_object()
        toolbars = sorted(
            [c for c in native_editor.descendants() if c.class_name() == "TToolBar" and c.is_visible()],
            key=lambda c: c.rectangle().left,
        )
        if len(toolbars) != 3:
            raise RuntimeError(f"Expected three systems toolbars, found {len(toolbars)}")
        toolbar = ToolbarWrapper(toolbars[0].handle)
        if toolbar.button_count() != 8:
            raise RuntimeError(f"Unexpected original-systems toolbar shape: {toolbar.button_count()} buttons")
        separator = toolbar.get_button_struct(6)
        delete = toolbar.get_button_struct(7)
        report["toolbar_guard"] = {
            "count": toolbar.button_count(),
            "separator_style": int(separator.fsStyle),
            "delete_state": int(delete.fsState),
        }
        if int(separator.fsStyle) != 1 or int(delete.fsState) != 0:
            raise RuntimeError("Toolbar guard mismatch; refusing positional actions")

        process_id = int(editor.process_id())
        for index, expected_action in enumerate(EXPECTED_ACTIONS):
            before_handles = {
                int(w.handle) for w in Desktop(backend="uia").windows(top_level_only=True)
                if w.process_id() == process_id and w.is_visible()
            }
            # Delphi reports TBSTATE_ENABLED (value 4) correctly, but the
            # pywinauto version available to the 32-bit mapper interprets a
            # different bit as "enabled" in press_button().  Click the centre
            # returned by the native TB_GETITEMRECT query instead.
            button_rect = toolbar.get_button_rect(index)
            toolbar.click_input(coords=(
                (button_rect.left + button_rect.right) // 2,
                (button_rect.top + button_rect.bottom) // 2,
            ))
            deadline = time.monotonic() + 12
            dialog = None
            while time.monotonic() < deadline:
                candidates = [
                    w for w in Desktop(backend="uia").windows(top_level_only=True)
                    if w.process_id() == process_id and w.is_visible() and w.is_enabled()
                    and int(w.handle) not in before_handles
                ]
                if candidates:
                    candidates.sort(
                        key=lambda w: w.rectangle().width() * w.rectangle().height(), reverse=True
                    )
                    dialog = candidates[0]
                    break
                time.sleep(.1)
            if dialog is None:
                raise RuntimeError(f"No dialog opened for toolbar index {index}")

            stem = f"{index:02d}_{expected_action}"
            dialog.capture_as_image().save(str(output / f"{stem}.png"))
            native = Desktop(backend="win32").window(handle=dialog.handle).wrapper_object()
            controls = []
            for control in native.descendants():
                try:
                    if not control.is_visible():
                        continue
                    item = {
                        "text": control.window_text(),
                        "class_name": control.class_name(),
                        "control_id": control.control_id(),
                        "enabled": bool(control.is_enabled()),
                    }
                    if control.class_name() == "TComboBox":
                        combo = ComboBoxWrapper(control.handle)
                        item["values"] = combo.item_texts()
                        item["selected_index"] = combo.selected_index()
                    controls.append(item)
                except Exception as exc:
                    controls.append({"capture_error": repr(exc)})
            evidence = {
                "toolbar_index": index,
                "expected_action": expected_action,
                "title": dialog.window_text(),
                "class_name": dialog.class_name(),
                "controls": controls,
                "screenshot": f"{stem}.png",
            }
            (output / f"{stem}.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            report["dialogs"].append({k: evidence[k] for k in (
                "toolbar_index", "expected_action", "title", "class_name", "screenshot"
            )})
            checkpoint()

            cancel = [
                c for c in native.descendants()
                if c.class_name() == "TButton" and c.window_text() == "Elvet"
                and c.is_visible() and c.is_enabled()
            ]
            if len(cancel) != 1:
                raise RuntimeError(
                    f"Dialog {dialog.class_name()} has {len(cancel)} unambiguous Elvet buttons"
                )
            dialog_handle = int(dialog.handle)
            cancel[0].click()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                live_handles = {
                    int(w.handle) for w in Desktop(backend="uia").windows(top_level_only=True)
                    if w.process_id() == process_id
                }
                if dialog_handle not in live_handles:
                    break
                time.sleep(.1)
            if dialog_handle in live_handles:
                raise RuntimeError(f"Dialog did not close after Elvet: {dialog.class_name()}")
            editor = Desktop(backend="uia").window(
                process=process_id, class_name="TBuildingModifyForm"
            ).wrapper_object()
            native_editor = Desktop(backend="win32").window(handle=editor.handle).wrapper_object()
            toolbars = sorted(
                [c for c in native_editor.descendants() if c.class_name() == "TToolBar" and c.is_visible()],
                key=lambda c: c.rectangle().left,
            )
            toolbar = ToolbarWrapper(toolbars[0].handle)

        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        report["copy_unchanged"] = sha256(project) == report["source_sha256"]
        report["status"] = "passed" if report["source_unchanged"] and report["copy_unchanged"] else "failed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
    finally:
        checkpoint()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
