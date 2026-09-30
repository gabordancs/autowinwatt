"""Inventory the heated and cooled zone dialogs without committing changes."""
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
    from pywinauto.controls.win32_controls import ComboBoxWrapper, ListBoxWrapper
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
        "dialogs": [],
    }

    def checkpoint() -> None:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    checkpoint()
    try:
        editor = open_sandbox_building(project_path=str(project))
        process_id = int(editor.process_id())
        zones = [t for t in editor.descendants(control_type="TabItem") if t.window_text() == "Zónák"]
        if len(zones) != 1:
            raise RuntimeError(f"Expected one Zones tab, found {len(zones)}")
        zones[0].select()
        time.sleep(.35)
        native_editor = Desktop(backend="win32").window(handle=int(editor.handle)).wrapper_object()
        zone_lists = [
            {"rectangle": [int(c.rectangle().left), int(c.rectangle().top),
                           int(c.rectangle().right), int(c.rectangle().bottom)],
             "rows": ListBoxWrapper(c.handle).item_texts()}
            for c in native_editor.descendants()
            if c.class_name() == "TListBox" and c.is_visible() and c.rectangle().top < 400
        ]
        report["zone_lists"] = zone_lists

        for index, button_text in enumerate(("A fűtött zóna", "A hűtött zóna")):
            editor = Desktop(backend="uia").window(
                process=process_id, class_name="TBuildingModifyForm"
            ).wrapper_object()
            native_editor = Desktop(backend="win32").window(handle=int(editor.handle)).wrapper_object()
            buttons = [
                c for c in native_editor.descendants()
                if c.class_name() == "TButton" and c.window_text() == button_text
                and c.is_visible() and c.is_enabled()
            ]
            if len(buttons) != 1:
                raise RuntimeError(f"Expected one {button_text!r} button, found {len(buttons)}")
            before = {int(w.handle) for w in Desktop(backend="uia").windows(top_level_only=True)
                      if int(w.process_id()) == process_id}
            buttons[0].click()
            deadline = time.monotonic() + 10
            dialog = None
            while time.monotonic() < deadline:
                candidates = [
                    w for w in Desktop(backend="uia").windows(top_level_only=True)
                    if int(w.process_id()) == process_id and int(w.handle) not in before
                    and w.is_visible() and w.is_enabled()
                ]
                if candidates:
                    dialog = max(candidates, key=lambda w: w.rectangle().width() * w.rectangle().height())
                    break
                time.sleep(.1)
            if dialog is None:
                raise RuntimeError(f"No dialog opened for {button_text!r}")
            native = Desktop(backend="win32").window(handle=int(dialog.handle)).wrapper_object()
            controls = []
            for c in native.descendants():
                if not c.is_visible():
                    continue
                rect = c.rectangle()
                item = {
                    "class_name": c.class_name(), "text": c.window_text(),
                    "control_id": c.control_id(), "enabled": bool(c.is_enabled()),
                    "rectangle": [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)],
                }
                if c.class_name() == "TComboBox":
                    combo = ComboBoxWrapper(c.handle)
                    item["values"] = combo.item_texts()
                    item["selected_index"] = combo.selected_index()
                controls.append(item)
            stem = f"{index:02d}_{'heated' if index == 0 else 'cooled'}_zone"
            dialog.capture_as_image().save(str(output / f"{stem}.png"))
            evidence = {
                "trigger": button_text, "title": dialog.window_text(),
                "class_name": dialog.class_name(), "controls": controls,
                "screenshot": f"{stem}.png",
            }
            (output / f"{stem}.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            report["dialogs"].append({k: evidence[k] for k in (
                "trigger", "title", "class_name", "screenshot"
            )})
            checkpoint()
            cancel = [c for c in native.descendants() if c.class_name() == "TButton"
                      and c.window_text() == "Elvet" and c.is_visible() and c.is_enabled()]
            if len(cancel) != 1:
                raise RuntimeError(f"Expected one Elvet button in {dialog.class_name()}")
            cancel[0].click()
            time.sleep(.3)

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
