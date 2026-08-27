"""Merge independently captured room-exploration runs by logical state hash."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any


def _graph_path(run_dir: Path) -> Path:
    complete = run_dir / "graph.json"
    return complete if complete.exists() else run_dir / "graph.checkpoint.json"


def merge_room_runs(*, base_run: Path, additional_run: Path, output_run: Path) -> dict[str, Any]:
    """Create a new evidence-preserving union of two deep-exploration runs."""
    base_run, additional_run, output_run = (Path(item).resolve() for item in (base_run, additional_run, output_run))
    if output_run.exists():
        raise FileExistsError(f"Merge output already exists: {output_run}")
    shutil.copytree(base_run, output_run)
    graph_path = output_run / _graph_path(base_run).name
    base = json.loads(graph_path.read_text(encoding="utf-8"))
    extra = json.loads(_graph_path(additional_run).read_text(encoding="utf-8"))
    states: list[dict[str, Any]] = list(base.get("states") or [])
    known = {str(state["signature_hash"]): state["state_id"] for state in states}
    state_ids: dict[str, str] = {}
    for state in extra.get("states") or []:
        old_id = str(state["state_id"])
        digest = str(state["signature_hash"])
        if digest in known:
            state_ids[old_id] = known[digest]
            continue
        new_id = f"state_{len(states):04d}_{digest[:10]}"
        state_ids[old_id] = new_id
        known[digest] = new_id
        imported = copy.deepcopy(state)
        imported["state_id"] = new_id
        parent = imported.get("parent_state")
        imported["parent_state"] = state_ids.get(str(parent)) if parent else None
        states.append(imported)
        source_dir = additional_run / "states" / old_id
        if source_dir.is_dir():
            shutil.copytree(source_dir, output_run / "states" / new_id)
    edges = list(base.get("edges") or [])
    seen_edges = {json.dumps(edge, ensure_ascii=False, sort_keys=True) for edge in edges}
    for edge in extra.get("edges") or []:
        imported = copy.deepcopy(edge)
        imported["from"] = state_ids.get(str(imported.get("from")), imported.get("from"))
        if str(imported.get("to")) in state_ids:
            imported["to"] = state_ids[str(imported["to"])]
        fingerprint = json.dumps(imported, ensure_ascii=False, sort_keys=True)
        if fingerprint not in seen_edges:
            seen_edges.add(fingerprint)
            edges.append(imported)
    failures = list(base.get("failures") or [])
    seen_failures = {json.dumps(item, ensure_ascii=False, sort_keys=True) for item in failures}
    for item in extra.get("failures") or []:
        fingerprint = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if fingerprint not in seen_failures:
            seen_failures.add(fingerprint)
            failures.append(item)
    merged = {"states": states, "edges": edges, "failures": failures, "queue_size": 0, "complete": False}
    (output_run / "graph.checkpoint.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return merged
