"""Generate and validate a local ET certificate XML from a disposable WWP."""
from __future__ import annotations

import argparse
import base64
import ctypes
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
    parser.add_argument("--zone-name")
    parser.add_argument("--printer", default="Adobe PDF")
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
        "building_name": args.building_name, "zone_name": args.zone_name,
    }
    original_printer: str | None = None

    def checkpoint() -> None:
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def native(window: Any) -> Any:
        return Desktop(backend="win32").window(handle=int(window.handle)).wrapper_object()

    def click_unique(window: Any, caption: str) -> None:
        matches = [x for x in native(window).descendants() if x.class_name() == "TButton" and x.window_text() == caption and x.is_visible() and x.is_enabled()]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one enabled {caption!r} button, found {len(matches)}")
        matches[0].click()

    def configure_certificate_printer(window: Any, printer_name: str) -> dict[str, Any]:
        """Select the ET renderer through its printer-setup modal.

        The printer name on the ET final page is owner-drawn, so it is not a
        real combobox.  The adjacent setup button opens a native dialog whose
        controls can be driven and verified.
        """
        before_handles = {
            int(item.handle) for item in Desktop(backend="win32").windows(top_level_only=True)
        }
        setup_buttons = [
            item for item in native(window).descendants()
            if item.class_name() == "TButton" and item.window_text() == "Beállít..."
            and item.is_visible() and item.is_enabled()
        ]
        if len(setup_buttons) != 1:
            raise RuntimeError(f"Expected one enabled printer setup button, found {len(setup_buttons)}")
        # This does not print a PDF.  WinWatt nevertheless requires a valid
        # local printer renderer before it can build the e-certificate XML.
        # POST is essential: SEND blocks until the modal closes, preventing
        # this process from selecting a printer in that modal.
        if not ctypes.windll.user32.PostMessageW(int(setup_buttons[0].handle), 0x00F5, 0, 0):
            raise ctypes.WinError()
        deadline = time.monotonic() + 30.0
        setup = None
        while time.monotonic() < deadline:
            popup_handle = int(ctypes.windll.user32.GetLastActivePopup(int(window.handle)))
            if (popup_handle and popup_handle != int(window.handle)
                    and ctypes.windll.user32.IsWindowVisible(popup_handle)):
                try:
                    candidate = Desktop(backend="win32").window(handle=popup_handle).wrapper_object()
                    if candidate.is_enabled():
                        setup = candidate
                        break
                except Exception:
                    pass
            candidates = [
                item for item in Desktop(backend="win32").windows(top_level_only=True)
                if int(item.handle) not in before_handles and item.is_visible() and item.is_enabled()
            ]
            if candidates:
                setup = candidates[0]
                break
            time.sleep(0.1)
        if setup is None:
            # Some printer drivers do not show a setup modal when they are
            # already the process/default renderer.  The caller has verified
            # and broadcast the Windows default before opening WinWatt; let
            # the subsequent XML creation be the authoritative check.
            recovery = "not_needed"
            if not window.is_enabled():
                keyboard.send_keys("{ESC}")
                recovery = "escape_hidden_setup_modal"
                recovery_deadline = time.monotonic() + 5.0
                while time.monotonic() < recovery_deadline and not window.is_enabled():
                    time.sleep(0.1)
            if not window.is_enabled():
                raise RuntimeError("Printer setup left the ET final page disabled")
            # The renderer is an internal prerequisite for creating the PDF
            # payload embedded in the XML, not a standalone output.  Some
            # drivers accept the verified Windows default without showing a
            # modal.  The decoded CalculationsPdfFileContent below is the
            # authoritative result check.
            return {
                "dialog_class": None, "selected": printer_name,
                "method": "verified_windows_default_no_modal", "recovery": recovery,
            }
        setup.capture_as_image().save(str(output / "printer_setup.png"))
        controls = native(setup).descendants()
        combo_matches = []
        for item in controls:
            if item.class_name() != "ComboBox" or not item.is_visible() or not item.is_enabled():
                continue
            combo = ComboBoxWrapper(item.handle)
            try:
                values = combo.item_texts()
            except Exception:
                continue
            if printer_name in values:
                combo_matches.append((combo, values))
        if len(combo_matches) != 1:
            report["printer_setup_controls"] = [
                {
                    "class": item.class_name(), "text": item.window_text(),
                    "control_id": int(item.control_id()),
                    "rectangle": [int(item.rectangle().left), int(item.rectangle().top),
                                  int(item.rectangle().right), int(item.rectangle().bottom)],
                }
                for item in controls if item.is_visible()
            ]
            raise RuntimeError(
                f"Printer setup selector is ambiguous for {printer_name!r}: "
                f"found {len(combo_matches)}"
            )
        combo, values = combo_matches[0]
        combo.select(values.index(printer_name))
        time.sleep(0.4)
        selected = combo.selected_text()
        if selected != printer_name:
            raise RuntimeError(f"Printer setup selection did not commit: {selected!r}")
        ok_buttons = [
            item for item in controls
            if item.class_name() == "Button" and int(item.control_id()) == 1
            and item.is_visible() and item.is_enabled()
        ]
        if len(ok_buttons) != 1:
            raise RuntimeError(f"Printer setup OK button is ambiguous: {len(ok_buttons)}")
        ok_buttons[0].click()
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if window.is_visible() and window.is_enabled():
                return {"dialog_class": setup.class_name(), "selected": selected}
            time.sleep(0.1)
        raise RuntimeError("Printer setup dialog did not close")

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
        import win32print

        original_printer = win32print.GetDefaultPrinter()
        win32print.SetDefaultPrinter(args.printer)
        # WinWatt is a legacy application and reads the win.ini-compatible
        # printer setting while opening the certificate document.  It needs a
        # valid printer even when the requested output is XML.
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x001A, 0, "windows", 0x0002, 5000, None
        )
        time.sleep(1.0)
        report["printer"] = {"original": original_printer, "render": args.printer}
        dialog = open_et_document(project_path=str(project), reuse_session=False)
        process_id = int(dialog.process_id())
        report["scope"] = configure_et_scope(
            dialog, building_name=args.building_name, zone_name=args.zone_name,
            structure_scope="all",
        )
        dialog.capture_as_image().save(str(output / "step_00_scope.png"))
        # Depending on calculation state, WinWatt can omit the intermediate
        # warning page. Advance until the document-production page is reached
        # instead of assuming a fixed number of Tovább clicks.
        final_page = None
        for step in range(1, 4):
            active = _active_window(process_id)
            export_buttons = [
                item for item in native(active).descendants()
                if item.class_name() == "TButton" and item.is_visible() and item.is_enabled()
                and item.window_text().strip().casefold() == "e-tanúsítás xml export..."
            ]
            if len(export_buttons) == 1:
                final_page = active
                break
            click_unique(active, "Tovább")
            time.sleep(0.9)
            active = _active_window(process_id)
            active.capture_as_image().save(str(output / f"step_{step:02d}.png"))
        if final_page is None:
            active = _active_window(process_id)
            export_buttons = [
                item for item in native(active).descendants()
                if item.class_name() == "TButton" and item.is_visible() and item.is_enabled()
                and item.window_text().strip().casefold() == "e-tanúsítás xml export..."
            ]
            if len(export_buttons) != 1:
                raise RuntimeError("ET document-production page was not reached within three steps")
            final_page = active
        report["printer"]["certificate_setup"] = configure_certificate_printer(
            final_page, args.printer
        )
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
        report["save_dialog_filename"] = filename.window_text()
        if Path(report["save_dialog_filename"]).resolve() != target_xml.resolve():
            raise RuntimeError(
                f"Save dialog did not retain target path: {report['save_dialog_filename']!r}"
            )
        save_button = next(item for item in save_dialog.descendants() if item.class_name() == "Button" and int(item.control_id()) == 1)
        save_button.click_input()
        # This legacy build can spend roughly 40 seconds in its printer-backed
        # document preparation before the XML appears.
        deadline = time.monotonic() + 90.0
        while time.monotonic() < deadline and not target_xml.is_file():
            time.sleep(0.1)
        if not target_xml.is_file():
            report["windows_after_export_timeout"] = [
                {
                    "class": item.class_name(), "title": item.window_text(),
                    "texts": [child.window_text() for child in item.descendants() if child.window_text()][:40],
                }
                for item in Desktop(backend="win32").windows(top_level_only=True)
                if int(item.process_id()) == process_id and item.is_visible()
            ]
            for index, item in enumerate(Desktop(backend="win32").windows(top_level_only=True)):
                if int(item.process_id()) == process_id and item.is_visible():
                    try:
                        item.capture_as_image().save(str(output / f"export_timeout_{index}.png"))
                    except Exception:
                        pass
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
        embedded_nodes = [item for item in root.iter()
                          if item.tag.rsplit("}", 1)[-1] == "CalculationsPdfFileContent"]
        if len(embedded_nodes) != 1 or not (embedded_nodes[0].text or "").strip():
            raise RuntimeError(
                f"Expected one non-empty CalculationsPdfFileContent, found {len(embedded_nodes)}"
            )
        try:
            embedded_pdf = base64.b64decode("".join((embedded_nodes[0].text or "").split()), validate=True)
        except Exception as decode_exc:
            raise RuntimeError("Embedded certificate PDF is not valid Base64") from decode_exc
        embedded_pdf_valid = (
            len(embedded_pdf) > 1000
            and embedded_pdf.startswith(b"%PDF-")
            and b"%%EOF" in embedded_pdf[-4096:]
        )
        report["xml"]["embedded_pdf"] = {
            "field": "CalculationsPdfFileContent", "base64_chars": len((embedded_nodes[0].text or "").strip()),
            "decoded_bytes": len(embedded_pdf), "sha256": hashlib.sha256(embedded_pdf).hexdigest(),
            "pdf_header": embedded_pdf[:8].decode("ascii", errors="replace"),
            "has_eof_marker": b"%%EOF" in embedded_pdf[-4096:], "valid": embedded_pdf_valid,
        }
        if not embedded_pdf_valid:
            raise RuntimeError("Decoded CalculationsPdfFileContent is not a complete PDF")
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        report["copy_unchanged"] = sha256(project) == report["source_sha256"]
        report["status"] = "passed" if all((
            report["xml"]["well_formed"], report["xml"]["size"] > 0,
            report["xml"]["embedded_pdf"]["valid"],
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
        if original_printer is not None:
            try:
                import win32print

                win32print.SetDefaultPrinter(original_printer)
                ctypes.windll.user32.SendMessageTimeoutW(
                    0xFFFF, 0x001A, 0, "windows", 0x0002, 5000, None
                )
                report.setdefault("printer", {})["restored"] = (
                    win32print.GetDefaultPrinter() == original_printer
                )
            except Exception as printer_exc:
                report.setdefault("printer", {})["restore_error"] = repr(printer_exc)
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        checkpoint()
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
