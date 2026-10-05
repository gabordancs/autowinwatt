"""Export native WinWatt XML from a sandbox copy and record file evidence."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
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
    project = output / source.name
    shutil.copy2(source, project)
    native_xml = output / "native_project.xml"
    source_hash = sha256(source)
    report = {
        "schema_version": 1,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "profile_id": profile["profile_id"],
        "source": str(source),
        "source_sha256": source_hash,
        "project": str(project),
        "native_xml": str(native_xml),
        "status": "running",
    }

    def checkpoint() -> None:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    checkpoint()
    process: subprocess.Popen[bytes] | None = None
    try:
        os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
        import ctypes
        from pywinauto import Desktop

        # Launch and address the Delphi window directly. This path deliberately
        # avoids foreground-sensitive mapping startup probes: a heartbeat often
        # runs while Codex itself owns the foreground window.
        process = subprocess.Popen([profile["exe_path"], str(project)])
        deadline = time.monotonic() + 75.0
        main = None
        stable_handle = None
        stable_count = 0
        while time.monotonic() < deadline:
            # Offline startup can block behind the known version-check prompt.
            for startup_dialog in Desktop(backend="win32").windows(top_level_only=True):
                if int(startup_dialog.process_id()) != process.pid or startup_dialog.class_name() != "#32770":
                    continue
                texts = " ".join(
                    str(control.window_text() or "")
                    for control in [startup_dialog, *startup_dialog.descendants()]
                ).casefold()
                if "verzió ellenőrzés sikertelen" in texts:
                    buttons = [
                        button for button in startup_dialog.descendants(class_name="Button")
                        if button.window_text().replace("&", "").strip().casefold() == "nem"
                    ]
                    if len(buttons) == 1:
                        buttons[0].send_message(0x00F5)
                        time.sleep(0.3)
            candidates = [
                item for item in Desktop(backend="win32").windows(top_level_only=True)
                if int(item.process_id()) == process.pid and item.class_name() == "TMainForm"
                and item.is_visible() and item.is_enabled()
            ]
            if candidates:
                candidate = max(candidates, key=lambda item: item.rectangle().width() * item.rectangle().height())
                handle = int(candidate.handle)
                project_loaded = " - " in candidate.window_text() and project.stem.casefold() in candidate.window_text().casefold()
                if handle == stable_handle and project_loaded:
                    stable_count += 1
                else:
                    stable_handle = handle
                    stable_count = 1
                if stable_count >= 8:
                    main = candidate
                    break
            time.sleep(0.25)
        if main is None:
            raise RuntimeError("WinWatt TMainForm did not become ready")

        # MainForm.XMLExportAction is command 9 on this exact version profile.
        if not ctypes.windll.user32.PostMessageW(int(main.handle), 0x0111, 9, 0):
            raise ctypes.WinError()
        deadline = time.monotonic() + 8.0
        dialog = None
        while time.monotonic() < deadline:
            matches = [
                item for item in Desktop(backend="win32").windows(top_level_only=True)
                if int(item.process_id()) == process.pid and item.class_name() == "#32770"
                and item.is_visible() and item.is_enabled()
                and any(child.class_name() == "Edit" and int(child.control_id()) == 1001
                        for child in item.descendants())
            ]
            if matches:
                dialog = matches[0]
                break
            time.sleep(0.1)
        if dialog is None:
            raise RuntimeError("Native XML save dialog did not open")
        filename = next(child for child in dialog.descendants()
                        if child.class_name() == "Edit" and int(child.control_id()) == 1001)
        filename.set_edit_text(str(native_xml))
        save = next(child for child in dialog.descendants()
                    if child.class_name() == "Button" and int(child.control_id()) == 1)
        save.send_message(0x00F5)  # BM_CLICK
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and not native_xml.is_file():
            time.sleep(0.1)
        if not native_xml.is_file():
            raise RuntimeError("Native XML file was not created")
        root = ET.parse(native_xml).getroot()
        evidence = {"path": str(native_xml), "root_tag": root.tag,
                    "bytes": native_xml.stat().st_size}

        main.post_message(0x0010)  # WM_CLOSE
        try:
            process.wait(timeout=20.0)
        except subprocess.TimeoutExpired:
            raise RuntimeError("WinWatt did not close after native XML export")
        report.update({
            "export": evidence,
            "native_xml_sha256": sha256(native_xml),
            "source_unchanged": sha256(source) == source_hash,
            "copy_unchanged": sha256(project) == source_hash,
            "session_closed": process.poll() is not None,
        })
        report["status"] = "passed" if all((
            report["source_unchanged"], report["copy_unchanged"], report["session_closed"]
        )) else "failed"
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
        report["source_unchanged"] = sha256(source) == source_hash
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        checkpoint()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
