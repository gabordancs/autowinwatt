"""Create a compact, deterministic summary of a WinWatt mapping campaign."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json_lines(path: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    ignored = 0
    if not path.is_file():
        return rows, ignored
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                ignored += 1
    return rows, ignored


def _action_label(path: Iterable[dict[str, Any]]) -> str:
    actions = list(path)
    if not actions:
        return "<no action>"
    item = actions[-1]
    return " | ".join((
        str(item.get("operation") or ""), str(item.get("control_type") or ""),
        str(item.get("name") or "<unnamed>"),
    ))


def analyze_mapping_graph(
    *, states: list[dict[str, Any]], edges: list[dict[str, Any]],
    failures: list[dict[str, Any]], queue: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build deterministic coverage, convergence, failure and frontier metrics."""
    state_ids = {str(item.get("state_id")) for item in states if item.get("state_id")}
    statuses = Counter(str(item.get("status") or "unknown") for item in edges)
    resolved_edges = [item for item in edges if str(item.get("to")) in state_ids]
    unresolved_edges = [item for item in edges if str(item.get("to")) not in state_ids]
    incoming: dict[str, list[dict[str, Any]]] = {}
    for edge in resolved_edges:
        incoming.setdefault(str(edge["to"]), []).append(edge)
    alternative_targets = [
        {
            "state_id": target,
            "route_count": len(routes),
            "routes": [
                {"from": item.get("from"), "action": _action_label([item.get("action") or {}]), "status": item.get("status")}
                for item in routes
            ],
        }
        for target, routes in sorted(incoming.items()) if len(routes) > 1
    ]
    failure_groups: dict[tuple[str, str], dict[str, Any]] = {}
    for item in failures:
        key = (str(item.get("error_type") or "UnknownError"), _action_label(item.get("path") or []))
        group = failure_groups.setdefault(key, {
            "error_type": key[0], "action": key[1], "count": 0,
            "max_attempt": 0, "sample_error": item.get("error") or item.get("error_repr"),
        })
        group["count"] += 1
        group["max_attempt"] = max(group["max_attempt"], int(item.get("attempt") or 0))
    failure_clusters = sorted(
        failure_groups.values(), key=lambda item: (-item["count"], item["error_type"], item["action"])
    )
    frontier = Counter(_action_label(item.get("path") or []) for item in queue)
    finished = sum(count for status, count in statuses.items() if status not in {"pending", "running"})
    return {
        "states": len(states),
        "edges": len(edges),
        "edge_statuses": dict(sorted(statuses.items())),
        "processed_edge_ratio": round(finished / len(edges), 6) if edges else 1.0,
        "resolved_target_edges": len(resolved_edges),
        "unresolved_target_edges": len(unresolved_edges),
        "canonical_revisited_edges": sum(
            1 for item in resolved_edges if item.get("status") == "revisited"
        ),
        "unresolved_revisited_edges": sum(
            1 for item in unresolved_edges if item.get("status") == "revisited"
        ),
        "multi_route_target_count": len(alternative_targets),
        "alternative_routes": alternative_targets[:50],
        "failure_clusters": failure_clusters[:50],
        "remaining_frontier": [
            {"action": label, "paths": count} for label, count in frontier.most_common(50)
        ],
    }


def summarize_graph_jobs(campaign: Path) -> dict[str, dict[str, Any]]:
    """Summarize every deep graph job, including focused ET/system campaigns."""
    summaries: dict[str, dict[str, Any]] = {}
    jobs_root = campaign / "jobs"
    if not jobs_root.is_dir():
        return summaries
    for job_root in sorted(path for path in jobs_root.iterdir() if path.is_dir()):
        graph_root = job_root / "graph"
        if not graph_root.is_dir():
            continue
        graph_path = graph_root / "graph.json"
        checkpoint_path = graph_root / "graph.checkpoint.json"
        progress_path = graph_root / "progress.json"
        queue_path = graph_root / "queue.checkpoint.json"
        payload: dict[str, Any] = {}
        source = None
        for candidate in (graph_path, checkpoint_path):
            if candidate.is_file():
                payload = json.loads(candidate.read_text(encoding="utf-8"))
                source = candidate.name
                break
        progress = (
            json.loads(progress_path.read_text(encoding="utf-8"))
            if progress_path.is_file() else {}
        )
        queue = (
            json.loads(queue_path.read_text(encoding="utf-8"))
            if queue_path.is_file() else []
        )
        states = list(payload.get("states") or [])
        edges = list(payload.get("edges") or [])
        failures = list(payload.get("failures") or [])
        summaries[job_root.name] = {
            "source": source,
            "states": len(states) if payload else progress.get("states"),
            "edges": len(edges) if payload else progress.get("edges"),
            "failures": len(failures) if payload else progress.get("failures"),
            "queue": len(queue) if queue_path.is_file() else payload.get(
                "queue_size", progress.get("queue")
            ),
            "complete": payload.get("complete", progress.get("complete")),
            "analysis": analyze_mapping_graph(
                states=states, edges=edges, failures=failures, queue=queue,
            ) if payload else None,
        }
    return summaries


def summarize_campaign(campaign: Path, output: Path) -> dict[str, Any]:
    campaign = campaign.resolve(strict=True)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    state_path = campaign / "campaign_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    source = Path(state["source_project"])
    current_hash = sha256(source)
    source_unchanged = current_hash == state.get("source_sha256")
    graph_root = campaign / "jobs" / "recursive_building_mapping" / "graph"
    progress_path = graph_root / "progress.json"
    progress = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.is_file() else {}
    events, ignored_lines = read_json_lines(graph_root / "exploration.events.jsonl")
    checkpoint_path = graph_root / "graph.checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.is_file() else {}
    queue_path = graph_root / "queue.checkpoint.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8")) if queue_path.is_file() else []
    states = list(checkpoint.get("states") or [])
    edges = list(checkpoint.get("edges") or [])
    checkpoint_failures = list(checkpoint.get("failures") or [])
    if edges:
        action_source = "graph.checkpoint.json"
        outcomes = Counter(str(item.get("status") or "unknown") for item in edges)
        failures = Counter(_action_label(item.get("path") or []) for item in checkpoint_failures)
        observations = Counter(
            _action_label([item.get("action") or {}])
            for item in edges if item.get("status") not in {"failed", "pending"}
        )
    else:
        action_source = "exploration.events.jsonl"
        outcomes = Counter(str(item.get("outcome") or "unknown") for item in events)
        failures = Counter(
            _action_label(item.get("path") or []) for item in events if item.get("outcome") == "failed"
        )
        observations = Counter(
            _action_label(item.get("path") or []) for item in events if item.get("outcome") != "failed"
        )
    jobs = {
        name: {
            "status": record.get("status"),
            "attempts": len(record.get("attempts") or []),
            "successful_attempt": record.get("successful_attempt"),
        }
        for name, record in state.get("jobs", {}).items()
    }
    summary = {
        "schema_version": 1,
        "tool": "winwatt.mapping.campaign.summarize",
        "tool_version": "1.2.0",
        "status": "passed" if source_unchanged and state.get("llm_used") is False else "failed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "campaign": str(campaign),
        "campaign_id": state.get("campaign_id"),
        "campaign_status": state.get("status"),
        "heartbeat_at": state.get("heartbeat_at"),
        "deadline": state.get("deadline"),
        "current_job": state.get("current_job"),
        "current_pid": state.get("current_pid"),
        "profile_id": state.get("profile_id"),
        "llm_used": state.get("llm_used"),
        "source": str(source),
        "expected_source_sha256": state.get("source_sha256"),
        "current_source_sha256": current_hash,
        "source_unchanged": source_unchanged,
        "jobs": jobs,
        "job_totals": dict(Counter(item["status"] for item in jobs.values())),
        "graph_progress": {
            "states": progress.get("states"), "edges": progress.get("edges"),
            "failures": progress.get("failures"), "queue": progress.get("queue"),
            "complete": progress.get("complete"), "updated_at": progress.get("updated_at"),
        },
        "event_totals": dict(outcomes),
        "recent_event_totals": dict(Counter(str(item.get("outcome") or "unknown") for item in events)),
        "event_lines": len(events),
        "ignored_partial_event_lines": ignored_lines,
        "action_summary_source": action_source,
        "graph_analysis": analyze_mapping_graph(
            states=states, edges=edges, failures=checkpoint_failures, queue=queue,
        ),
        "graph_jobs": summarize_graph_jobs(campaign),
        "top_observed_actions": [
            {"action": label, "count": count} for label, count in observations.most_common(20)
        ],
        "top_failed_actions": [
            {"action": label, "count": count} for label, count in failures.most_common(20)
        ],
        "resumable": state.get("status") not in {"completed", "source_changed", "profile_rejected"},
        "errors": state.get("errors") or [],
    }
    (output / "campaign_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        summary = summarize_campaign(args.campaign, args.output)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
