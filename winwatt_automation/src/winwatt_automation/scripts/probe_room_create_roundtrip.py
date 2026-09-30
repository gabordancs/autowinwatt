"""Create one room on a disposable WWP copy and prove UI save/reopen readback."""
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
from winwatt_automation.version_profile import require_profile


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    if struct.calcsize("P") * 8 != 32:
        parser.error("requires 32-bit Python")
    profile = require_profile(args.profile.resolve(strict=True))
    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"output must be new: {output}")
    output.mkdir(parents=True)
    source_before = sha256(source)
    report: dict[str, object] = {
        "schema_version": 1, "tool_id": "winwatt.building.room.create_roundtrip",
        "profile_id": profile["profile_id"], "source": str(source),
        "source_sha256": source_before, "name": args.name, "llm_used": False,
        "started_at": datetime.now(timezone.utc).isoformat(), "status": "failed",
    }
    service = WinWattService()
    try:
        sandbox = service.create_sandbox(source, output / "sandbox" / "input.wwp")
        copied_before = sha256(sandbox)
        result = RoomService().prepare_rooms([
            RoomInput(name=args.name),
        ], sandbox)
        persisted = sandbox.with_name("prepared.wwp")
        report.update({
            "project": str(persisted), "operation": result.model_dump(mode="json"),
            "roundtrip_passed": bool(result.success and result.verified),
            "copy_changed": persisted.is_file() and sha256(persisted) != copied_before,
        })
    except Exception as exc:
        report["error"] = repr(exc)
    finally:
        try:
            service.close_project_gracefully()
        except Exception:
            pass
    report["source_unchanged"] = sha256(source) == source_before
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["status"] = "passed" if all((
        report.get("roundtrip_passed"), report.get("source_unchanged"), report.get("copy_changed"),
    )) else "failed"
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
