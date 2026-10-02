"""Prove the configured ET scope and capture the next wizard page."""
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
    parser.add_argument("--building-name")
    parser.add_argument("--zone-name")
    parser.add_argument("--structure-scope", choices=("all", "heated_boundary"), default="all")
    args = parser.parse_args()

    profile = require_profile(args.profile)
    source = args.source.resolve(strict=True)
    source_hash = sha256(source)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = output / "full_authorized_sandbox" / "et_wizard.wwp"
    project.parent.mkdir(parents=True)
    shutil.copy2(source, project)
    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]

    from pywinauto import Desktop, keyboard
    from winwatt_automation.runtime_mapping.et_document import configure_et_scope, open_et_document
    from winwatt_automation.runtime_mapping.room_deep_explorer import _active_window, state_signature

    report: dict[str, object] = {
        "schema_version": 1, "profile_id": profile["profile_id"],
        "source": str(source), "source_sha256": source_hash,
        "project": str(project), "status": "running",
    }
    try:
        dialog = open_et_document(project_path=str(project), reuse_session=False)
        process_id = int(dialog.process_id())
        report["scope_selection"] = configure_et_scope(
            dialog, building_name=args.building_name, zone_name=args.zone_name,
            structure_scope=args.structure_scope,
        )
        dialog.capture_as_image().save(str(output / "step_00_configured.png"))
        native = Desktop(backend="win32").window(handle=int(dialog.handle)).wrapper_object()
        next_buttons = [
            item for item in native.descendants()
            if item.class_name() == "TButton" and item.window_text() == "Tovább"
            and item.is_visible() and item.is_enabled()
        ]
        if len(next_buttons) != 1:
            raise RuntimeError(f"Expected one enabled Tovább button, found {len(next_buttons)}")
        next_buttons[0].click()
        time.sleep(1.0)
        next_window = _active_window(process_id)
        next_window.capture_as_image().save(str(output / "step_01.png"))
        report["next_state"] = state_signature(next_window)
        report["screenshots"] = ["step_00_configured.png", "step_01.png"]
        for _ in range(8):
            try:
                active = _active_window(process_id)
            except RuntimeError:
                break
            if active.class_name() == "TMainForm":
                break
            keyboard.send_keys("{ESC}")
            time.sleep(0.2)
        report["source_unchanged"] = sha256(source) == source_hash
        report["copy_unchanged"] = sha256(project) == source_hash
        report["status"] = "passed" if report["source_unchanged"] and report["copy_unchanged"] else "failed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
    finally:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({key: report.get(key) for key in (
        "status", "scope_selection", "source_unchanged", "copy_unchanged", "error"
    )}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
