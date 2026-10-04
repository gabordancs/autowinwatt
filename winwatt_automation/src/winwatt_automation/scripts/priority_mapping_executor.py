"""Run prioritized building-failure retries, then a version-bound room crawl."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PRIORITIES = [
    "bivalencia",
    "becsult eves fogyasztas",
    "hoszukseglet",
    "nyari hoterheles",
    "felujitasi utlevel",
    "felujitas",
    "export",
    "import",
    "pdf",
    "foto",
    "epulettechnikai rendszerek",
    "helyisegek",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_stage(*, name: str, command: list[str], output: Path, state: dict[str, Any], state_path: Path) -> int:
    log_path = output / f"{name}.log"
    state["current_stage"] = name
    state["stages"][name] = {"status": "running", "started_at": utc_now(), "log": str(log_path)}
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        state["current_pid"] = process.pid
        while process.poll() is None:
            state["heartbeat_at"] = utc_now()
            atomic_json(state_path, state)
            time.sleep(5)
        code = int(process.returncode or 0)
    state["stages"][name].update({
        "status": "passed" if code == 0 else "failed",
        "finished_at": utc_now(), "exit_code": code,
    })
    state["current_pid"] = None
    state["heartbeat_at"] = utc_now()
    atomic_json(state_path, state)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--building-project", required=True, type=Path)
    parser.add_argument("--building-graph", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--room-only", action="store_true", help="Skip the already completed building retry stage")
    parser.add_argument("--resume", action="store_true", help="Resume the room graph in an existing priority run")
    parser.add_argument(
        "--certification-core", action="store_true",
        help="Prioritize certification room data and skip room-level emitter catalog tabs",
    )
    parser.add_argument(
        "--room-reference-graph", action="append", default=[], type=Path,
        help="Record a previous room graph as discovery guidance; current-version paths are still revalidated",
    )
    args = parser.parse_args()
    if struct.calcsize("P") * 8 != 32:
        parser.error("This executor requires 32-bit Python")
    profile = args.profile.resolve(strict=True)
    source = args.source.resolve(strict=True)
    building_project = args.building_project.resolve(strict=True)
    building_graph = args.building_graph.resolve(strict=True)
    output = args.output.resolve()
    room_project = output / "room" / "full_authorized_sandbox" / "prepared.wwp"
    state_path = output / "priority_mapping_state.json"
    if args.resume:
        output = output.resolve(strict=True)
        room_project = room_project.resolve(strict=True)
        state = json.loads(state_path.read_text(encoding="utf-8-sig"))
        source_hash = str(state["source_sha256"])
        state.setdefault("resume_history", []).append({
            "resumed_at": utc_now(),
            "interrupted_heartbeat": state.get("heartbeat_at"),
            "interrupted_pid": state.get("current_pid"),
        })
        state.update({"status": "running", "heartbeat_at": utc_now(), "current_pid": None})
        state.pop("finished_at", None)
        state.pop("source_unchanged", None)
    else:
        output.mkdir(parents=True, exist_ok=False)
        room_project.parent.mkdir(parents=True)
        shutil.copy2(source, room_project)
        source_hash = sha256(source)
        state = {
            "schema_version": 1, "status": "running", "started_at": utc_now(),
            "heartbeat_at": utc_now(), "current_stage": None, "current_pid": None,
            "llm_used": False, "source": str(source), "source_sha256": source_hash,
            "profile": str(profile), "priorities": PRIORITIES, "stages": {},
            "room_reference_graphs": [],
        }
        for reference_path in args.room_reference_graph:
            resolved_reference = reference_path.resolve(strict=True)
            previous = json.loads(resolved_reference.read_text(encoding="utf-8"))
            state["room_reference_graphs"].append({
                "path": str(resolved_reference),
                "sha256": sha256(resolved_reference),
                "states": len(previous.get("states") or []),
                "edges": len(previous.get("edges") or []),
                "failures": len(previous.get("failures") or []),
                "complete": bool(previous.get("complete")),
                "use": "known-path and coverage reference; revalidated on the current version profile",
            })
    atomic_json(state_path, state)
    building_command = [
        sys.executable, "-m", "winwatt_automation.scripts.explore_buildings_deep",
        "--project", str(building_project), "--output-dir", str(building_graph),
        "--version-profile", str(profile), "--resume", "--retry-failures", "--session-islands",
    ]
    for token in PRIORITIES:
        building_command.extend(("--failure-priority", token))
    room_command = [
        sys.executable, "-m", "winwatt_automation.scripts.explore_rooms_deep",
        "--project", str(room_project), "--output-dir", str(output / "room" / "graph"),
        "--room-name", "Room graph current", "--session-islands",
        "--version-profile", str(profile),
    ]
    if args.resume:
        room_command.append("--resume")
    if args.certification_core:
        room_command.extend(("--room-core-only", "--max-path-depth", "16"))
    codes: list[int] = []
    if not args.room_only:
        codes.append(run_stage(name="building_priority_retries", command=building_command, output=output,
                               state=state, state_path=state_path))
    codes.append(run_stage(name="room_current_profile_deep", command=room_command, output=output,
                           state=state, state_path=state_path))
    unchanged = sha256(source) == source_hash
    state.update({
        "status": "completed" if not any(codes) and unchanged else "completed_with_errors",
        "finished_at": utc_now(), "heartbeat_at": utc_now(), "current_stage": None,
        "source_unchanged": unchanged,
    })
    atomic_json(state_path, state)
    return 0 if state["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
