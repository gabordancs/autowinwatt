from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from winwatt_automation.runtime_logging.progress_display import write_progress_status


DEFAULT_LOGS_ROOT = Path("data/run_logs")
RETENTION_TODO = "TODO: implement retention policy (max files/age) in future iteration."


@dataclass(slots=True)
class RunContext:
    run_id: str
    sequence_number: int
    command: str
    cwd: str
    safe_mode: str | None
    project_path: str | None
    started_at: str
    logs_root: Path
    runs_dir: Path
    log_path: Path
    json_path: Path
    status_path: Path
    log_handle: Any
    tags: list[str] = field(default_factory=list)
    important_events: list[dict[str, Any]] = field(default_factory=list)


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso_timestamp(moment: datetime) -> str:
    return moment.isoformat()


def _filename_timestamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d_%H-%M-%S")


def _safe_slug(command: str) -> str:
    first = (command or "run").strip().split()
    candidate = first[2] if len(first) >= 3 and first[1] == "-m" else first[-1] if first else "run"
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", candidate).strip("_").lower()
    return slug or "run"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_structure(logs_root: Path) -> dict[str, Path]:
    runs = logs_root / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    index = logs_root / "index.json"
    latest_txt = logs_root / "latest.txt"
    latest_json = logs_root / "latest.json"
    if not index.exists():
        _write_json(index, {"retention": RETENTION_TODO, "runs": []})
    if not latest_txt.exists():
        latest_txt.write_text("No runs recorded yet.\n", encoding="utf-8")
    if not latest_json.exists():
        _write_json(latest_json, {"retention": RETENTION_TODO, "latest_run": None})
    return {"runs": runs, "index": index, "latest_txt": latest_txt, "latest_json": latest_json}


def _next_sequence(index_path: Path) -> int:
    index = _load_json(index_path, {"runs": []})
    rows = index.get("runs", []) if isinstance(index, dict) else []
    if not rows:
        return 1
    numbers = [int(item.get("sequence_number") or 0) for item in rows if isinstance(item, dict)]
    return max(numbers, default=0) + 1


def start_run(command: str, context: dict[str, Any]) -> RunContext:
    root = _project_root()
    logs_root = root / DEFAULT_LOGS_ROOT
    paths = _ensure_structure(logs_root)

    now = _utc_now()
    sequence = _next_sequence(paths["index"])
    slug = _safe_slug(command)
    run_id = f"{sequence:04d}_{slug}_{_filename_timestamp(now)}"
    log_path = paths["runs"] / f"{run_id}.log"
    json_path = paths["runs"] / f"{run_id}.json"
    status_path = logs_root / "live_status.json"

    handle = log_path.open("w", encoding="utf-8")
    handle.write(f"run_id={run_id}\n")
    handle.write(f"started_at={_iso_timestamp(now)}\n")
    handle.write(f"command={command}\n\n")
    handle.flush()

    return RunContext(
        run_id=run_id,
        sequence_number=sequence,
        command=command,
        cwd=str(context.get("cwd") or root),
        safe_mode=context.get("safe_mode"),
        project_path=context.get("project_path"),
        started_at=_iso_timestamp(now),
        logs_root=logs_root,
        runs_dir=paths["runs"],
        log_path=log_path,
        json_path=json_path,
        status_path=status_path,
        log_handle=handle,
        tags=list(context.get("tags") or []),
    )


def append_terminal_line(run_ctx: RunContext, line: str) -> None:
    if getattr(run_ctx.log_handle, "closed", False):
        return
    run_ctx.log_handle.write(f"{line.rstrip()}\n")
    run_ctx.log_handle.flush()


def record_event(run_ctx: RunContext, event_type: str, payload: dict[str, Any]) -> None:
    event = {
        "timestamp": _iso_timestamp(_utc_now()),
        "event_type": event_type,
        "payload": payload,
    }
    run_ctx.important_events.append(event)
    append_terminal_line(run_ctx, f"[event] {event_type}: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}")


def update_status(run_ctx: RunContext, state: str, message: str, details: dict[str, Any] | None = None) -> Path:
    return write_progress_status(
        run_ctx.status_path,
        run_id=run_ctx.run_id,
        state=state,
        message=message,
        command=run_ctx.command,
        details=details,
    )


def finalize_run(run_ctx: RunContext, success: bool, exit_code: int, summary: dict[str, Any]) -> Path:
    finished_dt = _utc_now()
    finished_at = _iso_timestamp(finished_dt)
    started_dt = datetime.fromisoformat(run_ctx.started_at)
    duration_seconds = round((finished_dt - started_dt).total_seconds(), 3)
    summary_payload = {
        "no_project_top_menus": summary.get("no_project_top_menus"),
        "project_open_top_menus": summary.get("project_open_top_menus"),
        "diff_summary": summary.get("diff_summary", {}),
        "startup_project_detected": summary.get("startup_project_detected"),
        "already_open_before_mapping": summary.get("already_open_before_mapping"),
        "project_open_verdict": summary.get("project_open_verdict"),
        "expected_project_path": summary.get("expected_project_path"),
        "observed_project_path": summary.get("observed_project_path"),
        "path_match_normalized": summary.get("path_match_normalized"),
        "skipped_by_safety": summary.get("skipped_by_safety"),
        "last_error": summary.get("last_error"),
        "modal_detected": summary.get("modal_detected", False),
        "recovery_attempted": summary.get("recovery_attempted", False),
        "recovery_success": summary.get("recovery_success", False),
    }

    payload = {
        "run_id": run_ctx.run_id,
        "sequence_number": run_ctx.sequence_number,
        "started_at": run_ctx.started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "command": run_ctx.command,
        "cwd": run_ctx.cwd,
        "safe_mode": run_ctx.safe_mode,
        "project_path": run_ctx.project_path,
        "exit_code": exit_code,
        "success": success,
        "summary": summary_payload,
        "important_events": run_ctx.important_events,
        "output_paths": {
            "log_path": str(run_ctx.log_path.relative_to(_project_root())),
            "json_path": str(run_ctx.json_path.relative_to(_project_root())),
        },
        "tags": run_ctx.tags,
    }
    _write_json(run_ctx.json_path, payload)

    latest_json_path = run_ctx.logs_root / "latest.json"
    latest_txt_path = run_ctx.logs_root / "latest.txt"
    _write_json(latest_json_path, payload)
    latest_txt_path.write_text(
        "\n".join(
            [
                f"run_id={run_ctx.run_id}",
                f"sequence_number={run_ctx.sequence_number}",
                f"success={success}",
                f"log={payload['output_paths']['log_path']}",
                f"meta={payload['output_paths']['json_path']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    index_path = run_ctx.logs_root / "index.json"
    index = _load_json(index_path, {"retention": RETENTION_TODO, "runs": []})
    index.setdefault("retention", RETENTION_TODO)
    index.setdefault("runs", [])
    index["runs"].append(
        {
            "sequence_number": run_ctx.sequence_number,
            "run_id": run_ctx.run_id,
            "started_at": run_ctx.started_at,
            "command": run_ctx.command,
            "success": success,
            "short_summary": summary.get("short_summary") or summary_payload,
            "log_path": payload["output_paths"]["log_path"],
            "json_path": payload["output_paths"]["json_path"],
        }
    )
    _write_json(index_path, index)

    update_status(
        run_ctx,
        "finished" if success else "failed",
        "Mapping finished successfully." if success else "Mapping failed.",
        {
            "exit_code": exit_code,
            "summary": summary_payload,
        },
    )

    run_ctx.log_handle.write(f"\nfinished_at={finished_at} success={success} exit_code={exit_code}\n")
    run_ctx.log_handle.flush()
    run_ctx.log_handle.close()
    return run_ctx.json_path
