"""Capture WinWatt heated-zone controls after selecting room-based mode."""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from pywinauto import Desktop
from pywinauto.controls.win32_controls import ListBoxWrapper

from winwatt_automation.runtime_mapping.room_deep_explorer import open_sandbox_building
from winwatt_automation.services.winwatt_service import WinWattService
from winwatt_automation.version_profile import require_profile


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", required=True, type=Path)
    p.add_argument("--source", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    profile = require_profile(a.profile)
    a.output.mkdir(parents=True, exist_ok=False)
    project = a.output / "testwwp.wwp"
    shutil.copy2(a.source.resolve(strict=True), project)
    import os
    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    report = {"status": "failed", "project": str(project)}
    try:
        editor = open_sandbox_building(project_path=str(project))
        pid = int(editor.process_id())
        next(x for x in editor.descendants(control_type="TabItem") if x.window_text() == "Zónák").select()
        time.sleep(.3)
        native_editor = Desktop(backend="win32").window(handle=int(editor.handle)).wrapper_object()
        next(x for x in native_editor.descendants() if x.class_name() == "TButton" and x.window_text() == "A fűtött zóna").click()
        time.sleep(.5)
        dialog = Desktop(backend="uia").window(process=pid, class_name="TThermicZoneForm").wrapper_object()
        native = Desktop(backend="win32").window(handle=int(dialog.handle)).wrapper_object()
        radio = next(x for x in native.descendants() if x.class_name() == "TGroupButton" and x.window_text() == "Helyiségek alapján")
        radio.click_input()
        time.sleep(.5)
        dialog.capture_as_image().save(str(a.output / "room_mode.png"))
        controls = []
        for x in native.descendants():
            if not x.is_visible():
                continue
            item = {"class": x.class_name(), "text": x.window_text(), "id": int(x.control_id()), "enabled": bool(x.is_enabled())}
            if x.class_name() == "TListBox":
                item["rows"] = ListBoxWrapper(x.handle).item_texts()
            controls.append(item)
        report.update(status="passed", controls=controls)
        next(x for x in native.descendants() if x.class_name() == "TButton" and x.window_text() == "Elvet").click()
        time.sleep(.2)
        native_editor = Desktop(backend="win32").window(handle=int(editor.handle)).wrapper_object()
        next(x for x in native_editor.descendants() if x.class_name() == "TButton" and x.window_text() == "Elvet").click()
        WinWattService().close_project_gracefully()
    except Exception as exc:
        report["error"] = repr(exc)
        try: WinWattService().close_project_gracefully()
        except Exception: pass
    (a.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
