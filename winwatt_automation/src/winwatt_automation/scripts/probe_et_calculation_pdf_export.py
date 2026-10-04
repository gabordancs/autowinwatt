"""Export and validate the ET calculation PDF from a disposable WWP."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from winwatt_automation.version_profile import require_profile, sha256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--building-name", required=True)
    parser.add_argument("--printer", default="Adobe PDF")
    parser.add_argument("--configure-printer", action="store_true")
    parser.add_argument("--export-mode", choices=("pdf", "rtf"), default="pdf")
    args = parser.parse_args()

    profile = require_profile(args.profile)
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = output / "testwwp.wwp"
    target_pdf = output / "calculation.pdf"
    target_rtf = output / "calculation.rtf"
    shutil.copy2(source, project)
    source_hash = sha256(source)
    report: dict[str, Any] = {
        "schema_version": 1,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "profile_id": profile["profile_id"],
        "source": str(source),
        "source_sha256": source_hash,
        "project": str(project),
        "target_pdf": str(target_pdf),
        "status": "running",
    }

    def checkpoint() -> None:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def process_is_alive(pid: int) -> bool:
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(ctypes.windll.kernel32.GetExitCodeProcess(
                handle, ctypes.byref(code)
            )) and code.value == 259
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)

    def discard_sandbox_save_prompt(pid: int, desktop: Any) -> bool:
        for window in desktop.windows(top_level_only=True):
            if int(window.process_id()) != pid or window.class_name() != "#32770" or not window.is_visible():
                continue
            messages = [x.window_text() for x in window.descendants() if x.class_name() == "Static"]
            if not any("Az adatok változtak" in message for message in messages):
                continue
            buttons = [x for x in window.descendants()
                       if x.class_name() == "Button" and int(x.control_id()) == 7]
            if len(buttons) == 1:
                buttons[0].post_message(0x00F5)
                time.sleep(0.4)
                return True
        return False

    def close_session(pid: int, desktop: Any) -> tuple[bool, bool]:
        discarded = False
        deadline = time.monotonic() + 35.0
        while time.monotonic() < deadline and process_is_alive(pid):
            if discard_sandbox_save_prompt(pid, desktop):
                discarded = True
                continue
            windows = [w for w in desktop.windows(top_level_only=True)
                       if int(w.process_id()) == pid and w.is_visible() and w.is_enabled()]
            mains = [w for w in windows if w.class_name() == "TMainForm"]
            modals = [w for w in windows if w.class_name() != "TMainForm"]
            target = modals[0] if modals else (mains[0] if mains else None)
            if target is not None:
                target.post_message(0x0010)
            time.sleep(0.3)
        return not process_is_alive(pid), discarded

    checkpoint()
    process: subprocess.Popen[bytes] | None = None
    original_printer: str | None = None
    try:
        from pywinauto import Desktop, keyboard
        from pywinauto.application import Application
        import win32print
        from winwatt_automation.runtime_mapping.et_document import configure_et_scope
        from winwatt_automation.runtime_mapping.room_deep_explorer import _active_window

        os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
        render_printer = args.printer
        if args.export_mode == "pdf":
            original_printer = win32print.GetDefaultPrinter()
            win32print.SetDefaultPrinter(render_printer)
            # Notify legacy applications that still read the win.ini-compatible
            # default printer setting during startup.
            ctypes.windll.user32.SendMessageTimeoutW(
                0xFFFF, 0x001A, 0, "windows", 0x0002, 5000, None
            )
            time.sleep(1.0)
            report["printer"] = {"original": original_printer, "render": render_printer}
        process = subprocess.Popen([profile["exe_path"], str(project)])
        deadline = time.monotonic() + 75.0
        main = None
        stable_handle = None
        stable_count = 0
        while time.monotonic() < deadline:
            for startup_dialog in Desktop(backend="win32").windows(top_level_only=True):
                if int(startup_dialog.process_id()) != process.pid or startup_dialog.class_name() != "#32770":
                    continue
                text = " ".join(str(c.window_text() or "") for c in [startup_dialog, *startup_dialog.descendants()]).casefold()
                if "verzió ellenőrzés sikertelen" in text:
                    buttons = [b for b in startup_dialog.descendants(class_name="Button")
                               if b.window_text().replace("&", "").strip().casefold() == "nem"]
                    if len(buttons) == 1:
                        buttons[0].send_message(0x00F5)
                        time.sleep(0.3)
            candidates = [w for w in Desktop(backend="win32").windows(top_level_only=True)
                          if int(w.process_id()) == process.pid and w.class_name() == "TMainForm"
                          and w.is_visible() and w.is_enabled()]
            if candidates:
                candidate = max(candidates, key=lambda w: w.rectangle().width() * w.rectangle().height())
                handle = int(candidate.handle)
                loaded = " - " in candidate.window_text() and project.stem.casefold() in candidate.window_text().casefold()
                stable_count = stable_count + 1 if handle == stable_handle and loaded else 1
                stable_handle = handle
                if stable_count >= 8:
                    main = candidate
                    break
            time.sleep(0.25)
        if main is None:
            raise RuntimeError("WinWatt project window did not become ready")

        native_main = Application(backend="win32").connect(process=process.pid).window(handle=int(main.handle))
        file_menu = next(item for item in native_main.menu().items() if int(item.item_id()) == 1)
        file_menu.click()
        time.sleep(0.15)
        et_item = next(item for item in file_menu.sub_menu().items() if int(item.item_id()) == 18)
        et_item.click()
        time.sleep(0.4)
        # Owner-drawn menu dispatch can be dropped; the profile-bound command
        # message is the deterministic retry used by the established ET tool.
        if not any(int(w.process_id()) == process.pid and w.class_name() == "TETDocumentForm"
                   for w in Desktop(backend="uia").windows(top_level_only=True)):
            if not ctypes.windll.user32.PostMessageW(int(main.handle), 0x0111, 18, 0):
                raise ctypes.WinError()
        deadline = time.monotonic() + 15.0
        wizard = None
        while time.monotonic() < deadline:
            windows = [w for w in Desktop(backend="uia").windows(top_level_only=True)
                       if int(w.process_id()) == process.pid and w.class_name() == "TETDocumentForm"
                       and w.is_visible() and w.is_enabled()]
            if windows:
                wizard = windows[0]
                break
            time.sleep(0.15)
        if wizard is None:
            raise RuntimeError("ET wizard did not open")

        report["scope"] = configure_et_scope(
            wizard, building_name=args.building_name, structure_scope="all"
        )
        wizard.capture_as_image().save(str(output / "step_00_scope.png"))

        def click_unique(window: Any, caption: str) -> None:
            native = Desktop(backend="win32").window(handle=int(window.handle)).wrapper_object()
            matches = [x for x in native.descendants() if x.class_name() == "TButton"
                       and x.window_text() == caption and x.is_visible() and x.is_enabled()]
            if len(matches) != 1:
                raise RuntimeError(f"Expected one enabled {caption!r} button, found {len(matches)}")
            matches[0].post_message(0x00F5)

        for step in (1, 2):
            active = _active_window(process.pid)
            click_unique(active, "Tovább")
            time.sleep(0.9)
            _active_window(process.pid).capture_as_image().save(str(output / f"step_{step:02d}.png"))

        final_page = _active_window(process.pid)
        final_page.capture_as_image().save(str(output / "final_page.png"))

        if args.export_mode == "pdf" and args.configure_printer:
            # Optional diagnostic path for drivers with a usable setup dialog.
            click_unique(final_page, "Beállít...")
            time.sleep(0.8)
            final_page = _active_window(process.pid)
        export_target = target_pdf if args.export_mode == "pdf" else target_rtf
        export_caption = "PDF fájlba..." if args.export_mode == "pdf" else "Export fájlba..."
        click_unique(final_page, export_caption)

        deadline = time.monotonic() + 30.0
        save_dialog = None
        while time.monotonic() < deadline:
            dialogs = []
            for candidate in Desktop(backend="win32").windows(top_level_only=True):
                if (int(candidate.process_id()) != process.pid or candidate.class_name() != "#32770"
                        or not candidate.is_visible() or not candidate.is_enabled()):
                    continue
                descendants = candidate.descendants()
                ready_edit = any(c.class_name() == "Edit" and int(c.control_id()) == 1001
                                 and c.is_visible() and c.is_enabled() for c in descendants)
                ready_save = any(c.class_name() == "Button" and int(c.control_id()) == 1
                                 and c.is_visible() and c.is_enabled() for c in descendants)
                if ready_edit and ready_save:
                    dialogs.append(candidate)
            if dialogs:
                save_dialog = dialogs[0]
                break
            time.sleep(0.1)
        if save_dialog is None:
            raise RuntimeError("PDF save dialog did not open")
        save_dialog.capture_as_image().save(str(output / "pdf_save_dialog.png"))
        filename = next(c for c in save_dialog.descendants()
                        if c.class_name() == "Edit" and int(c.control_id()) == 1001)
        filename.set_edit_text(str(export_target))
        save_dialog.capture_as_image().save(str(output / "save_dialog_filled.png"))
        filename.set_focus()
        keyboard.send_keys("{ENTER}")

        deadline = time.monotonic() + 120.0
        stable_size = None
        stable_checks = 0
        while time.monotonic() < deadline:
            if export_target.is_file():
                size = export_target.stat().st_size
                stable_checks = stable_checks + 1 if size == stable_size and size > 0 else 0
                stable_size = size
                if stable_checks >= 5:
                    break
            time.sleep(0.25)
        if not export_target.is_file() or export_target.stat().st_size == 0:
            raise RuntimeError(f"{args.export_mode.upper()} export did not create a non-empty file")
        if args.export_mode == "rtf":
            exported = export_target.read_bytes()
            if not exported.lstrip().startswith(b"{\\rtf"):
                raise RuntimeError("WinWatt file export is not RTF")
            import win32com.client
            word = win32com.client.DispatchEx("Word.Application")
            try:
                word.Visible = False
                word.DisplayAlerts = 0
                document = word.Documents.Open(
                    str(target_rtf), ConfirmConversions=False, ReadOnly=True,
                    AddToRecentFiles=False, OpenAndRepair=True,
                )
                try:
                    document.ExportAsFixedFormat(
                        str(target_pdf), 17, OpenAfterExport=False,
                        OptimizeFor=0, Range=0, Item=0, IncludeDocProps=True,
                        KeepIRM=True, CreateBookmarks=1, DocStructureTags=True,
                        BitmapMissingFonts=True, UseISO19005_1=False,
                    )
                finally:
                    document.Close(False)
            finally:
                word.Quit()
            report["conversion"] = {
                "source": str(target_rtf),
                "source_sha256": hashlib.sha256(exported).hexdigest(),
                "converter": "Microsoft Word 16 COM",
            }
        raw = target_pdf.read_bytes()
        if not raw.startswith(b"%PDF-"):
            raise RuntimeError("Exported file has no PDF signature")
        report["pdf"] = {
            "path": str(target_pdf), "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(), "signature": raw[:8].decode("ascii", "replace"),
        }
        report["source_unchanged"] = sha256(source) == source_hash
        report["copy_unchanged"] = sha256(project) == source_hash
        report["status"] = "passed" if report["source_unchanged"] and report["copy_unchanged"] else "failed"

        closed, discarded = close_session(process.pid, Desktop(backend="win32"))
        report["sandbox_save_discarded"] = discarded
        if not closed:
            raise RuntimeError("WinWatt did not close normally after PDF export")
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5.0)
        report["session_closed"] = process is None or process.poll() is not None
        if original_printer is not None:
            try:
                import win32print
                win32print.SetDefaultPrinter(original_printer)
                report.setdefault("printer", {})["restored"] = win32print.GetDefaultPrinter() == original_printer
            except Exception as printer_exc:
                report.setdefault("printer", {})["restore_error"] = repr(printer_exc)
        report["source_unchanged"] = sha256(source) == source_hash
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        checkpoint()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" and report["session_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
