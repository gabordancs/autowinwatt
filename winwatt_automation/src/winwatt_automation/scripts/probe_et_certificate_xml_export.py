"""Generate and validate a local ET certificate XML from a disposable WWP."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from winwatt_automation.version_profile import require_profile, sha256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--building-name", required=True)
    args = parser.parse_args()
    profile = require_profile(args.profile)
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = output / "testwwp.wwp"
    target_xml = output / "certificate.xml"
    shutil.copy2(source, project)

    import os
    from pywinauto import Desktop, keyboard
    from pywinauto.controls.win32_controls import ComboBoxWrapper
    from winwatt_automation.runtime_mapping.et_document import configure_et_scope, open_et_document
    from winwatt_automation.runtime_mapping.room_deep_explorer import _active_window
    from winwatt_automation.services.winwatt_service import WinWattService

    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    report: dict[str, Any] = {
        "schema_version": 1, "profile_id": profile["profile_id"],
        "source": str(source), "source_sha256": sha256(source),
        "project": str(project), "target_xml": str(target_xml), "status": "running",
    }

    def checkpoint() -> None:
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def native(window: Any) -> Any:
        return Desktop(backend="win32").window(handle=int(window.handle)).wrapper_object()

    def click_unique(window: Any, caption: str) -> None:
        matches = [x for x in native(window).descendants() if x.class_name() == "TButton" and x.window_text() == caption and x.is_visible() and x.is_enabled()]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one enabled {caption!r} button, found {len(matches)}")
        matches[0].click()

    def process_is_alive(pid: int) -> bool:
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(
                ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            ) and code.value == 259
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)

    def discard_sandbox_save_prompt(pid: int) -> bool:
        for window in Desktop(backend="win32").windows(top_level_only=True):
            if int(window.process_id()) != pid or window.class_name() != "#32770" or not window.is_visible():
                continue
            messages = [x.window_text() for x in window.descendants() if x.class_name() == "Static"]
            if not any("Az adatok változtak" in message for message in messages):
                continue
            no_buttons = [
                x for x in window.descendants()
                if x.class_name() == "Button" and int(x.control_id()) == 7
            ]
            if len(no_buttons) == 1:
                no_buttons[0].click()
                time.sleep(0.5)
                return True
        return False

    def cancel_printer_wait(pid: int) -> bool:
        for window in Desktop(backend="win32").windows(top_level_only=True):
            if int(window.process_id()) != pid or "Várakozás a nyomtatókapcsolatra" not in window.window_text():
                continue
            cancels = [
                x for x in window.descendants()
                if x.class_name() == "Button" and x.window_text() == "Mégse"
            ]
            if len(cancels) == 1:
                cancels[0].send_message(0x00F5)  # BM_CLICK
                time.sleep(0.3)
                return True
        return False

    def close_session(pid: int) -> tuple[bool, bool]:
        """Close modal ET windows, then discard changes to the sandbox WWP."""
        discarded = False
        deadline = time.monotonic() + 15.0
        main_close_sent = False
        while time.monotonic() < deadline and process_is_alive(pid):
            cancel_printer_wait(pid)
            if discard_sandbox_save_prompt(pid):
                discarded = True
                time.sleep(0.2)
                continue
            windows = [
                window for window in Desktop(backend="win32").windows(top_level_only=True)
                if int(window.process_id()) == pid and window.is_visible() and window.is_enabled()
            ]
            main = [window for window in windows if window.class_name() == "TMainForm"]
            if main:
                main[0].post_message(0x0010)  # asynchronous WM_CLOSE
                main_close_sent = True
                time.sleep(0.3)
                continue
            modals = [
                window for window in windows
                if window.class_name() in {"TETDocumentForm", "TLechnerAdminForm", "#32770"}
            ]
            if modals:
                modals[0].post_message(0x0010)
            time.sleep(0.25)
        if main_close_sent:
            final_deadline = time.monotonic() + 20.0
            while time.monotonic() < final_deadline and process_is_alive(pid):
                cancel_printer_wait(pid)
                if discard_sandbox_save_prompt(pid):
                    discarded = True
                time.sleep(0.2)
        return (not process_is_alive(pid), discarded)

    checkpoint()
    process_id: int | None = None
    try:
        dialog = open_et_document(project_path=str(project), reuse_session=False)
        process_id = int(dialog.process_id())
        report["scope"] = configure_et_scope(dialog, building_name=args.building_name, structure_scope="all")
        dialog.capture_as_image().save(str(output / "step_00_scope.png"))
        for step in (1, 2):
            active = _active_window(process_id)
            click_unique(active, "Tovább")
            time.sleep(0.9)
            active = _active_window(process_id)
            active.capture_as_image().save(str(output / f"step_{step:02d}.png"))

        final_page = _active_window(process_id)
        click_unique(final_page, "e-tanúsítás xml export...")
        time.sleep(0.8)
        admin = _active_window(process_id)
        if admin.class_name() != "TLechnerAdminForm":
            raise RuntimeError(f"Expected TLechnerAdminForm, found {admin.class_name()!r}")
        admin.capture_as_image().save(str(output / "admin_before_ok.png"))
        edits = [x.window_text() for x in native(admin).descendants() if x.class_name() == "TEdit" and x.is_visible()]
        report["admin"] = {
            "visible_edit_count": len(edits),
            "nonempty_edit_count": sum(bool(value.strip()) for value in edits),
            "project_data_available": any(value.strip() for value in edits),
        }
        # A newly created minimal building has no building-specific Lechner
        # classification yet. Fill only the four fields that WinWatt itself
        # reports as mandatory; keep the existing project/certifier data.
        admin_native = native(admin)
        year_fields = [
            x for x in admin_native.descendants()
            if x.class_name() == "TEdit" and x.is_visible()
            and x.rectangle().left == 124 and x.rectangle().top == 196
        ]
        if len(year_fields) != 1:
            raise RuntimeError(f"Building-year field is ambiguous: {len(year_fields)}")
        if not year_fields[0].window_text().strip():
            year_fields[0].set_edit_text("2020")
        required_combos = {
            322: 5,  # egyéb
            349: 0,  # Lakóépület
            378: 0,  # Nem áll védettség alatt
        }
        selected = {}
        for top, index in required_combos.items():
            matches = [
                x for x in admin_native.descendants()
                if x.class_name() == "TComboBox" and x.is_visible()
                and x.rectangle().left == 159 and x.rectangle().top == top
            ]
            if len(matches) != 1:
                raise RuntimeError(f"Required admin combo at y={top} is ambiguous: {len(matches)}")
            combo = ComboBoxWrapper(matches[0].handle)
            if not combo.selected_text().strip():
                combo.select(index)
                time.sleep(0.3)
            if combo.selected_index() != index:
                combo.select(index)
                time.sleep(0.3)
            if combo.selected_index() != index:
                raise RuntimeError(
                    f"Admin combo at y={top} did not commit index {index}: "
                    f"index={combo.selected_index()} text={combo.selected_text()!r}"
                )
            selected[str(top)] = {"index": combo.selected_index(), "text": combo.selected_text()}
        report["admin"]["manual_defaults"] = {
            "building_year": year_fields[0].window_text(), "combos": selected,
        }
        admin.capture_as_image().save(str(output / "admin_completed.png"))
        click_unique(admin, "OK")

        deadline = time.monotonic() + 8.0
        save_dialog = None
        while time.monotonic() < deadline:
            dialogs = [
                item for item in Desktop(backend="win32").windows(top_level_only=True)
                if int(item.process_id()) == process_id and item.class_name() == "#32770"
                and item.is_visible() and item.is_enabled()
                and any(child.class_name() == "Edit" and int(child.control_id()) == 1001 for child in item.descendants())
            ]
            if dialogs:
                save_dialog = dialogs[0]
                break
            time.sleep(0.1)
        if save_dialog is None:
            active = _active_window(process_id)
            active.capture_as_image().save(str(output / "after_admin_no_save_dialog.png"))
            raise RuntimeError(f"XML save dialog did not open; active={active.class_name()!r} {active.window_text()!r}")
        save_dialog.capture_as_image().save(str(output / "xml_save_dialog.png"))
        filename = next(item for item in save_dialog.descendants() if item.class_name() == "Edit" and int(item.control_id()) == 1001)
        filename.set_edit_text(str(target_xml))
        save_button = next(item for item in save_dialog.descendants() if item.class_name() == "Button" and int(item.control_id()) == 1)
        save_button.click_input()
        # This legacy build can spend roughly 40 seconds in its printer-backed
        # document preparation before the XML appears.
        deadline = time.monotonic() + 90.0
        while time.monotonic() < deadline and not target_xml.is_file():
            time.sleep(0.1)
        if not target_xml.is_file():
            raise RuntimeError("ET XML export did not create the requested file")

        # Creation precedes the final close of the export stream. Wait until
        # the file is both readable and well-formed instead of racing it.
        deadline = time.monotonic() + 90.0
        raw = b""
        root = None
        while time.monotonic() < deadline:
            try:
                raw = target_xml.read_bytes()
                root = ET.fromstring(raw)
                break
            except (PermissionError, ET.ParseError):
                time.sleep(0.25)
        if root is None:
            raise RuntimeError("ET XML remained locked or incomplete after export")
        report["xml"] = {
            "path": str(target_xml), "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(), "root_tag": root.tag,
            "element_count": sum(1 for _ in root.iter()), "well_formed": True,
        }
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        report["copy_unchanged"] = sha256(project) == report["source_sha256"]
        report["status"] = "passed" if all((
            report["xml"]["well_formed"], report["xml"]["size"] > 0,
            report["source_unchanged"], report["copy_unchanged"],
        )) else "failed"

        # Stop the background printer connection before closing the ET form.
        for window in Desktop(backend="win32").windows(top_level_only=True):
            if int(window.process_id()) != process_id or "Várakozás a nyomtatókapcsolatra" not in window.window_text():
                continue
            cancels = [x for x in window.descendants() if x.class_name() == "Button" and x.window_text() == "Mégse"]
            if len(cancels) == 1:
                cancels[0].send_message(0x00F5)  # BM_CLICK
                time.sleep(0.5)

        report["session_closed"], report["sandbox_save_discarded"] = close_session(process_id)
        if not report["session_closed"]:
            raise RuntimeError("WinWatt process remained alive after normal ET and application close")
    except Exception as exc:
        report["status"] = "failed"; report["error"] = repr(exc)
        try:
            if process_id is not None:
                report["session_closed"], report["sandbox_save_discarded"] = close_session(process_id)
        except Exception as cleanup_exc:
            report["cleanup_error"] = repr(cleanup_exc)
    finally:
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        checkpoint()
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
