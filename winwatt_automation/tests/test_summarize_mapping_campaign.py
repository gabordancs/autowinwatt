import json
from pathlib import Path

from winwatt_automation.scripts.summarize_mapping_campaign import analyze_mapping_graph, summarize_campaign


def test_campaign_summary_compacts_progress_and_preserves_evidence_level(tmp_path: Path) -> None:
    source = tmp_path / "source.wwp"
    source.write_bytes(b"source")
    import hashlib
    digest = hashlib.sha256(b"source").hexdigest()
    campaign = tmp_path / "campaign"
    graph = campaign / "jobs" / "recursive_building_mapping" / "graph"
    graph.mkdir(parents=True)
    (campaign / "campaign_state.json").write_text(json.dumps({
        "campaign_id": "test", "status": "running", "heartbeat_at": "now",
        "deadline": "later", "current_job": "recursive_building_mapping", "current_pid": 123,
        "profile_id": "profile", "llm_used": False, "source_project": str(source),
        "source_sha256": digest, "errors": [],
        "jobs": {"inventory": {"status": "passed", "attempts": [{}], "successful_attempt": 1}},
    }), encoding="utf-8")
    (graph / "progress.json").write_text(json.dumps({
        "states": 3, "edges": 4, "failures": 1, "queue": 2,
        "complete": False, "updated_at": "now",
    }), encoding="utf-8")
    events = [
        {"outcome": "new_state", "path": [{"operation": "activate", "control_type": "TabItem", "name": "Zónák"}]},
        {"outcome": "failed", "path": [{"operation": "expand", "control_type": "ComboBox", "name": ""}]},
    ]
    (graph / "exploration.events.jsonl").write_text(
        "\n".join(json.dumps(item) for item in events) + "\n{partial", encoding="utf-8"
    )

    result = summarize_campaign(campaign, tmp_path / "summary")

    assert result["status"] == "passed"
    assert result["source_unchanged"] is True
    assert result["graph_progress"]["queue"] == 2
    assert result["event_totals"] == {"new_state": 1, "failed": 1}
    assert result["ignored_partial_event_lines"] == 1
    assert result["top_observed_actions"][0]["action"].endswith("Zónák")


def test_campaign_summary_fails_when_source_changed(tmp_path: Path) -> None:
    source = tmp_path / "source.wwp"
    source.write_bytes(b"changed")
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    (campaign / "campaign_state.json").write_text(json.dumps({
        "status": "running", "llm_used": False, "source_project": str(source),
        "source_sha256": "wrong", "jobs": {},
    }), encoding="utf-8")

    result = summarize_campaign(campaign, tmp_path / "summary")

    assert result["status"] == "failed"
    assert result["source_unchanged"] is False


def test_graph_analysis_reports_alternative_routes_failures_and_frontier() -> None:
    states = [{"state_id": name} for name in ("root", "left", "target")]
    edges = [
        {"from": "root", "to": "target", "status": "discovered", "action": {"control_type": "Button", "name": "A"}},
        {"from": "left", "to": "target", "status": "revisited", "action": {"control_type": "Button", "name": "B"}},
        {"from": "target", "to": "revisited_or_blocked", "status": "revisited", "action": {"control_type": "Button", "name": "C"}},
    ]
    failures = [{
        "error_type": "TimeoutError", "error": "lassú ablak", "attempt": 2,
        "path": [{"operation": "activate", "control_type": "Button", "name": "Mentés"}],
    }]
    queue = [{"path": [{"operation": "activate", "control_type": "TabItem", "name": "Gépészet"}]}]

    result = analyze_mapping_graph(states=states, edges=edges, failures=failures, queue=queue)

    assert result["multi_route_target_count"] == 1
    assert result["canonical_revisited_edges"] == 1
    assert result["unresolved_revisited_edges"] == 1
    assert result["failure_clusters"][0]["error_type"] == "TimeoutError"
    assert result["remaining_frontier"][0]["action"].endswith("Gépészet")


def test_campaign_summary_includes_each_focused_graph_job(tmp_path: Path) -> None:
    source = tmp_path / "source.wwp"
    source.write_bytes(b"source")
    import hashlib
    campaign = tmp_path / "campaign"
    graph = campaign / "jobs" / "building_system_cooling_deep_mapping" / "graph"
    graph.mkdir(parents=True)
    (campaign / "campaign_state.json").write_text(json.dumps({
        "campaign_id": "focused", "status": "completed", "llm_used": False,
        "source_project": str(source),
        "source_sha256": hashlib.sha256(b"source").hexdigest(),
        "jobs": {"building_system_cooling_deep_mapping": {
            "status": "passed", "attempts": [{}], "successful_attempt": 1,
        }},
    }), encoding="utf-8")
    (graph / "graph.json").write_text(json.dumps({
        "states": [{"state_id": "root"}],
        "edges": [{"from": "root", "to": "root", "status": "revisited",
                   "action": {"control_type": "Button", "name": "Hűtés"}}],
        "failures": [], "queue_size": 0, "complete": True,
    }), encoding="utf-8")

    result = summarize_campaign(campaign, tmp_path / "summary")

    focused = result["graph_jobs"]["building_system_cooling_deep_mapping"]
    assert focused["states"] == 1
    assert focused["edges"] == 1
    assert focused["complete"] is True
