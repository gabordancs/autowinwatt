"""Capture the ET certification editor without generating or submitting data."""
from __future__ import annotations

import argparse
import json
import os
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
    project = output / "et_inventory.wwp"
    shutil.copy2(source, project)
    source_hash = sha256(source)
    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]

    from pywinauto import Desktop, keyboard
    from pywinauto.controls.win32_controls import ComboBoxWrapper
    from winwatt_automation.runtime_mapping.et_document import open_et_document

    report: dict[str, object] = {
        "schema_version": 1,
        "profile_id": profile["profile_id"],
        "source": str(source),
        "source_sha256": source_hash,
        "project": str(project),
        "scope": "ETAction 18 editor inventory; no XML generation or submission",
        "status": "running",
    }

    try:
        dialog = open_et_document(project_path=str(project), reuse_session=False)
        process_id = int(dialog.process_id())
        dialog.capture_as_image().save(str(output / "et_document.png"))
        native = Desktop(backend="win32").window(handle=int(dialog.handle)).wrapper_object()
        controls: list[dict[str, object]] = []
        for control in native.descendants():
            try:
                if not control.is_visible():
                    continue
                rect = control.rectangle()
                item: dict[str, object] = {
                    "text": control.window_text(),
                    "class_name": control.class_name(),
                    "control_id": int(control.control_id()),
                    "enabled": bool(control.is_enabled()),
                    "rectangle": [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)],
                }
                if control.class_name() == "TComboBox":
                    combo = ComboBoxWrapper(control.handle)
                    item["values"] = combo.item_texts()
                    item["selected_index"] = combo.selected_index()
                controls.append(item)
            except Exception as exc:
                controls.append({"capture_error": repr(exc)})
        report.update({
            "window": {"title": dialog.window_text(), "class_name": dialog.class_name()},
            "controls": controls,
            "screenshot": "et_document.png",
        })
        dialog_handle = int(dialog.handle)
        dialog.set_focus()
        keyboard.send_keys("{ESC}")
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            handles = {
                int(window.handle) for window in Desktop(backend="uia").windows(top_level_only=True)
                if window.process_id() == process_id
            }
            if dialog_handle not in handles:
                break
            time.sleep(0.1)
        report["closed_without_commit"] = dialog_handle not in handles
        report["source_unchanged"] = sha256(source) == source_hash
        report["copy_unchanged"] = sha256(project) == source_hash
        report["status"] = "passed" if all((
            report["closed_without_commit"], report["source_unchanged"], report["copy_unchanged"]
        )) else "failed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
    finally:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
