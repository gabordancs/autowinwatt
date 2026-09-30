"""Run the verified heated-zone and electric-heating tools as one workflow."""
from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from winwatt_automation.agent.capabilities import CertificationToolRegistry
from winwatt_automation.version_profile import require_profile, sha256


ZONE_TOOL = "winwatt.building.zone.heated.roundtrip"
HEATING_TOOL = "winwatt.building.system.heating.create_roundtrip"


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def validate_workflow_reports(
    *, zone: dict[str, Any], heating: dict[str, Any], profile_id: str,
    source_sha256: str, final_source_sha256: str,
) -> list[str]:
    errors: list[str] = []
    checks = (
        (zone.get("profile_id") == profile_id, "zone profile mismatch"),
        (zone.get("status") == "passed", "zone tool did not pass"),
        (zone.get("roundtrip_passed") is True, "zone roundtrip failed"),
        (zone.get("source_unchanged") is True, "zone tool changed its source"),
        (heating.get("profile_id") == profile_id, "heating profile mismatch"),
        (heating.get("status") == "passed", "heating tool did not pass"),
        (heating.get("system_roundtrip_passed") is True, "heating-system roundtrip failed"),
        (heating.get("zone_roundtrip_passed") is True, "heated zone did not survive heating roundtrip"),
        (heating.get("source_unchanged") is True, "heating tool changed its source"),
        (heating.get("copy_changed") is True, "heating output copy did not change"),
        (source_sha256 == final_source_sha256, "workflow changed the original source"),
    )
    for passed, message in checks:
        if not passed:
            errors.append(message)
    return errors


def run_module(module: str, arguments: list[str], *, cwd: Path, log: Path) -> int:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(cwd / "src")
    environment["PYTHONIOENCODING"] = "utf-8"
    with log.open("w", encoding="utf-8", errors="replace") as stream:
        completed = subprocess.run(
            [sys.executable, "-m", module, *arguments],
            cwd=cwd, env=environment, stdout=stream, stderr=subprocess.STDOUT,
            check=False,
        )
    return int(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--zone-name", default="AUTO_HEATED_ZONE_WORKFLOW")
    parser.add_argument("--system-name", default="AUTO_HEATING_WORKFLOW")
    args = parser.parse_args()
    if struct.calcsize("P") * 8 != 32:
        parser.error("This workflow requires 32-bit Python")

    profile_path = args.profile.resolve(strict=True)
    profile = require_profile(profile_path)
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source_hash = sha256(source)
    registry = CertificationToolRegistry.load()
    zone_tool = registry.require_executable(ZONE_TOOL, profile_id=profile["profile_id"])
    heating_tool = registry.require_executable(HEATING_TOOL, profile_id=profile["profile_id"])
    project_root = Path(__file__).resolve().parents[3]
    state_path = output / "workflow_report.json"
    state: dict[str, Any] = {
        "schema_version": 1,
        "workflow": "winwatt.heating_certification_fixture",
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "profile_id": profile["profile_id"],
        "source": str(source),
        "source_sha256": source_hash,
        "zone_name": args.zone_name,
        "system_name": args.system_name,
        "tools": [
            {"tool_id": zone_tool.tool_id, "version": zone_tool.version},
            {"tool_id": heating_tool.tool_id, "version": heating_tool.version},
        ],
        "llm_used": False,
        "steps": [],
        "errors": [],
    }
    atomic_json(state_path, state)

    zone_output = output / "01_heated_zone"
    zone_log = output / "01_heated_zone.log"
    zone_code = run_module(
        zone_tool.handler or "",
        ["--profile", str(profile_path), "--source", str(source),
         "--output", str(zone_output), "--name", args.zone_name],
        cwd=project_root, log=zone_log,
    )
    zone_report_path = zone_output / "report.json"
    zone_report = json.loads(zone_report_path.read_text(encoding="utf-8"))
    state["steps"].append({
        "tool_id": zone_tool.tool_id, "exit_code": zone_code,
        "report": str(zone_report_path), "status": zone_report.get("status"),
    })
    atomic_json(state_path, state)
    if zone_code != 0 or zone_report.get("status") != "passed":
        state["status"] = "failed"
        state["errors"].append("heated-zone tool failed")
        state["finished_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(state_path, state)
        return 1

    heating_output = output / "02_heating_system"
    heating_log = output / "02_heating_system.log"
    heating_code = run_module(
        heating_tool.handler or "",
        ["--profile", str(profile_path), "--source", str(zone_output / "testwwp.wwp"),
         "--output", str(heating_output), "--name", args.system_name,
         "--expected-zone", args.zone_name],
        cwd=project_root, log=heating_log,
    )
    heating_report_path = heating_output / "report.json"
    heating_report = json.loads(heating_report_path.read_text(encoding="utf-8"))
    state["steps"].append({
        "tool_id": heating_tool.tool_id, "exit_code": heating_code,
        "report": str(heating_report_path), "status": heating_report.get("status"),
    })
    state["final_project"] = str(heating_output / "testwwp.wwp")
    state["final_project_sha256"] = sha256(heating_output / "testwwp.wwp")
    state["errors"] = validate_workflow_reports(
        zone=zone_report, heating=heating_report, profile_id=profile["profile_id"],
        source_sha256=source_hash, final_source_sha256=sha256(source),
    )
    if heating_code != 0:
        state["errors"].append(f"heating tool exit code: {heating_code}")
    state["status"] = "passed" if not state["errors"] else "failed"
    state["finished_at"] = datetime.now(timezone.utc).isoformat()
    atomic_json(state_path, state)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0 if state["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
