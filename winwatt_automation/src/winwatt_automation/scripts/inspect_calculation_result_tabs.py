"""Read-only inspection of visible 2023 building calculation/result tabs."""
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
    from pywinauto import Desktop
    from winwatt_automation.runtime_mapping.room_deep_explorer import open_sandbox_building
    from winwatt_automation.services.winwatt_service import WinWattService

    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    report = {
        "profile_id": profile["profile_id"],
        "source": str(source),
        "source_sha256": sha256(source),
        "project": str(project),
        "status": "running",
        "tabs": [],
    }

    def checkpoint() -> None:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    process_id = None
    checkpoint()
    try:
        editor = open_sandbox_building(project_path=str(project))
        process_id = int(editor.process_id())
        tabs = [x for x in editor.descendants(control_type="TabItem") if x.is_visible()]
        for index, tab in enumerate(tabs):
            tab.select()
            time.sleep(0.35)
            native = Desktop(backend="win32").window(handle=int(editor.handle)).wrapper_object()
            controls = []
            for item in native.descendants():
                if not item.is_visible():
                    continue
                text = item.window_text().strip()
                if not text and item.class_name() not in {"TListView", "TListViewWithHeader", "TStringGrid"}:
                    continue
                rect = item.rectangle()
                record = {
                    "class": item.class_name(),
                    "text": text,
                    "enabled": bool(item.is_enabled()),
                    "rectangle": [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)],
                }
                if item.class_name() in {"TListView", "TListViewWithHeader"}:
                    from pywinauto.controls.common_controls import ListViewWrapper
                    listing = ListViewWrapper(item.handle)
                    record["item_count"] = listing.item_count()
                    record["rows"] = [listing.get_item(i).texts() for i in range(listing.item_count())]
                controls.append(record)
            name = tab.window_text()
            editor.capture_as_image().save(str(output / f"tab_{index:02d}.png"))
            report["tabs"].append({"index": index, "name": name, "controls": controls})
            checkpoint()
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        report["copy_unchanged"] = sha256(project) == report["source_sha256"]
        report["status"] = "passed"
        native = Desktop(backend="win32").window(handle=int(editor.handle)).wrapper_object()
        discards = [x for x in native.descendants() if x.class_name() == "TButton" and x.window_text() == "Elvet" and x.is_visible()]
        if len(discards) == 1:
            discards[0].click()
            time.sleep(0.3)
        WinWattService().close_project_gracefully()
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
    finally:
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        checkpoint()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
