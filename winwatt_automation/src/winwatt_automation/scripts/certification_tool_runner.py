"""List or execute version-bound WinWatt certification tools.

This module is the stable local entrypoint for Codex skills.  It translates a
semantic tool ID and named parameters to an already verified probe module; it
does not discover controls or ask an LLM how to operate WinWatt.
"""
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

from winwatt_automation.agent.capabilities import CertificationTool, CertificationToolRegistry
from winwatt_automation.version_profile import profile_id, require_profile


PARAMETER_FLAGS: dict[str, dict[str, tuple[str, type, bool]]] = {
    "winwatt.building.room.create_roundtrip": {
        "name": ("--name", str, True),
    },
    "winwatt.building.structure.layered.create_roundtrip": {
        "template_xml": ("--template-xml", Path, True),
        "name": ("--name", str, True),
        "layer_name": ("--layer-name", str, False),
        "thickness_cm": ("--thickness-cm", float, False),
    },
    "winwatt.building.structure.reviewed_handoff.roundtrip": {
        "template_xml": ("--template-xml", Path, True),
        "handoff": ("--handoff", Path, True),
        "catalog_xml": ("--catalog-xml", Path, True),
    },
    "winwatt.building.room.boundary.assign_roundtrip": {
        "room_name": ("--room-name", str, True),
        "structure_reference": ("--structure-reference", str, True),
        "area_m2": ("--area-m2", float, False),
    },
    "winwatt.building.orientation.roundtrip": {
        "angle": ("--angle", int, True),
    },
    "winwatt.building.system.lighting.create_roundtrip": {
        "name": ("--name", str, True),
    },
    "winwatt.building.zone.heated.roundtrip": {
        "name": ("--name", str, True),
    },
    "winwatt.building.system.heating.create_roundtrip": {
        "name": ("--name", str, True),
        "expected_zone": ("--expected-zone", str, True),
    },
    "winwatt.building.system.water_heating.create_roundtrip": {
        "name": ("--name", str, True),
    },
    "winwatt.building.system.airing.create_roundtrip": {
        "name": ("--name", str, True),
    },
    "winwatt.building.system.cooling.create_roundtrip": {
        "name": ("--name", str, True),
    },
    "winwatt.building.calculation.result_roundtrip": {},
    "winwatt.certificate.et_xml.export": {
        "building_name": ("--building-name", str, True),
    },
    "winwatt.certificate.preflight": {
        "model": ("--model", Path, True),
        "readback_xml": ("--readback-xml", Path, False),
        "catalog_xml": ("--catalog-xml", Path, False),
        "scope": ("--scope", str, False),
        "tolerance": ("--tolerance", float, False),
    },
    "winwatt.mapping.campaign.summarize": {
        "campaign": ("--campaign", Path, True),
    },
    "webwatt.certificate.intake.local": {
        "input_file": ("--input-file", Path, True),
        "catalog_xml": ("--catalog-xml", Path, False),
    },
}


def parse_parameters(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        key, separator, raw = value.partition("=")
        if not separator or not key or not raw:
            raise ValueError(f"parameter must be KEY=VALUE: {value!r}")
        if key in result:
            raise ValueError(f"duplicate parameter: {key}")
        result[key] = raw
    return result


def build_handler_arguments(
    *, tool: CertificationTool, profile: Path, source: Path | None, output: Path,
    parameters: dict[str, str],
) -> list[str]:
    specification = PARAMETER_FLAGS.get(tool.tool_id)
    if specification is None:
        raise ValueError(f"no local argument adapter for tool: {tool.tool_id}")
    unknown = set(parameters).difference(specification)
    missing = {key for key, (_, _, required) in specification.items() if required and key not in parameters}
    if unknown:
        raise ValueError(f"unknown parameters for {tool.tool_id}: {sorted(unknown)}")
    if missing:
        raise ValueError(f"missing parameters for {tool.tool_id}: {sorted(missing)}")

    if tool.safety_scope == "local_files":
        arguments = ["--output", str(output)]
    else:
        if source is None:
            raise ValueError(f"source WWP is required for {tool.tool_id}")
        arguments = [
            "--profile", str(profile), "--source", str(source), "--output", str(output),
        ]
    if tool.tool_id == "winwatt.building.orientation.roundtrip":
        arguments.append("--skip-mode-survey")
    if tool.tool_id == "winwatt.building.system.airing.create_roundtrip":
        arguments.extend(["--system", "airing"])
    if tool.tool_id == "winwatt.building.system.cooling.create_roundtrip":
        arguments.extend(["--system", "cooling"])
    for key, (flag, converter, _) in specification.items():
        if key not in parameters:
            continue
        converted = converter(parameters[key])
        arguments.extend([flag, str(converted)])
    return arguments


def execute(
    *, tool_id: str, profile_path: Path, source: Path | None, output: Path,
    parameters: dict[str, str], registry: CertificationToolRegistry,
) -> dict[str, Any]:
    profile_path = profile_path.resolve(strict=True)
    recorded_profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if profile_id(recorded_profile) != recorded_profile.get("profile_id"):
        raise ValueError("profile identity does not match its recorded contents")
    preliminary = registry.require_executable(tool_id, profile_id=recorded_profile["profile_id"])
    if preliminary.safety_scope == "local_files":
        profile = recorded_profile
        resolved_source = None
    else:
        if struct.calcsize("P") * 8 != 32:
            raise RuntimeError("WinWatt tool execution requires 32-bit Python")
        profile = require_profile(profile_path)
        if source is None:
            raise ValueError("--source is required for WinWatt UI tools")
        resolved_source = source.resolve(strict=True)
        if resolved_source.suffix.lower() != ".wwp":
            raise ValueError("source must be a WWP project")
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"output must be a new path: {output}")
    tool = registry.require_executable(tool_id, profile_id=profile["profile_id"])
    arguments = build_handler_arguments(
        tool=tool, profile=profile_path, source=resolved_source, output=output,
        parameters=parameters,
    )
    project_root = Path(__file__).resolve().parents[3]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project_root / "src")
    environment["PYTHONIOENCODING"] = "utf-8"
    started_at = datetime.now(timezone.utc).isoformat()
    completed = subprocess.run(
        [sys.executable, "-m", tool.handler or "", *arguments],
        cwd=project_root, env=environment, check=False,
    )
    report_path = output / tool.output_contract.get("report", "report.json")
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else None
    invocation = {
        "schema_version": 1,
        "tool_id": tool.tool_id,
        "tool_version": tool.version,
        "handler": tool.handler,
        "profile_id": profile["profile_id"],
        "source": str(resolved_source) if resolved_source else None,
        "output": str(output),
        "parameters": parameters,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "exit_code": int(completed.returncode),
        "report": str(report_path) if report is not None else None,
        "report_status": report.get("status") if report else None,
        "llm_used": False,
    }
    if output.is_dir():
        (output / "tool_invocation.json").write_text(
            json.dumps(invocation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return invocation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--list", action="store_true", help="List executable tool contracts")
    action.add_argument("--describe", metavar="TOOL_ID", help="Show one tool contract")
    action.add_argument("--tool-id", help="Execute one verified tool")
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    args = parser.parse_args()
    registry = CertificationToolRegistry.load()

    if args.list:
        print(json.dumps(
            [tool.model_dump(mode="json") for tool in registry.list(include_observed=False)],
            ensure_ascii=False, indent=2,
        ))
        return 0
    if args.describe:
        tool = registry.get(args.describe)
        if tool is None:
            parser.error(f"unknown tool: {args.describe}")
        print(json.dumps(tool.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0
    if not all((args.profile, args.output)):
        parser.error("--tool-id requires --profile and --output")
    try:
        result = execute(
            tool_id=args.tool_id, profile_path=args.profile, source=args.source,
            output=args.output, parameters=parse_parameters(args.param), registry=registry,
        )
    except (ValueError, KeyError, PermissionError, OSError, RuntimeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    accepted = {"passed", "review_required"} if registry.get(args.tool_id).safety_scope == "local_files" else {"passed"}
    return 0 if result["exit_code"] == 0 and result["report_status"] in accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
