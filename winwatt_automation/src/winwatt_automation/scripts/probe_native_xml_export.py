"""Export native WinWatt XML from a sandbox copy and record file evidence."""
from __future__ import annotations

import argparse
import json
import os
import shutil
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
    try:
        os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
        from winwatt_automation.runtime_mapping.room_deep_explorer import open_sandbox_buildings
        from winwatt_automation.services.winwatt_service import WinWattService
        from winwatt_automation.services.xml_native_service import NativeXmlService

        service = WinWattService()
        # The mapping launcher handles the legacy welcome screen without the
        # broad startup reconnaissance performed by WinWattService.open_project.
        open_sandbox_buildings(project_path=str(project))
        evidence = NativeXmlService().export_xml(native_xml)
        service.close_project_gracefully()
        report.update({
            "export": evidence.data,
            "native_xml_sha256": sha256(native_xml),
            "source_unchanged": sha256(source) == source_hash,
            "copy_unchanged": sha256(project) == source_hash,
            "session_closed": True,
        })
        report["status"] = "passed" if all((
            report["source_unchanged"], report["copy_unchanged"], report["session_closed"]
        )) else "failed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
    finally:
        report["source_unchanged"] = sha256(source) == source_hash
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        checkpoint()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
