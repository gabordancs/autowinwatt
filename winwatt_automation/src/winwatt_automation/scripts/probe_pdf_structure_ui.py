"""Open a disposable PDF-reconstruction WWP and inventory the structure UI.

This is a bounded precursor to the deterministic structure-rebuild worker.  It
only opens the project and the verified global ``Szerkezetek`` catalogue, then
captures the visible controls and a screenshot.  It does not edit or save.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from pywinauto import Desktop

from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.runtime_mapping.mdi_state_model import (
    activate_structures_catalog_native,
    active_mdi_title,
)
from winwatt_automation.services.winwatt_service import WinWattService
from winwatt_automation.version_profile import require_profile


def _control(item: Any) -> dict[str, Any] | None:
    try:
        if not item.is_visible():
            return None
        rect = item.rectangle()
        return {
            "control_type": item.element_info.control_type,
            "caption": item.window_text() or None,
            "class_name": item.class_name(),
            "automation_id": item.element_info.automation_id or None,
            "enabled": bool(item.is_enabled()),
            "rectangle": [rect.left, rect.top, rect.right, rect.bottom],
        }
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    profile = require_profile(args.profile.resolve(strict=True))
    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    project = args.project.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    service = WinWattService()
    service.open_project(project)
    if not activate_structures_catalog_native() or active_mdi_title() != "Szerkezetek":
        raise RuntimeError("verified catalog.structure.open did not reach Szerkezetek")
    time.sleep(0.5)
    main = get_main_window()
    process_id = int(main.process_id())
    certificate = next(
        item for item in main.descendants(control_type="TreeItem")
        if item.is_visible() and item.window_text() == "Certificate"
    )
    certificate.double_click_input()
    time.sleep(0.5)

    windows: list[dict[str, Any]] = []
    for window in Desktop(backend="uia").windows(top_level_only=True):
        try:
            if int(window.process_id()) != process_id or not window.is_visible():
                continue
            controls = [record for item in window.descendants() if (record := _control(item))]
            windows.append({
                "title": window.window_text(),
                "class_name": window.class_name(),
                "handle": int(window.handle),
                "controls": controls,
            })
            window.capture_as_image().save(output / f"window_{int(window.handle)}.png")
        except Exception:
            continue
    (output / "inventory.json").write_text(
        json.dumps({"project": str(project), "windows": windows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "passed", "windows": len(windows), "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
