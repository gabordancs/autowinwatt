"""Evidence audit for a completed or in-progress room state graph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def audit_room_graph(run_dir: Path) -> dict[str, Any]:
    """Validate required state evidence and summarize unfinished branches."""
    run_dir = Path(run_dir).resolve()
    source = run_dir / "graph.json"
    if not source.exists():
        source = run_dir / "graph.checkpoint.json"
    graph = json.loads(source.read_text(encoding="utf-8"))
    state_evidence: list[dict[str, Any]] = []
    for state in graph.get("states") or []:
        state_id = str(state["state_id"])
        state_dir = run_dir / "states" / state_id
        saved_state = state_dir / "state.json"
        screenshot = state_dir / "ui.png"
        state_evidence.append({
            "state_id": state_id,
            "state_json": str(saved_state),
            "screenshot": str(screenshot),
            "state_json_exists": saved_state.is_file(),
            "screenshot_exists": screenshot.is_file(),
            "ui_map_present": bool(state.get("controls")),
            "menu_snapshot_present": state.get("native_menu") is not None,
            "diff_present": state.get("diff_from_parent") is not None,
        })
    incomplete = [
        item for item in state_evidence
        if not all((item["state_json_exists"], item["screenshot_exists"], item["ui_map_present"], item["menu_snapshot_present"], item["diff_present"]))
    ]
    edges = list(graph.get("edges") or [])
    pending_edges = [edge for edge in edges if edge.get("to") == "pending"]
    revisited_or_blocked = [edge for edge in edges if edge.get("to") == "revisited_or_blocked"]
    result = {
        "source": str(source),
        "run_complete": bool(graph.get("complete")),
        "state_count": len(state_evidence),
        "edge_count": len(edges),
        "failure_count": len(graph.get("failures") or []),
        "queue_size": int(graph.get("queue_size") or 0),
        "evidence_complete": not incomplete,
        "incomplete_state_evidence": incomplete,
        "pending_edges": pending_edges,
        "revisited_or_blocked_edges": revisited_or_blocked,
        "failures": list(graph.get("failures") or []),
        "state_evidence": state_evidence,
    }
    (run_dir / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
