"""Open the ET XML-administration form on a minimal disposable project."""
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
    from pywinauto import Desktop, keyboard
    from pywinauto.controls.win32_controls import ComboBoxWrapper
    from winwatt_automation.runtime_mapping.et_document import configure_et_scope, open_et_document
    from winwatt_automation.runtime_mapping.room_deep_explorer import _active_window
    from winwatt_automation.services.winwatt_service import WinWattService

    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    report = {"status": "running", "source": str(source), "source_sha256": sha256(source), "project": str(project)}
    try:
        dialog = open_et_document(project_path=str(project), reuse_session=False)
        pid = int(dialog.process_id())
        report["scope"] = configure_et_scope(dialog, structure_scope="all")

        def native_active():
            active = _active_window(pid)
            return active, Desktop(backend="win32").window(handle=int(active.handle)).wrapper_object()

        for step in range(3):
            active, native = native_active()
            active.capture_as_image().save(str(output / f"step_{step:02d}.png"))
            export = [x for x in native.descendants() if x.class_name() == "TButton" and x.window_text() == "e-tanúsítás xml export..." and x.is_visible() and x.is_enabled()]
            if export:
                export[0].click(); time.sleep(0.8); break
            nexts = [x for x in native.descendants() if x.class_name() == "TButton" and x.window_text() == "Tovább" and x.is_visible() and x.is_enabled()]
            if len(nexts) != 1:
                raise RuntimeError(f"ET step {step}: expected one enabled Next, found {len(nexts)}")
            nexts[0].click(); time.sleep(0.8)
        admin, native = native_active()
        report["admin_window"] = {"class": admin.class_name(), "title": admin.window_text()}
        admin.capture_as_image().save(str(output / "admin.png"))
        controls = []
        for item in native.descendants():
            if not item.is_visible():
                continue
            rect = item.rectangle()
            row = {"class": item.class_name(), "text": item.window_text(), "enabled": bool(item.is_enabled()), "rect": [int(rect.left),int(rect.top),int(rect.right),int(rect.bottom)]}
            if item.class_name() == "TComboBox":
                combo = ComboBoxWrapper(item.handle)
                row["values"] = combo.item_texts()
                row["selected_index"] = combo.selected_index()
            controls.append(row)
        report["controls"] = controls
        keyboard.send_keys("{ESC}"); time.sleep(0.3)
        for _ in range(5):
            try:
                active = _active_window(pid)
            except RuntimeError:
                break
            if active.class_name() == "TMainForm":
                break
            keyboard.send_keys("{ESC}"); time.sleep(0.25)
        WinWattService().close_project_gracefully()
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        report["copy_unchanged"] = sha256(project) == report["source_sha256"]
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"; report["error"] = repr(exc)
    finally:
        (output / "report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
