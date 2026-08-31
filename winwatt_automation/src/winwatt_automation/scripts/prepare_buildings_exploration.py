"""Prepare small, transferable work packages for the Buildings catalog.

The manifest is deliberately independent from a worker machine.  A worker
leases one package, writes evidence below its package directory, and releases
it as completed or failed.  Expired leases can be claimed by another worker,
so a later Munka-PC reconnect does not require restarting the whole mapping.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from winwatt_automation.runtime_mapping.program_mapper import prepare_fresh_winwatt_session
from winwatt_automation.scripts.map_catalog_contexts import main as map_catalog_contexts_main


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BUILDINGS_INDEX = 4
TASKS = (
    ("baseline", "Buildings list root, MDI state, and dynamic menu snapshots"),
    ("element", "Elem menu and every child dialog opened from its enabled commands"),
    ("group", "Csoport menu and every child dialog opened from its enabled commands"),
    ("edit", "Szerkesztes menu and context-sensitive list actions"),
    ("tools", "Eszkozok actions available in Buildings context"),
    ("settings_window", "Beallitasok and Ablak context branches"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_progress(run_dir: Path, *, complete: bool, paused: bool = False) -> None:
    _atomic_write(run_dir / "progress.json", {
        "states": 0, "edges": 0, "failures": 0,
        "queue": 0 if complete else 1, "complete": complete,
        "paused": paused, "updated_at": _now().isoformat(),
    })


def create_plan(run_dir: Path, sandbox_project: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "work_plan.json"
    if path.exists():
        return path
    payload = {
        "schema_version": 1,
        "catalog": {"caption": "Buildings", "index": BUILDINGS_INDEX},
        "sandbox_project": str(sandbox_project),
        "created_at": _now().isoformat(),
        "reuse_sources": [
            "data/runtime_maps/catalog_contexts_9_60/04_Epuletek.json",
            "data/runtime_maps/mdi_runtime_states_9_60/project_open__mdi__epuletek",
            "data/runtime_maps/deep_native_menu_buildings_mdi_9_60.json",
        ],
        "tasks": [
            {"id": task_id, "description": description, "status": "pending", "lease": None,
             "evidence_dir": f"tasks/{task_id}"}
            for task_id, description in TASKS
        ],
    }
    _atomic_write(path, payload)
    return path


def claim_next(plan_path: Path, worker: str, lease_minutes: int = 30) -> dict[str, Any] | None:
    plan = _load(plan_path)
    now = _now()
    for task in plan["tasks"]:
        lease = task.get("lease") or {}
        expired = lease.get("expires_at") and datetime.fromisoformat(lease["expires_at"]) <= now
        if task["status"] == "pending" or (task["status"] == "leased" and expired):
            task["status"] = "leased"
            task["lease"] = {"worker": worker, "claimed_at": now.isoformat(),
                             "expires_at": (now + timedelta(minutes=lease_minutes)).isoformat()}
            _atomic_write(plan_path, plan)
            return task
    return None


def finish(plan_path: Path, task_id: str, *, status: str, note: str) -> None:
    plan = _load(plan_path)
    task = next(item for item in plan["tasks"] if item["id"] == task_id)
    task["status"] = status
    task["lease"] = None
    task["finished_at"] = _now().isoformat()
    task["note"] = note
    _atomic_write(plan_path, plan)


def run_baseline(task_dir: Path, project: Path) -> None:
    """Capture only the known root context; no Building record is modified."""
    task_dir.mkdir(parents=True, exist_ok=True)
    prepare_fresh_winwatt_session(project_path=str(project))
    # Reuse the established catalog mapper rather than reimplementing its
    # menu handling.  It snapshots Buildings + Szerkesztes/Csoport/Elem.
    import sys
    previous = sys.argv[:]
    try:
        sys.argv = ["map_catalog_contexts", "--indices", str(BUILDINGS_INDEX),
                    "--output-dir", str(task_dir), "--capture-dynamic-popups"]
        if map_catalog_contexts_main() != 0:
            raise RuntimeError("baseline catalog mapper returned nonzero")
    finally:
        sys.argv = previous


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--worker", default="local")
    parser.add_argument("--lease-minutes", type=int, default=30)
    parser.add_argument("--claim-only", action="store_true")
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    sandbox = run_dir / "sandbox" / "testwwp.wwp"
    if not sandbox.exists():
        sandbox.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / "tests" / "testwwp.wwp", sandbox)
    plan_path = create_plan(run_dir, sandbox)
    _write_progress(run_dir, complete=False)
    task = claim_next(plan_path, args.worker, args.lease_minutes)
    if task is None:
        print(json.dumps({"status": "no_pending_task", "plan": str(plan_path)}))
        return 0
    if args.claim_only:
        print(json.dumps({"status": "leased", "task": task, "plan": str(plan_path)}))
        return 0
    if task["id"] != "baseline":
        print(json.dumps({"status": "leased_for_later_worker", "task": task, "plan": str(plan_path)}))
        return 0
    try:
        pause = run_dir / "pause.request"
        while pause.exists():
            _write_progress(run_dir, complete=False, paused=True)
            time.sleep(0.25)
        run_baseline(run_dir / task["evidence_dir"], sandbox)
    except Exception as exc:
        finish(plan_path, task["id"], status="failed", note=str(exc))
        _atomic_write(run_dir / "progress.json", {
            "states": 0, "edges": 0, "failures": 1, "queue": 0,
            "complete": True, "updated_at": _now().isoformat(),
        })
        raise
    finish(plan_path, task["id"], status="completed", note="root state and dynamic menu evidence captured")
    _write_progress(run_dir, complete=True)
    print(json.dumps({"status": "completed", "task": task["id"], "plan": str(plan_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
