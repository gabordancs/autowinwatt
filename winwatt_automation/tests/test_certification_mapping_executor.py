import json
from pathlib import Path

import pytest

from winwatt_automation.scripts.certification_mapping_executor import (
    atomic_write_json,
    build_jobs,
    latest_resumable_campaign,
    load_report,
    recover_existing_passed_attempt,
    resolve_recorded_path,
    ensure_job_project,
)


def test_atomic_write_json_replaces_complete_document(tmp_path: Path):
    target = tmp_path / "state.json"
    atomic_write_json(target, {"status": "running", "number": 1})
    atomic_write_json(target, {"status": "completed", "number": 2})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "status": "completed",
        "number": 2,
    }
    assert not target.with_suffix(".json.tmp").exists()


def test_atomic_write_json_retries_transient_windows_replace_lock(monkeypatch, tmp_path: Path):
    import winwatt_automation.scripts.certification_mapping_executor as executor

    target = tmp_path / "state.json"
    real_replace = executor.os.replace
    calls = 0

    def temporarily_locked(source, destination):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise PermissionError("transient lock")
        real_replace(source, destination)

    monkeypatch.setattr(executor.os, "replace", temporarily_locked)
    monkeypatch.setattr(executor.time, "sleep", lambda _seconds: None)

    atomic_write_json(target, {"status": "running"})

    assert calls == 3
    assert json.loads(target.read_text(encoding="utf-8")) == {"status": "running"}


def test_resolve_recorded_path_rebases_old_checkout(monkeypatch, tmp_path: Path):
    import winwatt_automation.scripts.certification_mapping_executor as executor

    repo = tmp_path / "autowinwatt"
    project_root = repo / "winwatt_automation"
    source = project_root / "data" / "prepared.wwp"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"same-source")
    monkeypatch.setattr(executor, "PROJECT_ROOT", project_root)

    resolved, old = resolve_recorded_path(
        r"C:\old\checkout\autowinwatt\winwatt_automation\data\prepared.wwp",
        expected_sha256=executor.sha256(source),
    )

    assert resolved == source.resolve()
    assert old is not None


def test_existing_sandbox_accepts_same_hash_after_source_rebase(tmp_path: Path):
    old_source = tmp_path / "old" / "prepared.wwp"
    new_source = tmp_path / "new" / "prepared.wwp"
    old_source.parent.mkdir()
    new_source.parent.mkdir()
    old_source.write_bytes(b"same-source")
    new_source.write_bytes(b"same-source")
    job_root = tmp_path / "campaign" / "jobs" / "mapping"
    sandbox = job_root / "full_authorized_sandbox" / "prepared.wwp"
    sandbox.parent.mkdir(parents=True)
    sandbox.write_bytes(b"sandbox")
    (job_root / "sandbox_manifest.json").write_text(json.dumps({
        "source": str(old_source), "source_sha256": __import__("hashlib").sha256(b"same-source").hexdigest(),
        "sandbox": str(sandbox),
    }), encoding="utf-8")

    assert ensure_job_project(new_source, job_root) == sandbox
    manifest = json.loads((job_root / "sandbox_manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"] == str(new_source)
    assert manifest["source_rebased_from"] == str(old_source)


def test_latest_resumable_campaign_ignores_completed(tmp_path: Path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    complete = tmp_path / "complete"
    for root, status in ((old, "interrupted"), (new, "waiting_for_desktop"), (complete, "completed")):
        root.mkdir()
        (root / "campaign_state.json").write_text(json.dumps({"status": status}), encoding="utf-8")
    old_state = old / "campaign_state.json"
    new_state = new / "campaign_state.json"
    old_state.touch()
    import os
    os.utime(old_state, (1, 1))
    os.utime(new_state, (2, 2))

    assert latest_resumable_campaign(tmp_path) == new.resolve()


def test_latest_resumable_campaign_requires_checkpoint(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        latest_resumable_campaign(tmp_path)


def test_empty_graph_is_not_a_completed_mapping(tmp_path: Path):
    job = type("JobStub", (), {"name": "building_system_heating_deep_mapping", "bounded": True})()
    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    (graph_dir / "graph.json").write_text(
        json.dumps({"states": [], "failures": [{"error": "root failed"}], "complete": True}),
        encoding="utf-8",
    )

    report = load_report(job, tmp_path, 1)

    assert report is not None
    assert report["status"] == "failed"


def test_build_jobs_uses_isolated_attempts_and_resumable_background(tmp_path: Path):
    profile = tmp_path / "profile.json"
    source = tmp_path / "source.wwp"
    jobs = build_jobs(
        profile=profile,
        source=source,
        include_roundtrip=True,
        include_background=True,
        background_mode="aggressive-sandbox-map",
        background_scope="structures",
    )
    assert [job.name for job in jobs] == [
        "system_dialog_inventory",
        "zone_dialog_inventory",
        "heating_generator_catalog",
        "lighting_save_reopen_roundtrip",
        "heating_certification_workflow",
        "recursive_structure_mapping",
    ]
    job_root = tmp_path / "campaign" / "jobs" / "recursive_background_mapping"
    first = jobs[-1].arguments(job_root, 1, 7200)
    second = jobs[-1].arguments(job_root, 2, 3600)
    assert "--resume" not in first
    assert "--resume" in second
    assert first[first.index("--max-runtime-hours") + 1] == "2.0"
    assert second[second.index("--max-runtime-hours") + 1] == "1.0"


def test_resume_recovers_passed_job_added_after_campaign_creation(tmp_path: Path):
    profile = tmp_path / "profile.json"
    source = tmp_path / "source.wwp"
    jobs = build_jobs(
        profile=profile, source=source, include_roundtrip=True,
        include_background=False, background_mode="safe-map", background_scope="buildings",
    )
    job = next(item for item in jobs if item.name == "heating_certification_workflow")
    root = tmp_path / "jobs" / job.name
    attempt = root / "attempt_001"
    attempt.mkdir(parents=True)
    (attempt / "workflow_report.json").write_text(
        json.dumps({"status": "passed", "llm_used": False}), encoding="utf-8"
    )
    record = {"status": "pending", "attempts": []}

    assert recover_existing_passed_attempt(job=job, job_root=root, record=record)
    assert record["status"] == "passed"
    assert record["attempts"][0]["recovered_existing_report"] is True


def test_building_background_uses_durable_campaign_copy(tmp_path: Path):
    profile = tmp_path / "profile.json"
    source = tmp_path / "source.wwp"
    source.write_bytes(b"source")
    jobs = build_jobs(
        profile=profile,
        source=source,
        include_roundtrip=False,
        include_background=True,
        background_mode="safe-map",
        background_scope="buildings",
    )
    background = jobs[-1]
    root = tmp_path / "campaign" / "jobs" / background.name
    first = background.arguments(root, 1, 600)
    sandbox = root / "full_authorized_sandbox" / source.name
    assert background.name == "recursive_building_mapping"
    assert sandbox.read_bytes() == b"source"
    assert str(sandbox) in first
    assert "--resume" not in first
    graph = root / "graph"
    graph.mkdir()
    (graph / "graph.checkpoint.json").write_text("{}", encoding="utf-8")
    second = background.arguments(root, 2, 300)
    assert "--resume" in second
    assert "--retry-failures" not in second


def test_building_failure_retry_is_explicit(tmp_path: Path):
    profile = tmp_path / "profile.json"
    source = tmp_path / "source.wwp"
    source.write_bytes(b"source")
    jobs = build_jobs(
        profile=profile,
        source=source,
        include_roundtrip=False,
        include_background=True,
        background_mode="safe-map",
        background_scope="buildings",
        retry_background_failures=True,
    )

    root = tmp_path / "campaign" / "jobs" / "recursive_building_mapping"
    graph = root / "graph"
    graph.mkdir(parents=True)
    (graph / "graph.checkpoint.json").write_text("{}", encoding="utf-8")
    arguments = jobs[-1].arguments(root, 2, 300)

    assert "--resume" in arguments
    assert "--retry-failures" in arguments


def test_building_job_accepts_unbounded_remaining_time(tmp_path: Path):
    profile = tmp_path / "profile.json"
    source = tmp_path / "source.wwp"
    source.write_bytes(b"source")
    jobs = build_jobs(
        profile=profile, source=source, include_roundtrip=False,
        include_background=True, background_mode="safe-map", background_scope="buildings",
    )

    arguments = jobs[-1].arguments(
        tmp_path / "campaign" / "jobs" / "recursive_building_mapping", 1, None
    )

    assert "--max-runtime-hours" not in arguments
    assert "--resume" not in arguments
