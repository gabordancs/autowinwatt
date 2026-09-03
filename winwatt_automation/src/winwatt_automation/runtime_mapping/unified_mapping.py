"""Manifest and progress helpers for the cumulative WinWatt exploration."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
UNIFIED_ROOT = PROJECT_ROOT / "data" / "runtime_maps" / "unified_exploration"
KNOWN_SOURCES = (
    "data/runtime_maps/room_deep_runs/20260826T154506_merged",
    "data/runtime_maps/external_wall_targeted_20260827",
    "data/runtime_maps/room_core_tabs_20260827",
    "data/runtime_maps/mdi_runtime_states_9_60",
    "data/runtime_maps/catalog_contexts_9_60",
)


def _source_summary(relative: str) -> dict[str, Any]:
    path = PROJECT_ROOT / relative
    result: dict[str, Any] = {"path": relative.replace("\\", "/"), "exists": path.exists()}
    graph = path / "graph.checkpoint.json"
    if graph.exists():
        try:
            content = json.loads(graph.read_text(encoding="utf-8"))
            result["states"] = len(content.get("states") or [])
            result["edges"] = len(content.get("edges") or [])
        except json.JSONDecodeError:
            result["read_error"] = "invalid_json"
    return result


def write_manifest(*, selected_scopes: list[str], active_run: Path | None = None) -> Path:
    """Record sources instead of copying or overwriting historic evidence."""
    UNIFIED_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "selected_scopes": selected_scopes,
        "active_run": str(active_run.relative_to(PROJECT_ROOT)).replace("\\", "/") if active_run else None,
        "sources": [_source_summary(item) for item in KNOWN_SOURCES],
        "merge_policy": "references_only; previous state screenshots and graphs are immutable evidence",
    }
    target = UNIFIED_ROOT / "manifest.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def write_progress(*, selected_scopes: list[str], completed: int, run_root: Path) -> None:
    """Use the common status-card schema so all mapping modes look alike."""
    payload = {
        "states": 0,
        "edges": 0,
        "failures": 0,
        "queue": max(0, len(selected_scopes) - completed),
        "complete": completed >= len(selected_scopes),
        "scope_total": len(selected_scopes),
        "scope_completed": completed,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (run_root / "progress.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
