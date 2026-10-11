"""Import a complete native XML into a disposable WWP and verify zone readback."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import struct
import time
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from winwatt_automation.services.winwatt_service import WinWattService
from winwatt_automation.services.xml_native_service import NativeXmlService
from winwatt_automation.version_profile import require_profile


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_text(element: ET.Element, name: str) -> str | None:
    return next(((child.text or "").strip() for child in element if local(child.tag) == name), None)


def zone_snapshot(path: Path, zone_name: str) -> dict:
    root = ET.parse(path).getroot()
    zones = [item for item in root.iter() if local(item.tag) == "ETZone" and item.attrib.get("Name") == zone_name]
    if len(zones) != 1:
        raise ValueError(f"Expected one ETZone {zone_name!r}, found {len(zones)}")
    room_ids = [item.attrib["ID"] for item in zones[0] if local(item.tag) == "RoomAreaItem" and item.attrib.get("ID")]
    rooms = []
    for room in (item for item in root.iter() if local(item.tag) == "WinWatt32Room"):
        header = next((child for child in room if local(child.tag) == "ItemHeader"), None)
        if header is None or child_text(header, "ID") not in room_ids:
            continue
        boundaries = []
        for boundary in (child for child in room if local(child.tag) == "Boundary"):
            boundaries.append({key: child_text(boundary, key) for key in ("Name", "Type", "x", "y", "A", "MinA", "Compass")})
        rooms.append({
            "id": child_text(header, "ID"), "name": child_text(header, "ItemName"),
            "function": child_text(room, "Function"), "area": child_text(room, "Area"),
            "height": child_text(room, "Height"), "boundaries": boundaries,
        })
    return {"zone": zone_name, "room_ids": room_ids, "rooms": rooms}


def semantic_zone_snapshot(snapshot: dict) -> dict:
    """Remove volatile import IDs while retaining resolved zone membership."""
    return {
        "zone": snapshot["zone"],
        "rooms": [
            {key: value for key, value in room.items() if key != "id"}
            for room in snapshot["rooms"]
        ],
    }


def semantic_zone_equal(expected: dict, actual: dict, *, numeric_tolerance: float = 5e-5) -> bool:
    """Compare import readback while allowing WinWatt's four-decimal rounding."""
    def equal(left, right) -> bool:
        if isinstance(left, dict) and isinstance(right, dict):
            return left.keys() == right.keys() and all(equal(left[key], right[key]) for key in left)
        if isinstance(left, list) and isinstance(right, list):
            return len(left) == len(right) and all(equal(a, b) for a, b in zip(left, right))
        if isinstance(left, str) and isinstance(right, str):
            try:
                return abs(float(left) - float(right)) <= numeric_tolerance
            except ValueError:
                return left == right
        return left == right

    return equal(semantic_zone_snapshot(expected), semantic_zone_snapshot(actual))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path, help="Immutable seed WWP used only to start WinWatt")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--native-xml", required=True, type=Path)
    parser.add_argument(
        "--expected-native-xml", type=Path,
        help="Optional pre-rebase XML containing the semantic expected zone",
    )
    parser.add_argument("--zone", required=True)
    args = parser.parse_args()
    if struct.calcsize("P") * 8 != 32:
        parser.error("requires 32-bit Python")
    profile = require_profile(args.profile.resolve(strict=True))
    source = args.source.resolve(strict=True)
    native_xml = args.native_xml.resolve(strict=True)
    expected_native_xml = (
        args.expected_native_xml.resolve(strict=True)
        if args.expected_native_xml else native_xml
    )
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"output must be new: {output}")
    output.mkdir(parents=True)
    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    source_hash, xml_hash = digest(source), digest(native_xml)
    report = {
        "schema_version": 1, "operation": "native_project_import_roundtrip",
        "profile_id": profile["profile_id"], "source": str(source), "source_sha256": source_hash,
        "native_xml": str(native_xml), "native_xml_sha256": xml_hash, "zone": args.zone,
        "started_at": datetime.now(timezone.utc).isoformat(), "status": "failed", "llm_used": False,
    }
    service = WinWattService()
    owned_process_id: int | None = None
    phase = "snapshot_import"
    try:
        expected = zone_snapshot(expected_native_xml, args.zone)
        phase = "open_seed"
        service.open_project(source)
        phase = "create_empty_project"
        project = service.create_empty_project(output / "sandbox" / "imported.wwp")
        # create_empty_project can return after the process is launched but
        # before a slow TMainForm becomes discoverable.  Wait for the exact
        # project window instead of treating this startup race as an import
        # failure.
        from winwatt_automation.live_ui.app_connector import (
            WinWattNotRunningError,
            get_main_window,
            reset_winwatt_connection_cache,
        )
        startup_deadline = time.monotonic() + 60.0
        stable_ready_polls = 0
        while True:
            try:
                reset_winwatt_connection_cache()
                startup_main = get_main_window()
                if (project.stem.casefold() in startup_main.window_text().casefold()
                        and startup_main.is_visible() and startup_main.is_enabled()):
                    owned_process_id = int(startup_main.process_id())
                    stable_ready_polls += 1
                else:
                    stable_ready_polls = 0
                # TMainForm can appear briefly before its menu/import command
                # is usable. Require a stable enabled window across three
                # independent cache resets before opening XML Import.
                if stable_ready_polls >= 3:
                    break
            except WinWattNotRunningError:
                stable_ready_polls = 0
            if time.monotonic() >= startup_deadline:
                raise RuntimeError("Imported-project WinWatt window did not become ready within 60 seconds")
            time.sleep(0.5)
        phase = "import_xml"
        import_evidence = NativeXmlService().import_xml(native_xml)
        phase = "save_project"
        service.save_project()
        phase = "close_after_save"
        service.close_project_gracefully()
        phase = "reopen_project"
        service.open_project(project)
        phase = "export_readback"
        readback = output / "reopen_readback.xml"
        export_evidence = NativeXmlService().export_xml(readback)
        phase = "compare_zone"
        actual = zone_snapshot(readback, args.zone)
        semantic_equal = semantic_zone_equal(expected, actual)
        report.update({
            "project": str(project), "readback_xml": str(readback),
            "import_evidence": import_evidence.model_dump(mode="json"),
            "export_evidence": export_evidence.model_dump(mode="json"),
            "expected_native_xml": str(expected_native_xml),
            "zone_references_resolved": len(actual["rooms"]) == len(actual["room_ids"]),
            "zone_roundtrip_equal": semantic_equal,
            "expected_zone": expected, "actual_zone": actual,
        })
        service.close_project_gracefully()
        report["session_closed"] = True
        report["source_unchanged"] = digest(source) == source_hash
        report["native_xml_unchanged"] = digest(native_xml) == xml_hash
        report["status"] = "passed" if all((
            report["zone_references_resolved"], report["zone_roundtrip_equal"], report["source_unchanged"],
            report["native_xml_unchanged"], report["session_closed"],
        )) else "failed"
    except Exception as exc:
        report["failed_phase"] = phase
        report["error"] = repr(exc)
        report["traceback"] = traceback.format_exc()
        if phase == "import_xml":
            try:
                from pywinauto import Desktop
                windows = []
                for index, window in enumerate(Desktop(backend="win32").windows(top_level_only=True)):
                    if not window.is_visible():
                        continue
                    data = {
                        "index": index, "process_id": int(window.process_id()),
                        "class_name": window.class_name(), "title": window.window_text(),
                        "enabled": window.is_enabled(),
                        "children": [
                            {"class_name": child.class_name(), "title": child.window_text(), "control_id": int(child.control_id())}
                            for child in window.descendants() if child.is_visible()
                        ][:80],
                    }
                    windows.append(data)
                    if int(window.process_id()) == getattr(service, "process_id", int(window.process_id())):
                        try:
                            window.capture_as_image().save(str(output / f"failed_import_window_{index}.png"))
                        except Exception:
                            pass
                report["visible_windows_at_failure"] = windows
            except Exception as diagnostic_exc:
                report["diagnostic_error"] = repr(diagnostic_exc)
        try:
            service.close_project_gracefully()
        except Exception as cleanup_exc:
            report["cleanup_error"] = repr(cleanup_exc)
            # Only terminate the exact sandbox process discovered above. It
            # was created by this probe and failed normal cleanup; never touch
            # an unrelated WinWatt session.
            if owned_process_id is not None:
                try:
                    from pywinauto import Desktop
                    owned_windows = [
                        item for item in Desktop(backend="win32").windows(top_level_only=True)
                        if int(item.process_id()) == owned_process_id
                    ]
                    if owned_windows and any(project.stem.casefold() in item.window_text().casefold()
                                             for item in owned_windows):
                        os.kill(owned_process_id, signal.SIGTERM)
                        report["owned_failed_process_terminated"] = True
                except Exception as terminate_exc:
                    report["owned_failed_process_terminate_error"] = repr(terminate_exc)
    finally:
        report["source_unchanged"] = digest(source) == source_hash
        report["native_xml_unchanged"] = digest(native_xml) == xml_hash
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report.get(key) for key in ("status", "failed_phase", "error", "project", "zone_roundtrip_equal")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
