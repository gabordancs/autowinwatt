from __future__ import annotations

import json
import time
from pathlib import Path

from pywinauto import Application, Desktop

from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.services.winwatt_service import WinWattService


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "winwatt_automation/data/runtime_maps/full_authorized_sandbox/certification_seed_20260929b/prepared.wwp"
OUTPUT = ROOT / "data/delceg56/winwatt_material_catalog_export.xml"
REPORT = ROOT / "data/delceg56/material_catalog_export_probe.json"


def main() -> int:
    report = {"source": str(SOURCE), "output": str(OUTPUT), "status": "failed", "observed_probe": True}
    service = WinWattService()
    try:
        if OUTPUT.exists():
            raise FileExistsError(OUTPUT)
        service.open_project(SOURCE)
        main_uia = get_main_window()
        pid = int(main_uia.process_id())
        native = Application(backend="win32").connect(process=pid).window(handle=int(main_uia.handle))
        native.menu_select("Jegyzékek->Anyagok")
        deadline = time.monotonic() + 8
        child = None
        while time.monotonic() < deadline:
            items = [w for w in Desktop(backend="win32").windows() if int(w.process_id()) == pid and w.class_name() == "TChildWinForm" and w.window_text() == "Anyagok"]
            if items:
                child = items[0]
                break
            time.sleep(0.1)
        if child is None:
            raise RuntimeError("Anyagok catalog did not open")
        child.set_focus()
        trees = [w for w in child.descendants() if w.class_name() == "TTreeView"]
        if not trees:
            raise RuntimeError("Material group tree missing")
        trees[0].select("\\Anyagok")
        native.menu_select("Csoport->Export fájlba...")
        deadline = time.monotonic() + 8
        dialog = None
        while time.monotonic() < deadline:
            items = [w for w in Desktop(backend="win32").windows() if int(w.process_id()) == pid and w.class_name() == "#32770" and w.is_visible()]
            if items:
                dialog = items[0]
                break
            time.sleep(0.1)
        if dialog is None:
            raise RuntimeError("Material export save dialog did not open")
        edits = [w for w in dialog.descendants() if w.class_name() == "Edit" and w.is_visible()]
        max(edits, key=lambda w: w.rectangle().top).set_edit_text(str(OUTPUT))
        buttons = [w for w in dialog.descendants() if w.class_name() == "Button" and w.is_visible()]
        next(w for w in buttons if int(w.control_id()) == 1).click_input()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not OUTPUT.exists():
            time.sleep(0.1)
        if not OUTPUT.exists():
            raise RuntimeError("Material export file was not created")
        report.update({"status": "passed", "bytes": OUTPUT.stat().st_size})
    except Exception as exc:
        report["error"] = repr(exc)
    finally:
        try:
            service.close_project_gracefully()
        except Exception:
            pass
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
