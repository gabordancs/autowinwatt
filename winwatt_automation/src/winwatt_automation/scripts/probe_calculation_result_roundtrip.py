"""Recalculate a minimal building and verify one result after save/reopen."""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

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
    from pywinauto.controls.common_controls import ListViewWrapper
    from winwatt_automation.runtime_mapping.room_deep_explorer import (
        open_sandbox_building,
        open_sandbox_buildings,
    )
    from winwatt_automation.services.winwatt_service import WinWattService

    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    report: dict[str, Any] = {
        "schema_version": 1,
        "profile_id": profile["profile_id"],
        "source": str(source),
        "source_sha256": sha256(source),
        "project": str(project),
        "status": "running",
    }
    process_id: int | None = None

    def checkpoint() -> None:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def native(window: Any) -> Any:
        return Desktop(backend="win32").window(handle=int(window.handle)).wrapper_object()

    def select_tab(editor: Any, caption: str) -> None:
        matches = [
            item for item in editor.descendants(control_type="TabItem")
            if item.window_text() == caption
        ]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one {caption!r} tab, found {len(matches)}")
        matches[0].select()
        time.sleep(0.4)

    def click_button(window: Any, caption: str) -> None:
        matches = [
            item for item in native(window).descendants()
            if item.class_name() == "TButton" and item.window_text() == caption
            and item.is_visible() and item.is_enabled()
        ]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one enabled {caption!r} button, found {len(matches)}")
        matches[0].click()

    def result_tables(editor: Any) -> list[dict[str, Any]]:
        tables = []
        for item in native(editor).descendants():
            if item.class_name() not in {"TListView", "TListViewWithHeader"} or not item.is_visible():
                continue
            listing = ListViewWrapper(item.handle)
            columns = max(1, listing.column_count())
            rows = []
            for row_index in range(listing.item_count()):
                rows.append([
                    listing.get_item(row_index, column_index).text()
                    for column_index in range(columns)
                ])
            rect = item.rectangle()
            tables.append({
                "rectangle": [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)],
                "column_count": columns,
                "rows": rows,
            })
        return tables

    def nonzero_result(tables: list[dict[str, Any]]) -> list[str] | None:
        for table in tables:
            for row in table["rows"]:
                if not row:
                    continue
                joined = " ".join(row).replace(",", ".")
                if any(char.isdigit() for char in joined) and not all(
                    value.strip() in {"", "0", "0.0", "0,0"} for value in row[1:]
                ):
                    return row
        return None

    checkpoint()
    try:
        editor = open_sandbox_building(project_path=str(project))
        process_id = int(editor.process_id())
        select_tab(editor, "Zónák")
        click_button(editor, "Mindet újraszámol")
        report["recalculation_triggered"] = True
        time.sleep(1.5)
        unexpected = [
            {"class": window.class_name(), "title": window.window_text()}
            for window in Desktop(backend="uia").windows(top_level_only=True)
            if int(window.process_id()) == process_id
            and window.class_name() not in {"TMainForm", "TBuildingModifyForm"}
            and window.is_visible()
        ]
        if unexpected:
            report["unexpected_windows_after_recalculation"] = unexpected
            raise RuntimeError(f"Recalculation opened unexpected windows: {unexpected!r}")

        select_tab(editor, "Hőszükséglet, fajlagos hőveszteségtényező")
        report["after_recalculation"] = result_tables(editor)
        report["selected_result_before_save"] = nonzero_result(report["after_recalculation"])
        if report["selected_result_before_save"] is None:
            raise RuntimeError("No non-zero machine-readable calculation result was found")
        editor.capture_as_image().save(str(output / "result_after_recalculation.png"))

        click_button(editor, "OK")
        service = WinWattService()
        service.save_project()
        report["saved_sha256"] = sha256(project)
        service.close_project_gracefully()
        report["first_session_closed"] = True

        open_sandbox_buildings(project_path=str(project))
        editor = open_sandbox_building(project_path=str(project))
        process_id = int(editor.process_id())
        select_tab(editor, "Hőszükséglet, fajlagos hőveszteségtényező")
        report["after_reopen"] = result_tables(editor)
        report["selected_result_after_reopen"] = nonzero_result(report["after_reopen"])
        report["roundtrip_passed"] = (
            report["selected_result_after_reopen"] == report["selected_result_before_save"]
        )
        editor.capture_as_image().save(str(output / "result_after_reopen.png"))
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        report["copy_saved"] = project.is_file()
        report["status"] = "passed" if all((
            report["recalculation_triggered"],
            report["roundtrip_passed"],
            report["source_unchanged"],
            report["copy_saved"],
        )) else "failed"
        click_button(editor, "Elvet")
        service.close_project_gracefully()
        report["second_session_closed"] = True
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
