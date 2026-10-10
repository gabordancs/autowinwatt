"""Inspect or apply a scoped WinWatt bulk boundary change on a sandbox copy.

The default mode is strictly read-only. Apply mode requires explicit target
room names, verifies them against WinWatt's occurrence list, selects only those
rows, and refuses to save unless the requested scope is exact.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from winwatt_automation.version_profile import require_profile


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wait_main(desktop, pid: int, project: Path, timeout: float = 75.0):
    deadline = time.monotonic() + timeout
    stable_handle = None
    stable_count = 0
    while time.monotonic() < deadline:
        for candidate in desktop.windows(top_level_only=True):
            if int(candidate.process_id()) != pid:
                continue
            if candidate.class_name() == "#32770":
                text = " ".join(
                    str(control.window_text() or "")
                    for control in [candidate, *candidate.descendants()]
                ).casefold()
                if "verzió ellenőrzés sikertelen" in text:
                    buttons = [
                        control
                        for control in candidate.descendants(class_name="Button")
                        if control.window_text().replace("&", "").strip().casefold() == "nem"
                    ]
                    if len(buttons) == 1:
                        buttons[0].send_message(0x00F5)
            if candidate.class_name() != "TMainForm" or not candidate.is_visible() or not candidate.is_enabled():
                continue
            loaded = " - " in candidate.window_text() and project.stem.casefold() in candidate.window_text().casefold()
            handle = int(candidate.handle)
            stable_count = stable_count + 1 if handle == stable_handle and loaded else 1
            stable_handle = handle
            if loaded and stable_count >= 8:
                return candidate
        time.sleep(0.25)
    raise RuntimeError("WinWatt TMainForm did not become ready")


def _wait_dialog(desktop, pid: int, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        matches = [
            item
            for item in desktop.windows(top_level_only=True)
            if int(item.process_id()) == pid
            and item.class_name() == "TChangeBoundarisForm"
            and item.is_visible()
            and item.is_enabled()
        ]
        if len(matches) == 1:
            return matches[0]
        time.sleep(0.1)
    raise RuntimeError("TChangeBoundarisForm did not open uniquely")


def _control_record(control) -> dict:
    rect = control.rectangle()
    record = {
        "handle": int(control.handle),
        "class": control.class_name(),
        "friendly_class": control.friendly_class_name(),
        "control_id": int(control.control_id()),
        "text": control.window_text(),
        "enabled": bool(control.is_enabled()),
        "visible": bool(control.is_visible()),
        "rectangle": [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)],
    }
    if control.class_name() in {"TCheckBox", "TRadioButton", "TGroupButton"}:
        try:
            record["check_state"] = int(control.get_check_state())
        except Exception:
            record["check_state"] = None
    if control.class_name() == "TComboBox":
        try:
            record["items"] = list(control.item_texts())
            record["selected"] = control.selected_text()
        except Exception as exc:
            record["combo_error"] = repr(exc)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--search-name")
    parser.add_argument("--search-type")
    parser.add_argument(
        "--find-only",
        action="store_true",
        help="Run the dialog's explicit occurrence-search mode without modification.",
    )
    parser.add_argument("--inspect-temperature-tab", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--target-room", action="append", default=[])
    args = parser.parse_args()
    if args.apply:
        if not args.search_name or not args.search_type:
            parser.error("--apply requires --search-name and --search-type")
        if not args.inspect_temperature_tab:
            parser.error("--apply requires --inspect-temperature-tab")
        if args.find_only:
            parser.error("--apply and --find-only are mutually exclusive")
        if not args.target_room:
            parser.error("--apply requires at least one --target-room")
        if len(set(args.target_room)) != len(args.target_room):
            parser.error("--target-room values must be unique")

    profile = require_profile(args.profile)
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = output / "sandbox.wwp"
    shutil.copy2(source, project)
    source_hash = _sha256(source)
    copy_hash = _sha256(project)
    report = {
        "schema_version": 1,
        "operation": "bulk_boundary_change_live_inventory",
        "mode": "sandbox_apply" if args.apply else "read_only_cancel",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "profile_id": profile["profile_id"],
        "source": str(source),
        "source_sha256": source_hash,
        "project": str(project),
        "status": "running",
        "llm_used": False,
    }
    process = None
    dialog_cancelled = False
    try:
        from pywinauto import Desktop

        os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
        process = subprocess.Popen([profile["exe_path"], str(project)])
        desktop = Desktop(backend="win32")
        main = _wait_main(desktop, process.pid, project)
        if not ctypes.windll.user32.PostMessageW(int(main.handle), 0x0111, 55, 0):
            raise ctypes.WinError()
        dialog = _wait_dialog(desktop, process.pid)
        dialog.capture_as_image().save(str(output / "change_boundaries_initial.png"))
        live_controls = list(dialog.descendants())
        if args.search_name:
            search_names = [
                item
                for item in live_controls
                if item.class_name() == "TEdit" and item.rectangle().top < dialog.rectangle().top + 180
            ]
            if len(search_names) != 2:
                raise RuntimeError(f"Expected two upper search edits, found {len(search_names)}")
            # The name edit is the wide upper field; the narrow one is U-value.
            name_edit = max(search_names, key=lambda item: item.rectangle().width())
            name_edit.set_edit_text(args.search_name)
        if args.search_type:
            search_types = [
                item
                for item in live_controls
                if item.class_name() == "TComboBox" and item.rectangle().top < dialog.rectangle().top + 180
            ]
            if len(search_types) != 1:
                raise RuntimeError(f"Expected one upper search type combo, found {len(search_types)}")
            combo = search_types[0]
            values = list(combo.item_texts())
            matches = [index for index, value in enumerate(values) if value.casefold() == args.search_type.casefold()]
            if len(matches) != 1:
                raise RuntimeError(f"Search type {args.search_type!r} is not unique in {values!r}")
            combo.select(matches[0])
        if args.search_name or args.search_type:
            copy_buttons = [
                item
                for item in live_controls
                if item.class_name() == "TButton" and item.window_text().strip().casefold() == "keresés szerinti"
            ]
            if len(copy_buttons) != 1:
                raise RuntimeError(f"Expected one Keresés szerinti button, found {len(copy_buttons)}")
            copy_buttons[0].send_message(0x00F5)
            time.sleep(0.4)
        if args.find_only:
            find_only = [
                item
                for item in live_controls
                if item.class_name() == "TCheckBox"
                and "előfordulások keresése" in item.window_text().casefold()
            ]
            if len(find_only) != 1:
                raise RuntimeError(f"Expected one find-only checkbox, found {len(find_only)}")
            if int(find_only[0].get_check_state()) != 1:
                find_only[0].click()
            if int(find_only[0].get_check_state()) != 1:
                raise RuntimeError("Find-only checkbox did not become checked")
        if args.inspect_temperature_tab:
            pages = [item for item in live_controls if item.class_name() == "TPageControl"]
            temperature_sheets = [
                item
                for item in live_controls
                if item.class_name() == "TTabSheet"
                and item.window_text().strip().casefold() == "túloldali hőmérséklet"
            ]
            if len(pages) != 1 or len(temperature_sheets) != 1 or not pages[0].is_visible():
                raise RuntimeError("Temperature tab is not uniquely available")
            page_rect = pages[0].rectangle()
            # On this profile the temperature tab is the second header.  The
            # click is derived from the live page-control rectangle, not a
            # desktop coordinate.
            dialog.click_input(coords=(
                int(page_rect.left - dialog.rectangle().left + 120),
                int(page_rect.top - dialog.rectangle().top + 12),
            ))
            time.sleep(0.4)
            if not temperature_sheets[0].is_visible():
                raise RuntimeError("Temperature tab click did not activate its sheet")
            report["temperature_tab_activated"] = True
            if args.apply:
                winter_on = [
                    item
                    for item in dialog.descendants()
                    if item.class_name() == "TCheckBox"
                    and item.window_text().strip().casefold() == "télre bekapcsolni"
                    and item.is_visible()
                ]
                winter_off = [
                    item
                    for item in dialog.descendants()
                    if item.class_name() == "TCheckBox"
                    and item.window_text().strip().casefold() == "télre kikapcsolni"
                    and item.is_visible()
                ]
                if len(winter_on) != 1 or len(winter_off) != 1:
                    raise RuntimeError("Winter coupling controls are not unique")
                if int(winter_on[0].get_check_state()) != 1:
                    winter_on[0].click()
                if int(winter_on[0].get_check_state()) != 1 or int(winter_off[0].get_check_state()) != 0:
                    raise RuntimeError("Winter-on could not be enabled exclusively")
                report["winter_change"] = {"enable": True, "disable": False}
        time.sleep(0.4)
        dialog.capture_as_image().save(str(output / "change_boundaries_configured.png"))
        controls = [_control_record(item) for item in dialog.descendants()]
        report.update(
            {
                "dialog": {
                    "handle": int(dialog.handle),
                    "class": dialog.class_name(),
                    "title": dialog.window_text(),
                    "controls": controls,
                },
                "control_count": len(controls),
                "search": {
                    "name": args.search_name,
                    "type": args.search_type,
                    "find_only": args.find_only,
                },
            }
        )
        if args.find_only or args.apply:
            ok_buttons = [
                item
                for item in dialog.descendants()
                if item.class_name() == "TButton" and item.window_text().strip().casefold() == "ok"
            ]
            if len(ok_buttons) != 1:
                raise RuntimeError(f"Expected one OK button, found {len(ok_buttons)}")
            # BM_CLICK is modal here: SendMessage would block until the result
            # window closes, so dispatch it asynchronously.
            if not ctypes.windll.user32.PostMessageW(int(ok_buttons[0].handle), 0x00F5, 0, 0):
                raise ctypes.WinError()
            time.sleep(0.8)
            result_windows = [
                item
                for item in desktop.windows(top_level_only=True)
                if int(item.process_id()) == process.pid
                and item.is_visible()
                and item.class_name() in {"TChangeBoundaryListForm", "#32770"}
            ]
            report["find_result_windows"] = [
                {
                    "class": item.class_name(),
                    "title": item.window_text(),
                    # Direct children are intentional here. Traversing the full
                    # accessibility tree of this result list can block for
                    # minutes on the 128-zone SR8 project.
                    "texts": [control.window_text() for control in item.children() if control.window_text()],
                    "controls": [_control_record(control) for control in item.children()],
                }
                for item in result_windows
            ]
            if result_windows:
                result = result_windows[-1]
                result.capture_as_image().save(str(output / "find_result.png"))
                lists = [control for control in result.children() if control.class_name() == "TListViewWithHeader"]
                if len(lists) == 1:
                    from pywinauto.controls.common_controls import ListViewWrapper

                    list_view = ListViewWrapper(lists[0].handle)
                    report["find_result_item_count"] = int(list_view.item_count())
                    report["find_result_rows"] = [
                        list_view.get_item(index).text()
                        for index in range(list_view.item_count())
                    ]
                    if args.apply:
                        target_set = set(args.target_room)
                        row_matches = {
                            target: [index for index, row in enumerate(report["find_result_rows"]) if row == target]
                            for target in target_set
                        }
                        if any(len(indices) != 1 for indices in row_matches.values()):
                            raise RuntimeError(f"Target rooms are not unique in result: {row_matches!r}")
                        for index in range(list_view.item_count()):
                            list_view.get_item(index).deselect()
                        for indices in row_matches.values():
                            list_view.get_item(indices[0]).select()
                        selected_count = int(list_view.get_selected_count())
                        if selected_count != len(target_set):
                            raise RuntimeError(
                                f"Expected {len(target_set)} selected occurrences, got {selected_count}"
                            )
                        only_selected = [
                            control
                            for control in result.children()
                            if control.class_name() == "TRadioButton"
                            and control.window_text().strip().casefold() == "csak a kijelöltek"
                        ]
                        if len(only_selected) != 1:
                            raise RuntimeError("Only-selected result scope is not unique")
                        only_selected[0].click()
                        if int(only_selected[0].get_check_state()) != 1:
                            raise RuntimeError("Only-selected result scope was not activated")
                        report["apply_scope"] = {
                            "target_rooms": sorted(target_set),
                            "selected_count": selected_count,
                            "result_count": int(list_view.item_count()),
                        }
                        result.capture_as_image().save(str(output / "apply_scope.png"))
                result_close = [
                    control
                    for control in result.children()
                    if control.class_name() == "TButton"
                    and control.window_text().replace("&", "").strip().casefold() in {"bezár", "ok"}
                ]
                if args.apply:
                    final_buttons = [
                        control
                        for control in result.children()
                        if control.class_name() == "TButton"
                        and control.window_text().replace("&", "").strip().casefold() == "ok"
                    ]
                    if len(final_buttons) != 1:
                        raise RuntimeError("Result OK button is not unique")
                    if not ctypes.windll.user32.PostMessageW(int(final_buttons[0].handle), 0x00F5, 0, 0):
                        raise ctypes.WinError()
                else:
                    cancel_buttons = [
                        control
                        for control in result.children()
                        if control.class_name() == "TButton"
                        and control.window_text().replace("&", "").strip().casefold() == "elvet"
                    ]
                    if len(cancel_buttons) != 1:
                        raise RuntimeError("Result Elvet button is not unique")
                    if not ctypes.windll.user32.PostMessageW(int(cancel_buttons[0].handle), 0x00F5, 0, 0):
                        raise ctypes.WinError()
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline and any(
                    int(item.process_id()) == process.pid and int(item.handle) == int(result.handle)
                    for item in desktop.windows(top_level_only=True)
                ):
                    time.sleep(0.1)
                if any(
                    int(item.process_id()) == process.pid and int(item.handle) == int(result.handle)
                    for item in desktop.windows(top_level_only=True)
                ):
                    raise RuntimeError("Find result window did not close")
            # A successful find can either keep the form open or close it.
            matching_forms = []
            settle_deadline = time.monotonic() + (3.0 if args.apply else 0.2)
            while time.monotonic() < settle_deadline:
                matching_forms = [
                    item
                    for item in desktop.windows(top_level_only=True)
                    if int(item.process_id()) == process.pid
                    and item.class_name() == "TChangeBoundarisForm"
                    and item.is_visible()
                ]
                if not matching_forms:
                    dialog_cancelled = True
                    break
                time.sleep(0.1)
            if matching_forms:
                dialog = matching_forms[0]
            else:
                dialog_cancelled = True
        if not dialog_cancelled:
            close_buttons = [
                item
                for item in dialog.descendants()
                if item.class_name() == "TButton" and item.window_text().strip().casefold() == "bezár"
            ]
            if len(close_buttons) != 1:
                raise RuntimeError(f"Expected one Bezár button, found {len(close_buttons)}")
            close_buttons[0].send_message(0x00F5)
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if not any(
                    int(item.process_id()) == process.pid and item.class_name() == "TChangeBoundarisForm"
                    for item in desktop.windows(top_level_only=True)
                ):
                    dialog_cancelled = True
                    break
                time.sleep(0.1)
        if not dialog_cancelled:
            raise RuntimeError("Bulk boundary dialog did not close through Bezár")
        if args.apply:
            from winwatt_automation.live_ui.app_connector import reset_winwatt_connection_cache
            from winwatt_automation.services.winwatt_service import WinWattService

            reset_winwatt_connection_cache()
            WinWattService().save_project()
            report["project_saved"] = True
        main.post_message(0x0010)
        process.wait(timeout=20.0)
        report.update(
            {
                "dialog_cancelled": True,
                "source_unchanged": _sha256(source) == source_hash,
                "copy_unchanged": _sha256(project) == copy_hash,
                "session_closed": process.poll() is not None,
            }
        )
        if args.apply:
            report["copy_changed"] = not report["copy_unchanged"]
            passed = all(
                report.get(key)
                for key in ("dialog_cancelled", "source_unchanged", "copy_changed", "session_closed", "project_saved")
            )
        else:
            passed = all(
                report.get(key)
                for key in ("dialog_cancelled", "source_unchanged", "copy_unchanged", "session_closed")
            )
        report["status"] = "passed" if passed else "failed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
    finally:
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=10.0)
            except Exception:
                process.kill()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({"status": report["status"], "output": str(output)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
