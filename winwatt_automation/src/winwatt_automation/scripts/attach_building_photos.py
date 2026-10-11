"""Attach certificate photos to a copied WinWatt project and verify persistence."""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from winwatt_automation.version_profile import require_profile, sha256


PHOTO_CATEGORIES = (
    "Első lapra kerülő, egyben homlokzati kép",
    "Homlokzati kép",
    "Jellemző hőleadót, annak szabályozását ábrázoló kép",
    "Jellemző nyílászáró képe",
    "Hőtermelő, hőtároló képe",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--building-name", required=True)
    parser.add_argument("--photo", action="append", required=True, type=Path)
    args = parser.parse_args()
    if len(args.photo) != len(PHOTO_CATEGORIES):
        parser.error(f"exactly {len(PHOTO_CATEGORIES)} --photo arguments are required")
    photos = [path.resolve(strict=True) for path in args.photo]
    profile = require_profile(args.profile)
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = output / "project_with_photos.wwp"
    shutil.copy2(source, project)

    import os
    from pywinauto import Desktop
    from pywinauto.controls.win32_controls import ComboBoxWrapper
    from winwatt_automation.runtime_mapping.room_deep_explorer import open_sandbox_building
    from winwatt_automation.services.winwatt_service import WinWattService

    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    report: dict[str, Any] = {
        "schema_version": 1, "operation": "attach_building_photos",
        "profile_id": profile["profile_id"], "source": str(source),
        "source_sha256": sha256(source), "project": str(project),
        "building_name": args.building_name, "status": "running",
        "photos": [{"category": category, "path": str(path), "sha256": sha256(path)}
                   for category, path in zip(PHOTO_CATEGORIES, photos)],
    }

    def checkpoint() -> None:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def native(window: Any) -> Any:
        return Desktop(backend="win32").window(handle=int(window.handle)).wrapper_object()

    def select_photos_tab(editor: Any) -> None:
        matches = [item for item in editor.descendants(control_type="TabItem")
                   if item.window_text() == "Fotók"]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one Photos tab, found {len(matches)}")
        matches[0].select(); time.sleep(0.5)

    checkpoint()
    service = WinWattService()
    try:
        editor = open_sandbox_building(project_path=str(project), building_name=args.building_name)
        select_photos_tab(editor)
        native_editor = native(editor)
        full_path_matches = [item for item in native_editor.descendants()
                             if item.class_name() == "TCheckBox" and item.is_visible()
                             and item.window_text() == "Fájlok kiválasztásakor a teljes útvonal használata"]
        if len(full_path_matches) != 1:
            raise RuntimeError(f"Expected one full-path checkbox, found {len(full_path_matches)}")
        full_path = full_path_matches[0]
        if full_path.get_check_state() != 1:
            full_path.click(); time.sleep(0.2)
        category_combos = []
        for item in native_editor.descendants():
            if item.class_name() != "TComboBox" or not item.is_visible():
                continue
            combo = ComboBoxWrapper(item.handle)
            if all(category in combo.item_texts() for category in PHOTO_CATEGORIES):
                category_combos.append(combo)
        if len(category_combos) != 1:
            raise RuntimeError(f"Expected one photo-category combo, found {len(category_combos)}")
        category_combo = category_combos[0]
        edits = [item for item in native_editor.descendants()
                 if item.class_name() == "TEdit" and item.is_visible()
                 and item.rectangle().top > category_combo.rectangle().top - 60]
        if len(edits) != 1:
            raise RuntimeError(f"Expected one photo filename edit, found {len(edits)}")
        filename = edits[0]
        adds = [item for item in native_editor.descendants()
                if item.class_name() == "TButton" and item.window_text() == "Felvesz" and item.is_visible()]
        if len(adds) != 1:
            raise RuntimeError(f"Expected one add-photo button, found {len(adds)}")
        add = adds[0]
        added = []
        for category_index, (category, photo) in enumerate(zip(PHOTO_CATEGORIES, photos)):
            category_combo.select(category_index)
            filename.set_edit_text(str(photo))
            time.sleep(0.2)
            if not add.is_enabled():
                raise RuntimeError(f"Add photo button remained disabled for {category!r}")
            add.click(); time.sleep(0.5)
            added.append({"category_index": category_index, "category": category,
                          "selected": category_combo.selected_text(), "path": filename.window_text()})
        report["added"] = added
        editor.capture_as_image().save(str(output / "photos_before_save.png"))
        ok = [item for item in native_editor.descendants()
              if item.class_name() == "TButton" and item.window_text() == "OK"
              and item.is_visible() and item.is_enabled()]
        if len(ok) != 1:
            raise RuntimeError(f"Expected one enabled OK button, found {len(ok)}")
        ok[0].click(); time.sleep(0.5)
        service.save_project()
        report["saved_sha256"] = sha256(project)
        service.close_project_gracefully()
        report["session_closed"] = True
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        report["status"] = "passed" if (
            len(added) == len(PHOTO_CATEGORIES) and report["source_unchanged"]
            and report["saved_sha256"] != report["source_sha256"]
        ) else "failed"
    except Exception as exc:
        report["status"] = "failed"; report["error"] = repr(exc)
        try:
            service.close_project_gracefully()
        except Exception as cleanup_exc:
            report["cleanup_error"] = repr(cleanup_exc)
    finally:
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        checkpoint()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
