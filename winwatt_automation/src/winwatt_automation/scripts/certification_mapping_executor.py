"""LLM-free, resumable WinWatt mapping campaign for certification coverage.

The executor supervises existing focused probes and the established recursive
background mapper.  Every mapper runs in a separate 32-bit Python process,
receives only a source project that its own code copies, and writes into a
campaign directory.  The source hash is checked after every phase.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import signal
import shutil
import struct
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from winwatt_automation.version_profile import require_profile, sha256


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROFILE = PROJECT_ROOT.parent / "docs" / "winwatt_local_profile_20260929.json"
DEFAULT_CAMPAIGNS = PROJECT_ROOT / "data" / "runtime_maps" / "certification_mapping"
DESKTOP_ERROR_MARKERS = (
    "no active desktop",
    "setforegroundwindow",
    "moving mouse cursor",
    "desktop required",
)


@dataclass(frozen=True)
class Job:
    name: str
    module: str
    arguments: Callable[[Path, int, float | None], list[str]]
    bounded: bool = True


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def discover_default_project() -> Path:
    roots = PROJECT_ROOT / "data" / "runtime_maps" / "full_authorized_sandbox"
    prepared = sorted(roots.glob("**/prepared.wwp"), key=lambda item: item.stat().st_mtime, reverse=True)
    if prepared:
        return prepared[0].resolve()
    test_project = PROJECT_ROOT / "tests" / "testwwp.wwp"
    if test_project.is_file():
        return test_project.resolve()
    raise FileNotFoundError("No prepared.wwp or tests/testwwp.wwp source project is available")


def latest_resumable_campaign(root: Path) -> Path:
    candidates = []
    for state_file in root.glob("*/campaign_state.json"):
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if state.get("status") not in {"completed", "source_changed", "profile_rejected"}:
            candidates.append((state_file.stat().st_mtime, state_file.parent))
    if not candidates:
        raise FileNotFoundError(f"No resumable mapping campaign under {root}")
    return max(candidates)[1].resolve()


def active_desktop_available() -> tuple[bool, str]:
    if os.name != "nt":
        return True, "non_windows"
    user32 = ctypes.windll.user32
    desktop = user32.OpenInputDesktop(0, False, 0x0100)
    if not desktop:
        return False, "OpenInputDesktop failed; unlock the Windows session"
    try:
        if not user32.GetForegroundWindow():
            return False, "Windows has no foreground window; unlock the session"
    finally:
        user32.CloseDesktop(desktop)
    return True, "available"


def compact_event(kind: str, **values: Any) -> None:
    print(json.dumps({"time": utc_now(), "event": kind, **values}, ensure_ascii=False), flush=True)


def read_tail(path: Path, limit: int = 16000) -> str:
    if not path.is_file():
        return ""
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(max(0, size - limit))
        return stream.read().decode("utf-8", errors="replace")


def ensure_job_project(source: Path, job_root: Path) -> Path:
    """Create one durable campaign copy for a resumable deep explorer."""
    # The deep explorer independently enforces this explicit path marker before
    # allowing state-changing branches.
    target = job_root / "full_authorized_sandbox" / source.name
    manifest_path = job_root / "sandbox_manifest.json"
    if target.is_file():
        if not manifest_path.is_file():
            raise RuntimeError(f"Existing deep-mapping sandbox has no manifest: {target}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("source") != str(source) or manifest.get("source_sha256") != sha256(source):
            raise RuntimeError("Deep-mapping sandbox belongs to a different source revision")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    atomic_write_json(manifest_path, {
        "created_at": utc_now(), "source": str(source),
        "source_sha256": sha256(source), "sandbox": str(target),
    })
    return target


def stop_child(process: subprocess.Popen[Any], grace_seconds: float = 20.0) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.send_signal(signal.SIGINT)
        process.wait(timeout=grace_seconds)
        return
    except Exception:
        pass
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def build_jobs(
    *, profile: Path, source: Path, include_roundtrip: bool,
    include_background: bool, background_mode: str, background_scope: str,
    retry_background_failures: bool = False,
) -> list[Job]:
    jobs = [
        Job(
            "system_dialog_inventory",
            "winwatt_automation.scripts.probe_building_system_dialogs",
            lambda root, attempt, remaining: [
                "--profile", str(profile), "--source", str(source),
                "--output", str(root / f"attempt_{attempt:03d}"),
            ],
        ),
        Job(
            "zone_dialog_inventory",
            "winwatt_automation.scripts.probe_zone_dialogs",
            lambda root, attempt, remaining: [
                "--profile", str(profile), "--source", str(source),
                "--output", str(root / f"attempt_{attempt:03d}"),
            ],
        ),
        Job(
            "heating_generator_catalog",
            "winwatt_automation.scripts.probe_heating_generator_catalog",
            lambda root, attempt, remaining: [
                "--profile", str(profile), "--source", str(source),
                "--output", str(root / f"attempt_{attempt:03d}"),
            ],
        ),
    ]
    if include_roundtrip:
        jobs.append(Job(
            "lighting_save_reopen_roundtrip",
            "winwatt_automation.scripts.probe_lighting_system_roundtrip",
            lambda root, attempt, remaining: [
                "--profile", str(profile), "--source", str(source),
                "--output", str(root / f"attempt_{attempt:03d}"),
                "--name", f"AUTO_MAPPING_{root.parents[1].name}",
            ],
        ))
        jobs.append(Job(
            "heating_certification_workflow",
            "winwatt_automation.scripts.run_heating_certification_workflow",
            lambda root, attempt, remaining: [
                "--profile", str(profile), "--source", str(source),
                "--output", str(root / f"attempt_{attempt:03d}"),
                "--zone-name", f"AUTO_ZONE_{root.parents[1].name}",
                "--system-name", f"AUTO_HEATING_{root.parents[1].name}",
            ],
        ))
    if include_background:
        if background_scope == "certification":
            jobs.append(Job(
                "et_document_deep_mapping",
                "winwatt_automation.scripts.explore_et_document_deep",
                lambda root, attempt, remaining: [
                    "--profile", str(profile),
                    "--project", str(ensure_job_project(source, root)),
                    "--output-dir", str(root / "graph"),
                    *(["--resume"] if (root / "graph" / "graph.checkpoint.json").is_file() else []),
                    *(["--retry-failures"] if retry_background_failures else []),
                ],
                bounded=False,
            ))
            for system in (
                "heating", "water_heating", "airing", "cooling", "lighting", "gain_or_loss",
            ):
                jobs.append(Job(
                    f"building_system_{system}_deep_mapping",
                    "winwatt_automation.scripts.explore_building_system_deep",
                    lambda root, attempt, remaining, system_name=system: [
                        "--profile", str(profile),
                        "--project", str(ensure_job_project(source, root)),
                        "--output-dir", str(root / "graph"),
                        "--system", system_name,
                        *(["--resume"] if (root / "graph" / "graph.checkpoint.json").is_file() else []),
                        *(["--retry-failures"] if retry_background_failures else []),
                    ],
                    bounded=False,
                ))
        elif background_scope == "buildings":
            jobs.append(Job(
                "recursive_building_mapping",
                "winwatt_automation.scripts.explore_buildings_deep",
                lambda root, attempt, remaining: [
                    "--project", str(ensure_job_project(source, root)),
                    "--output-dir", str(root / "graph"),
                    "--version-profile", str(profile), "--session-islands",
                    *(["--resume"] if (root / "graph" / "graph.checkpoint.json").is_file() else []),
                    *(["--retry-failures"] if retry_background_failures else []),
                ],
                bounded=False,
            ))
        else:
            jobs.append(Job(
                "recursive_structure_mapping",
                "winwatt_automation.scripts.background_mapper",
                lambda root, attempt, remaining: [
                    "--project", str(source),
                    "--output-root", str(root / "run"),
                    "--store-dir", str(root.parents[1] / "global_store"),
                    "--mode", background_mode,
                    "--max-runtime-hours", str(max(remaining / 3600.0, 0.001)),
                    "--max-depth", "64", "--max-actions", "100000", "--max-states", "25000",
                    *(["--resume"] if attempt > 1 or (root / "run" / "background_audit.json").is_file() else []),
                ],
                bounded=False,
            ))
    return jobs


def load_report(job: Job, job_root: Path, attempt: int) -> dict[str, Any] | None:
    if job.name == "recursive_building_mapping" or job.name == "et_document_deep_mapping" or (
        job.name.startswith("building_system_") and job.name.endswith("_deep_mapping")
    ):
        path = job_root / "graph" / "graph.json"
    elif job.name == "heating_certification_workflow":
        path = job_root / f"attempt_{attempt:03d}" / "workflow_report.json"
    elif not job.bounded:
        path = job_root / "run" / "background_audit.json"
    else:
        path = job_root / f"attempt_{attempt:03d}" / "report.json"
    if not path.is_file():
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        if path.name == "graph.json":
            # An exhausted queue is only a completed mapping when the root
            # itself was captured. Previously a root-opening exception
            # yielded zero states and still allowed a false pass.
            report["status"] = (
                "completed"
                if report.get("complete") and bool(report.get("states"))
                else "failed"
            )
        return report
    except Exception as exc:
        return {"status": "unreadable", "error": repr(exc), "path": str(path)}


def recover_existing_passed_attempt(
    *, job: Job, job_root: Path, record: dict[str, Any]
) -> bool:
    """Adopt a completed report created outside an older campaign schema."""
    if record.get("status") == "passed" or record.get("attempts"):
        return False
    report = load_report(job, job_root, 1)
    if not report or report.get("status") != "passed":
        return False
    record["status"] = "passed"
    record["successful_attempt"] = 1
    record["attempts"] = [{
        "attempt": 1,
        "finished_at": utc_now(),
        "exit_code": 0,
        "log": None,
        "report": report,
        "desktop_error": False,
        "deadline_interrupted": False,
        "recovered_existing_report": True,
    }]
    return True


def run_job(
    *, job: Job, job_root: Path, attempt: int, deadline_monotonic: float | None,
    state: dict[str, Any], state_path: Path, heartbeat_seconds: float,
) -> tuple[int, Path, bool]:
    remaining = (
        max(0.0, deadline_monotonic - time.monotonic())
        if deadline_monotonic is not None else None
    )
    command = [sys.executable, "-m", job.module, *job.arguments(job_root, attempt, remaining)]
    log_path = job_root / f"attempt_{attempt:03d}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    source_path = str(PROJECT_ROOT / "src")
    environment["PYTHONPATH"] = source_path + (os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else "")
    environment["PYTHONIOENCODING"] = "utf-8"
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    compact_event("job_started", job=job.name, attempt=attempt, log=str(log_path))
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        process = subprocess.Popen(
            command, cwd=PROJECT_ROOT, env=environment,
            stdout=log, stderr=subprocess.STDOUT, creationflags=creationflags,
        )
        interrupted = False
        try:
            while process.poll() is None:
                now = time.monotonic()
                if deadline_monotonic is not None and now >= deadline_monotonic:
                    interrupted = True
                    compact_event("deadline_reached", job=job.name)
                    stop_child(process)
                    break
                state["heartbeat_at"] = utc_now()
                state["current_job"] = job.name
                state["current_pid"] = process.pid
                atomic_write_json(state_path, state)
                delay = heartbeat_seconds if deadline_monotonic is None else min(
                    heartbeat_seconds, max(0.2, deadline_monotonic - now)
                )
                time.sleep(delay)
        except KeyboardInterrupt:
            interrupted = True
            compact_event("interrupt_requested", job=job.name)
            stop_child(process)
            raise
        finally:
            exit_code = process.poll()
            if exit_code is None:
                stop_child(process)
                exit_code = process.returncode
    return int(exit_code if exit_code is not None else 2), log_path, interrupted


def initial_state(*, campaign: Path, profile: dict[str, Any], profile_path: Path,
                  source: Path, deadline: datetime | None, jobs: list[Job]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign_id": campaign.name,
        "kind": "llm_free_certification_mapping",
        "status": "running",
        "started_at": utc_now(),
        "updated_at": utc_now(),
        "heartbeat_at": utc_now(),
        "deadline": deadline.isoformat() if deadline is not None else None,
        "run_mode": "bounded" if deadline is not None else "until_complete",
        "python": {"executable": sys.executable, "bits": struct.calcsize("P") * 8},
        "profile_path": str(profile_path),
        "profile_id": profile["profile_id"],
        "source_project": str(source),
        "source_sha256": sha256(source),
        "llm_used": False,
        "source_write_allowed": False,
        "current_job": None,
        "current_pid": None,
        "jobs": {job.name: {"status": "pending", "attempts": []} for job in jobs},
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, help="Source WWP; defaults to newest prepared sandbox")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--campaign-dir", type=Path)
    parser.add_argument("--campaigns-root", type=Path, default=DEFAULT_CAMPAIGNS)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--resume-latest", action="store_true")
    parser.add_argument("--hours", type=float)
    parser.add_argument(
        "--until-complete", action="store_true",
        help="Run without a wall-clock deadline until all selected jobs finish or a safety failure stops the campaign.",
    )
    parser.add_argument("--desktop-retry-seconds", type=float, default=60.0)
    parser.add_argument("--heartbeat-seconds", type=float, default=10.0)
    parser.add_argument("--max-desktop-retries", type=int, default=120)
    parser.add_argument("--skip-roundtrip", action="store_true")
    parser.add_argument("--skip-background", action="store_true")
    parser.add_argument(
        "--background-only", action="store_true",
        help="Run only the selected deep graph jobs; skip already-known focused probes.",
    )
    parser.add_argument(
        "--retry-background-failures", action="store_true",
        help="After the saved pending queue, explicitly retry failed building paths.",
    )
    parser.add_argument(
        "--background-mode", choices=("safe-map", "sandbox-map", "aggressive-sandbox-map"),
        default="aggressive-sandbox-map",
    )
    parser.add_argument(
        "--background-scope", choices=("buildings", "structures", "certification"), default="buildings",
        help="Long-running graph after focused probes; buildings is the certification default",
    )
    args = parser.parse_args()

    if struct.calcsize("P") * 8 != 32:
        parser.error(f"This executor requires 32-bit Python; current interpreter is {struct.calcsize('P') * 8}-bit")
    if args.until_complete and args.hours is not None:
        parser.error("--until-complete and --hours cannot be used together")
    if args.hours is not None and args.hours <= 0:
        parser.error("--hours must be positive")
    if args.until_complete and args.background_scope == "structures":
        parser.error("--until-complete does not support the legacy structures mapper")
    effective_hours = args.hours if args.hours is not None else 6.0
    campaigns_root = args.campaigns_root.resolve()
    if args.resume_latest:
        campaign = latest_resumable_campaign(campaigns_root)
        args.resume = True
    elif args.campaign_dir:
        campaign = args.campaign_dir.resolve()
    else:
        campaign = campaigns_root / f"campaign_{datetime.now():%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"
    state_path = campaign / "campaign_state.json"

    if args.resume:
        if not state_path.is_file():
            parser.error(f"Resume state does not exist: {state_path}")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        source = Path(state["source_project"]).resolve(strict=True)
        profile_path = Path(state["profile_path"]).resolve(strict=True)
    else:
        source = (args.project.resolve(strict=True) if args.project else discover_default_project())
        profile_path = args.profile.resolve(strict=True)
    if source.suffix.casefold() != ".wwp":
        parser.error("--project must be a WWP file")
    profile = require_profile(profile_path)
    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    jobs = build_jobs(
        profile=profile_path, source=source,
        include_roundtrip=not args.skip_roundtrip,
        include_background=not args.skip_background,
        background_mode=args.background_mode,
        background_scope=args.background_scope,
        retry_background_failures=args.retry_background_failures,
    )
    if args.background_only:
        jobs = [job for job in jobs if not job.bounded]
    deadline = None if args.until_complete else datetime.now(timezone.utc) + timedelta(hours=effective_hours)
    deadline_monotonic = None if args.until_complete else time.monotonic() + effective_hours * 3600
    campaign.mkdir(parents=True, exist_ok=True)
    if not args.resume:
        state = initial_state(
            campaign=campaign, profile=profile, profile_path=profile_path,
            source=source, deadline=deadline, jobs=jobs,
        )
    else:
        state["status"] = "running"
        state["resumed_at"] = utc_now()
        state["deadline"] = deadline.isoformat() if deadline is not None else None
        state["run_mode"] = "until_complete" if args.until_complete else "bounded"
        for job in jobs:
            record = state["jobs"].setdefault(job.name, {"status": "pending", "attempts": []})
            recover_existing_passed_attempt(
                job=job, job_root=campaign / "jobs" / job.name, record=record
            )
    atomic_write_json(state_path, state)
    compact_event(
        "campaign_started", campaign=str(campaign), source=str(source),
        profile_id=profile["profile_id"], deadline=deadline.isoformat() if deadline is not None else None,
    )

    desktop_retries = 0
    exit_code = 0
    try:
        for job in jobs:
            record = state["jobs"][job.name]
            if record.get("status") == "passed":
                compact_event("job_skipped_completed", job=job.name)
                continue
            while deadline_monotonic is None or time.monotonic() < deadline_monotonic:
                available, reason = active_desktop_available()
                if not available:
                    desktop_retries += 1
                    state["status"] = "waiting_for_desktop"
                    state["desktop_wait_reason"] = reason
                    state["heartbeat_at"] = utc_now()
                    atomic_write_json(state_path, state)
                    compact_event("waiting_for_desktop", reason=reason, retry=desktop_retries)
                    if args.max_desktop_retries > 0 and desktop_retries >= args.max_desktop_retries:
                        record["status"] = "blocked_desktop"
                        exit_code = 3
                        break
                    delay = args.desktop_retry_seconds if deadline_monotonic is None else min(
                        args.desktop_retry_seconds, max(.2, deadline_monotonic - time.monotonic())
                    )
                    time.sleep(delay)
                    continue
                state["status"] = "running"
                desktop_retries = 0
                attempt = len(record["attempts"]) + 1
                job_root = campaign / "jobs" / job.name
                try:
                    code, log_path, interrupted = run_job(
                        job=job, job_root=job_root, attempt=attempt,
                        deadline_monotonic=deadline_monotonic, state=state,
                        state_path=state_path, heartbeat_seconds=max(args.heartbeat_seconds, 1.0),
                    )
                except KeyboardInterrupt:
                    record["status"] = "interrupted"
                    state["status"] = "interrupted"
                    state["updated_at"] = utc_now()
                    state["current_pid"] = None
                    atomic_write_json(state_path, state)
                    return 130
                tail = read_tail(log_path)
                report = load_report(job, job_root, attempt)
                desktop_error = any(marker in tail.casefold() for marker in DESKTOP_ERROR_MARKERS)
                attempt_record = {
                    "attempt": attempt, "finished_at": utc_now(), "exit_code": code,
                    "log": str(log_path), "report": report,
                    "desktop_error": desktop_error, "deadline_interrupted": interrupted,
                }
                record["attempts"].append(attempt_record)
                state["current_pid"] = None
                state["updated_at"] = utc_now()
                if sha256(source) != state["source_sha256"]:
                    record["status"] = "source_changed"
                    state["status"] = "source_changed"
                    state["errors"].append({"job": job.name, "error": "source project hash changed"})
                    atomic_write_json(state_path, state)
                    compact_event("source_hash_violation", job=job.name)
                    return 4
                report_passed = report is None or report.get("status") in {"passed", "completed"}
                if code == 0 and report_passed:
                    record["status"] = "passed"
                    record["successful_attempt"] = attempt
                    atomic_write_json(state_path, state)
                    compact_event("job_passed", job=job.name, attempt=attempt)
                    break
                if interrupted:
                    record["status"] = "deadline_interrupted"
                    atomic_write_json(state_path, state)
                    break
                if desktop_error:
                    record["status"] = "waiting_for_desktop_retry"
                    atomic_write_json(state_path, state)
                    compact_event("desktop_retry", job=job.name, attempt=attempt)
                    delay = args.desktop_retry_seconds if deadline_monotonic is None else min(
                        args.desktop_retry_seconds, max(.2, deadline_monotonic - time.monotonic())
                    )
                    time.sleep(delay)
                    continue
                record["status"] = "failed"
                state["errors"].append({"job": job.name, "attempt": attempt, "log": str(log_path)})
                atomic_write_json(state_path, state)
                compact_event("job_failed", job=job.name, attempt=attempt, exit_code=code)
                exit_code = max(exit_code, 2)
                break
            if record.get("status") in {"blocked_desktop", "deadline_interrupted"}:
                break
    finally:
        state["current_job"] = None
        state["current_pid"] = None
        state["finished_at"] = utc_now()
        if any(state["jobs"].get(job.name, {}).get("status") == "blocked_desktop" for job in jobs):
            state["status"] = "blocked_desktop"
        elif state.get("status") not in {"interrupted", "source_changed"}:
            passed = all(state["jobs"].get(job.name, {}).get("status") == "passed" for job in jobs)
            state["status"] = "completed" if passed else (
                "deadline_reached"
                if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic
                else "completed_with_errors"
            )
        atomic_write_json(state_path, state)
        compact_event("campaign_finished", campaign=str(campaign), status=state["status"])
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
