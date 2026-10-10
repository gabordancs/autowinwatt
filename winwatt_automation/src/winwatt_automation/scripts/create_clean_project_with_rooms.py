from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
from datetime import datetime, timezone
from pathlib import Path

from winwatt_automation.domain.room import RoomInput
from winwatt_automation.services.room_service import RoomService
from winwatt_automation.services.winwatt_service import WinWattService
from winwatt_automation.runtime_mapping.program_mapper import prepare_fresh_winwatt_session
from winwatt_automation.version_profile import require_profile


PROFILE_ID = "winwatt_8c137b67c0a2214bb91aeae8"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a brand-new native WinWatt project and add reviewed rooms through the UI."
    )
    parser.add_argument("--rooms-json", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--building-name", required=True)
    parser.add_argument("--profile", required=True, type=Path)
    args = parser.parse_args()

    if struct.calcsize("P") * 8 != 32:
        parser.error("WinWatt UI automation requires 32-bit Python")

    profile = require_profile(args.profile.resolve(strict=True))
    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]

    output = args.output.resolve()
    if output.exists():
        parser.error(f"output directory already exists: {output}")
    output.mkdir(parents=True)

    payload = json.loads(args.rooms_json.read_text(encoding="utf-8"))
    rooms = [RoomInput.model_validate(item) for item in payload["rooms"]]
    overlong_names = [room.name for room in rooms if len(room.name) > 30]
    if overlong_names:
        parser.error(
            "WinWatt room names are limited to 30 characters; shorten these names before UI entry: "
            + ", ".join(repr(name) for name in overlong_names)
        )
    names = [room.name.casefold() for room in rooms]
    if len(names) != len(set(names)):
        parser.error("room names must be unique within the project")

    started_at = datetime.now(timezone.utc).isoformat()
    phase = "create_empty_project"
    report: dict[str, object] = {
        "status": "failed",
        "profile_id": profile["profile_id"],
        "started_at": started_at,
        "building_name": args.building_name,
        "requested_rooms": len(rooms),
        "source_kind": "new_native_project",
        "source_wwp_used": False,
        "xml_used": False,
        "llm_used": False,
    }
    try:
        startup = prepare_fresh_winwatt_session(exe_path=profile["exe_path"])
        if not startup.get("snapshot_ready"):
            raise RuntimeError(f"WinWatt did not reach the no-project main window: {startup!r}")
        seed = WinWattService().create_empty_project(output / "sandbox" / "clean_seed.wwp")
        seed_hash = digest(seed)
        phase = "create_and_verify_rooms"
        result = RoomService().prepare_rooms(
            rooms,
            seed,
            building_name=args.building_name,
        )
        project = seed.with_name("prepared.wwp")
        report.update(
            {
                "status": "passed" if result.success and result.verified else "failed",
                "failed_phase": None if result.success and result.verified else phase,
                "seed_project": str(seed),
                "seed_sha256": seed_hash,
                "project": str(project),
                "project_sha256": digest(project) if project.is_file() else None,
                "copy_changed": project.is_file() and digest(project) != seed_hash,
                "roundtrip_passed": bool(result.verified),
                "completed_rooms": result.completed,
                "warnings": result.warnings,
                "errors": result.errors,
                "evidence": [item.model_dump(mode="json") for item in result.evidence],
            }
        )
    except Exception as exc:
        report.update({"failed_phase": phase, "errors": [repr(exc)]})
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report_path), **report}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
