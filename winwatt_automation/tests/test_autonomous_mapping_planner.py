import json
from pathlib import Path

from winwatt_automation.scripts.plan_autonomous_mapping import (
    CERTIFICATION_JOBS,
    build_plan,
)


PROFILE = "winwatt_8c137b67c0a2214bb91aeae8"


def _campaign(
    root: Path, name: str, *, status: str, jobs: dict[str, tuple[int, int, int, bool]],
    current_job: str | None = None, current_pid: int | None = None,
) -> Path:
    campaign = root / name
    source = campaign / "source.wwp"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"fixture")
    import hashlib
    records = {}
    for job, (states, edges, failures, complete) in jobs.items():
        graph = campaign / "jobs" / job / "graph"
        graph.mkdir(parents=True)
        (graph / "progress.json").write_text(json.dumps({
            "states": states, "edges": edges, "failures": failures,
            "queue": 0 if complete else 3, "complete": complete,
            "updated_at": "2026-10-01T00:00:00+00:00",
        }), encoding="utf-8")
        records[job] = {"status": "passed" if complete else "pending", "attempts": []}
    (campaign / "campaign_state.json").write_text(json.dumps({
        "campaign_id": name, "profile_id": PROFILE, "status": status,
        "heartbeat_at": "2026-10-01T00:00:00+00:00", "updated_at": "2026-10-01T00:00:00+00:00",
        "current_job": current_job, "current_pid": current_pid, "llm_used": False,
        "source_project": str(source),
        "source_sha256": hashlib.sha256(b"fixture").hexdigest(), "jobs": records,
    }), encoding="utf-8")
    return campaign


def test_reuses_complete_graphs_and_retries_only_recorded_gaps(tmp_path: Path) -> None:
    jobs = {job: (10, 20, 0, True) for job in CERTIFICATION_JOBS}
    jobs["building_system_heating_deep_mapping"] = (21, 191, 86, True)
    jobs["building_system_water_heating_deep_mapping"] = (37, 276, 80, True)
    campaign = _campaign(tmp_path, "complete", status="completed", jobs=jobs)

    plan = build_plan(campaigns_root=tmp_path, profile_id=PROFILE)

    assert plan["coverage"]["building_system_heating_deep_mapping"]["coverage"] == "complete"
    assert plan["coverage"]["building_system_water_heating_deep_mapping"]["reuse"]["states"] == 37
    assert plan["recommendation"]["action"] == "retry_observed_failures"
    assert plan["recommendation"]["campaign"] == str(campaign)
    assert plan["recommendation"]["jobs"] == [
        "building_system_heating_deep_mapping",
        "building_system_water_heating_deep_mapping",
    ]
    assert plan["recommendation"]["force_selected_jobs"] is True


def test_missing_work_is_ranked_in_certification_order(tmp_path: Path) -> None:
    _campaign(tmp_path, "partial", status="interrupted", jobs={
        "et_document_deep_mapping": (16, 143, 0, True),
    })

    plan = build_plan(campaigns_root=tmp_path, profile_id=PROFILE)

    assert plan["recommendation"]["action"] == "resume_missing"
    assert plan["recommendation"]["jobs"] == list(CERTIFICATION_JOBS[1:])


def test_active_mapper_is_never_scheduled_beside(tmp_path: Path) -> None:
    _campaign(
        tmp_path, "active", status="running", jobs={
            "et_document_deep_mapping": (3, 65, 3, False),
        }, current_job="et_document_deep_mapping", current_pid=1234,
    )

    plan = build_plan(campaigns_root=tmp_path, profile_id=PROFILE, pid_exists=lambda _: True)

    assert plan["recommendation"]["action"] == "observe_active"
    assert plan["recommendation"]["jobs"] == ["et_document_deep_mapping"]


def test_stale_running_pid_is_not_treated_as_active(tmp_path: Path) -> None:
    _campaign(
        tmp_path, "stale", status="running", jobs={
            "et_document_deep_mapping": (3, 65, 3, False),
        }, current_job="et_document_deep_mapping", current_pid=1234,
    )

    plan = build_plan(campaigns_root=tmp_path, profile_id=PROFILE, pid_exists=lambda _: False)

    assert plan["recommendation"]["action"] == "resume_missing"


def test_partial_campaign_is_resumable_for_missing_jobs(tmp_path: Path) -> None:
    campaign = _campaign(tmp_path, "partial", status="partial", jobs={
        "et_document_deep_mapping": (16, 143, 0, True),
    })

    plan = build_plan(campaigns_root=tmp_path, profile_id=PROFILE)

    assert plan["recommendation"]["action"] == "resume_missing"
    assert plan["recommendation"]["campaign"] == str(campaign)
