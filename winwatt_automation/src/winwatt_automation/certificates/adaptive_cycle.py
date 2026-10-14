"""Deterministic state machine for gap-driven WinWatt reconstruction.

The cycle never decides engineering values.  It only routes a durable
reconstruction checkpoint to a verified tool, a bounded UI-mapping task, or a
human-owned input gap.  WinWatt UI workers must acquire the workspace lease so
reconstruction and mapping cannot overlap.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any


SCHEMA = "autowinwatt-adaptive-certification-cycle/v1"
GAP_KINDS = {"ui_gap", "input_gap", "validation_failure"}
GAP_RESULTS = {"observed", "verified", "input_supplied", "rejected"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def initialize_cycle(
    workspace: Path, *, certificate_id: str, profile_id: str,
    project: Path, reconstruction_checkpoint: Path,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    state_path = workspace / "cycle_state.json"
    if state_path.exists():
        raise FileExistsError(f"adaptive cycle already exists: {state_path}")
    project = project.resolve(strict=True)
    reconstruction_checkpoint = reconstruction_checkpoint.resolve(strict=True)
    state = {
        "schema": SCHEMA,
        "certificate_id": str(certificate_id),
        "mode": "gap_driven_alternating",
        "status": "reconstructing",
        "profile_id": profile_id,
        "project": {"path": str(project), "sha256": _sha256(project)},
        "reconstruction_checkpoint": str(reconstruction_checkpoint),
        "active_gap_id": None,
        "gaps": [],
        "ui_lease": None,
        "llm_used": False,
        "created_at": _now(),
        "updated_at": _now(),
    }
    _write_json(state_path, state)
    return state


def load_cycle(workspace: Path) -> dict[str, Any]:
    state_path = workspace.resolve() / "cycle_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("schema") != SCHEMA:
        raise ValueError(f"unsupported adaptive-cycle schema: {state.get('schema')!r}")
    return state


def verify_project(state: dict[str, Any]) -> bool:
    project = Path(state["project"]["path"])
    return project.is_file() and _sha256(project) == state["project"]["sha256"]


def record_gap(workspace: Path, gap: dict[str, Any]) -> dict[str, Any]:
    state = load_cycle(workspace)
    if not verify_project(state):
        raise RuntimeError("cycle project hash changed")
    kind = gap.get("kind")
    if kind not in GAP_KINDS:
        raise ValueError(f"unsupported gap kind: {kind!r}")
    required = {"gap_id", "stage", "operation", "summary", "evidence", "expected_postconditions"}
    missing = sorted(required.difference(gap))
    if missing:
        raise ValueError(f"gap is missing required fields: {missing}")
    if any(item.get("gap_id") == gap["gap_id"] for item in state["gaps"]):
        raise ValueError(f"duplicate gap_id: {gap['gap_id']}")
    if kind != "input_gap":
        budget = gap.get("mapping_budget") or {}
        if not budget or int(budget.get("max_actions", 0)) <= 0 or int(budget.get("max_depth", 0)) <= 0:
            raise ValueError("UI and validation gaps require a positive bounded mapping_budget")
    record = {
        **gap,
        "status": "open",
        "created_at": _now(),
        "result": None,
        "result_evidence": [],
    }
    state["gaps"].append(record)
    state["active_gap_id"] = record["gap_id"]
    state["status"] = "awaiting_input" if kind == "input_gap" else "mapping_required"
    state["updated_at"] = _now()
    _write_json(workspace.resolve() / "cycle_state.json", state)
    return state


def record_gap_result(
    workspace: Path, *, gap_id: str, result: str, evidence: list[str],
) -> dict[str, Any]:
    state = load_cycle(workspace)
    if result not in GAP_RESULTS:
        raise ValueError(f"unsupported gap result: {result!r}")
    matches = [item for item in state["gaps"] if item["gap_id"] == gap_id]
    if len(matches) != 1:
        raise ValueError(f"unknown gap_id: {gap_id}")
    gap = matches[0]
    if gap["kind"] == "input_gap" and result not in {"input_supplied", "rejected"}:
        raise ValueError("input gaps cannot be resolved by UI mapping")
    if gap["kind"] != "input_gap" and result == "input_supplied":
        raise ValueError("input_supplied is valid only for input gaps")
    gap["result"] = result
    gap["result_evidence"] = list(evidence)
    gap["updated_at"] = _now()
    if result == "observed":
        gap["status"] = "observed"
        state["status"] = "verification_required"
    elif result in {"verified", "input_supplied"}:
        gap["status"] = "resolved"
        state["active_gap_id"] = None
        state["status"] = "reconstructing"
    else:
        gap["status"] = "rejected"
        state["status"] = "blocked"
    state["updated_at"] = _now()
    _write_json(workspace.resolve() / "cycle_state.json", state)
    return state


def acquire_ui_lease(workspace: Path, *, owner: str, pid: int) -> dict[str, Any]:
    state = load_cycle(workspace)
    if state.get("ui_lease"):
        raise RuntimeError(f"WinWatt UI lease is already held: {state['ui_lease']}")
    state["ui_lease"] = {"owner": owner, "pid": int(pid), "acquired_at": _now()}
    state["updated_at"] = _now()
    _write_json(workspace.resolve() / "cycle_state.json", state)
    return state


def release_ui_lease(workspace: Path, *, owner: str) -> dict[str, Any]:
    state = load_cycle(workspace)
    lease = state.get("ui_lease")
    if not lease or lease.get("owner") != owner:
        raise RuntimeError("WinWatt UI lease is not held by this owner")
    state["ui_lease"] = None
    state["updated_at"] = _now()
    _write_json(workspace.resolve() / "cycle_state.json", state)
    return state


def next_action(state: dict[str, Any]) -> dict[str, Any]:
    routes = {
        "reconstructing": "run_reconstruction_until_checkpoint_or_gap",
        "mapping_required": "run_bounded_targeted_mapping",
        "verification_required": "run_save_reopen_readback_verification",
        "awaiting_input": "request_engineering_input_without_assumption",
        "blocked": "inspect_rejected_gap",
        "complete": "no_action",
    }
    return {
        "status": state["status"],
        "action": routes[state["status"]],
        "active_gap_id": state.get("active_gap_id"),
        "project_hash_ok": verify_project(state),
        "ui_lease": state.get("ui_lease"),
        "llm_used": False,
    }
