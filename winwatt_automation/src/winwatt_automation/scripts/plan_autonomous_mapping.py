"""Plan the next AI-free WinWatt mapping run from all recorded campaigns."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CAMPAIGNS = PROJECT_ROOT / "data" / "runtime_maps" / "certification_mapping"
DEFAULT_PROFILE_ID = "winwatt_8c137b67c0a2214bb91aeae8"
CERTIFICATION_JOBS = (
    "et_document_deep_mapping",
    "building_system_heating_deep_mapping",
    "building_system_water_heating_deep_mapping",
    "building_system_airing_deep_mapping",
    "building_system_cooling_deep_mapping",
    "building_system_lighting_deep_mapping",
    "building_system_gain_or_loss_deep_mapping",
)
ACTIVE_STATUSES = {"running", "waiting_for_desktop"}
RESUMABLE_STATUSES = {
    "interrupted", "deadline_reached", "completed_with_errors",
    "waiting_for_desktop", "running", "partial",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object expected: {path}")
    return value


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information, False, pid
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def _graph_progress(campaign: Path, job: str) -> dict[str, Any]:
    path = campaign / "jobs" / job / "graph" / "progress.json"
    if not path.is_file():
        return {"states": 0, "edges": 0, "failures": 0, "queue": None, "complete": False}
    payload = _read_json(path)
    return {
        "states": int(payload.get("states") or 0),
        "edges": int(payload.get("edges") or 0),
        "failures": int(payload.get("failures") or 0),
        "queue": payload.get("queue"),
        "complete": payload.get("complete") is True,
        "updated_at": payload.get("updated_at"),
    }


def _campaign_rows(root: Path, profile_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not root.is_dir():
        return rows, [f"campaign root does not exist: {root}"]
    for campaign in sorted(path for path in root.iterdir() if path.is_dir()):
        state_path = campaign / "campaign_state.json"
        if not state_path.is_file():
            continue
        try:
            state = _read_json(state_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            warnings.append(f"ignored unreadable campaign {campaign.name}: {exc}")
            continue
        if state.get("profile_id") != profile_id:
            continue
        source = Path(str(state.get("source_project") or ""))
        source_exists = source.is_file()
        source_matches = False
        if source_exists and state.get("source_sha256"):
            try:
                source_matches = _sha256(source) == state["source_sha256"]
            except OSError as exc:
                warnings.append(f"cannot hash source for {campaign.name}: {exc}")
        jobs: dict[str, Any] = {}
        records = state.get("jobs") if isinstance(state.get("jobs"), dict) else {}
        for job in CERTIFICATION_JOBS:
            record = records.get(job) if isinstance(records.get(job), dict) else {}
            progress = _graph_progress(campaign, job)
            jobs[job] = {
                "status": record.get("status"),
                "attempts": len(record.get("attempts") or []),
                "progress": progress,
            }
        rows.append({
            "campaign": str(campaign),
            "campaign_id": state.get("campaign_id") or campaign.name,
            "status": state.get("status"),
            "heartbeat_at": state.get("heartbeat_at"),
            "updated_at": state.get("updated_at"),
            "current_job": state.get("current_job"),
            "current_pid": state.get("current_pid"),
            "llm_used": state.get("llm_used"),
            "source": str(source),
            "source_exists": source_exists,
            "source_hash_matches": source_matches,
            "jobs": jobs,
        })
    return rows, warnings


def build_plan(
    *, campaigns_root: Path, profile_id: str,
    pid_exists: Callable[[int], bool] = _pid_exists,
) -> dict[str, Any]:
    campaigns_root = campaigns_root.resolve()
    campaigns, warnings = _campaign_rows(campaigns_root, profile_id)
    coverage: dict[str, Any] = {}
    for priority, job in enumerate(CERTIFICATION_JOBS, start=1):
        candidates = []
        for campaign in campaigns:
            item = campaign["jobs"][job]
            progress = item["progress"]
            if progress["states"] or item["status"]:
                candidates.append({
                    "campaign": campaign["campaign"],
                    "campaign_id": campaign["campaign_id"],
                    "campaign_status": campaign["status"],
                    "job_status": item["status"],
                    **progress,
                })
        completed = [
            item for item in candidates
            if item["complete"] and item["queue"] == 0 and item["states"] > 0
        ]
        completed.sort(
            key=lambda item: (item["states"], item["edges"], str(item.get("updated_at") or "")),
            reverse=True,
        )
        best = completed[0] if completed else None
        coverage[job] = {
            "priority": priority,
            "coverage": "complete" if best else "missing",
            "reuse": best,
            "failure_count": int(best["failures"]) if best else 0,
            "candidate_count": len(candidates),
        }

    active = [
        campaign for campaign in campaigns
        if campaign["status"] in ACTIVE_STATUSES
        and campaign.get("current_pid")
        and pid_exists(int(campaign["current_pid"]))
    ]
    active.sort(key=lambda item: str(item.get("heartbeat_at") or ""), reverse=True)
    missing = [job for job in CERTIFICATION_JOBS if coverage[job]["coverage"] == "missing"]
    retry_jobs = [
        job for job in CERTIFICATION_JOBS
        if coverage[job]["coverage"] == "complete" and coverage[job]["failure_count"] > 0
    ]
    if active:
        current = active[0]
        recommendation = {
            "action": "observe_active",
            "campaign": current["campaign"],
            "jobs": [current["current_job"]] if current.get("current_job") else [],
            "reason": "A mapping worker is already active; never start a second WinWatt UI worker.",
        }
    elif missing:
        resumable = [campaign for campaign in campaigns if campaign["status"] in RESUMABLE_STATUSES]
        resumable.sort(key=lambda item: str(item.get("heartbeat_at") or item.get("updated_at") or ""), reverse=True)
        recommendation = {
            "action": "resume_missing" if resumable else "start_missing",
            "campaign": resumable[0]["campaign"] if resumable else None,
            "jobs": missing,
            "retry_failures": False,
            "force_selected_jobs": False,
            "reason": "Run only certification graph jobs without reusable complete evidence.",
        }
    elif retry_jobs:
        campaign_counts: dict[str, int] = {}
        for job in retry_jobs:
            campaign = coverage[job]["reuse"]["campaign"]
            campaign_counts[campaign] = campaign_counts.get(campaign, 0) + 1
        selected_campaign = sorted(campaign_counts, key=lambda item: (-campaign_counts[item], item))[0]
        selected_jobs = [job for job in retry_jobs if coverage[job]["reuse"]["campaign"] == selected_campaign]
        recommendation = {
            "action": "retry_observed_failures",
            "campaign": selected_campaign,
            "jobs": selected_jobs,
            "retry_failures": True,
            "force_selected_jobs": True,
            "reason": "Coverage is complete; spend new runtime only on recorded failed paths.",
        }
    else:
        recommendation = {
            "action": "complete",
            "campaign": None,
            "jobs": [],
            "reason": "All certification mapping jobs have complete, zero-failure graph evidence.",
        }

    bad_sources = [
        item["campaign_id"] for item in campaigns
        if item["source_exists"] and not item["source_hash_matches"]
    ]
    if bad_sources:
        warnings.append("source hash mismatch: " + ", ".join(bad_sources))
    return {
        "schema_version": 1,
        "tool": "winwatt.mapping.autonomous.plan",
        "tool_version": "1.0.0",
        "status": "review_required" if bad_sources else "passed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "profile_id": profile_id,
        "campaigns_root": str(campaigns_root),
        "llm_used": False,
        "campaign_count": len(campaigns),
        "coverage": coverage,
        "recommendation": recommendation,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaigns-root", type=Path, default=DEFAULT_CAMPAIGNS)
    parser.add_argument("--profile-id", default=DEFAULT_PROFILE_ID)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error(f"output must be a new path: {output}")
    try:
        report = build_plan(campaigns_root=args.campaigns_root, profile_id=args.profile_id)
        output.mkdir(parents=True)
        (output / "autonomous_mapping_plan.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"passed", "review_required"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
