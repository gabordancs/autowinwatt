"""Unattended sandbox-only Structure Catalog mapping until a wall-clock deadline.

The runner first performs an explicit disposable structure creation experiment,
then verifies it through save -> close -> reopen -> exact readback.  After that
it hands the committed sandbox to RecursiveStructureCrawler, which breadth-first
expands every newly discovered UI frontier until the deadline or configured
budgets are reached.

The original source project is never modified.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.research.ui_exploration import SandboxUIExplorer
from winwatt_automation.runtime_mapping.mdi_state_model import (
    activate_structures_catalog_native,
    active_mdi_title,
)
from winwatt_automation.runtime_mapping.structure_catalog_deep_mapper import StructureCatalogDeepMapper
from winwatt_automation.scripts.recursive_structure_crawler import RecursiveStructureCrawler
from winwatt_automation.services.winwatt_service import WinWattService


def parse_stop_at(value: str) -> datetime:
    try:
        hour, minute = (int(part) for part in value.split(":", 1))
    except Exception as exc:
        raise argparse.ArgumentTypeError("--stop-at must be HH:MM") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise argparse.ArgumentTypeError("--stop-at must be HH:MM")
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def verify_created_structure(run_dir: Path, source_project_name: str) -> dict[str, Any]:
    sandbox = run_dir / "sandbox" / source_project_name
    expected_name = f"AI_TEST_{run_dir.name}"
    service = WinWattService()
    try:
        service.close_project_gracefully()
    except Exception:
        pass
    service.open_project(sandbox)
    if not activate_structures_catalog_native() or active_mdi_title() != "Szerkezetek":
        return {
            "verified": False,
            "expected_name": expected_name,
            "reason": "catalog.structure.open failed after reopen",
        }
    explorer = SandboxUIExplorer(get_main_window(), sandbox)
    state = explorer.inspect_window()
    match = next(
        (
            item
            for item in state.controls
            if item.control_type == "ListItem"
            and item.caption == expected_name
            and item.enabled
        ),
        None,
    )
    return {
        "verified": match is not None,
        "expected_name": expected_name,
        "matched_identity": match.identity if match else None,
        "state_fingerprint": state.state_fingerprint,
        "reason": None if match else "exact AI_TEST structure not found after reopen",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unattended sandbox Structure Catalog mapping with recursive frontier expansion"
    )
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--stop-at", default="08:00", help="Local wall-clock deadline HH:MM; default 08:00")

    # Creation bootstrap budget.  This stage is deliberately narrow and explicit.
    parser.add_argument("--creation-max-actions", type=int, default=100)

    # Recursive graph traversal budgets.  New states are automatically expanded;
    # these are hard safety ceilings, not traversal-depth hints.
    parser.add_argument("--max-depth", type=int, default=64)
    parser.add_argument("--max-actions", type=int, default=100000)
    parser.add_argument("--max-states", type=int, default=25000)
    parser.add_argument("--replay-pause-seconds", type=float, default=0.08)
    parser.add_argument("--no-import-navigation", action="store_true")
    args = parser.parse_args()

    source = args.project.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    stop_at = parse_stop_at(args.stop_at)

    summary: dict[str, Any] = {
        "source_project": str(source),
        "started_at": datetime.now().isoformat(),
        "stop_at": stop_at.isoformat(),
        "creation": None,
        "creation_verification": None,
        "recursive_crawl": None,
        "errors": [],
    }
    write_json(output_root / "overnight_summary.json", summary)

    # Phase 1: explicitly create one disposable sandbox structure and persist it.
    creation_dir = output_root / "creation_bootstrap"
    try:
        creation = StructureCatalogDeepMapper(
            source_project=source,
            output_dir=creation_dir,
            max_actions=max(args.creation_max_actions, 1),
            import_navigation=not args.no_import_navigation,
            focus_creation=True,
            probe_input=True,
            commit_creation=True,
        ).run()
        summary["creation"] = creation
        write_json(output_root / "overnight_summary.json", summary)
    except Exception as exc:
        summary["errors"].append({"stage": "creation", "error": repr(exc)})
        summary["status"] = "creation_failed"
        summary["finished_at"] = datetime.now().isoformat()
        write_json(output_root / "overnight_summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, default=str))
        return 2

    if datetime.now() >= stop_at:
        summary["status"] = "deadline_reached_after_creation"
        summary["finished_at"] = datetime.now().isoformat()
        write_json(output_root / "overnight_summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, default=str))
        return 0

    # Phase 2: deterministic persistence proof before using the mutated sandbox as
    # the recursive crawler's source.  A failed proof is recorded but does not
    # silently become VERIFIED knowledge.
    try:
        verification = verify_created_structure(creation_dir, source.name)
        summary["creation_verification"] = verification
        write_json(output_root / "creation_verification.json", verification)
        write_json(output_root / "overnight_summary.json", summary)
    except Exception as exc:
        summary["errors"].append({"stage": "creation_verification", "error": repr(exc)})
        verification = {"verified": False, "reason": repr(exc)}
        summary["creation_verification"] = verification
        write_json(output_root / "overnight_summary.json", summary)

    if datetime.now() >= stop_at:
        summary["status"] = "deadline_reached_after_verification"
        summary["finished_at"] = datetime.now().isoformat()
        write_json(output_root / "overnight_summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, default=str))
        return 0

    committed_sandbox = creation_dir / "sandbox" / source.name
    if not committed_sandbox.is_file():
        summary["errors"].append(
            {"stage": "recursive_crawl", "error": f"committed sandbox missing: {committed_sandbox}"}
        )
        summary["status"] = "sandbox_missing"
        summary["finished_at"] = datetime.now().isoformat()
        write_json(output_root / "overnight_summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, default=str))
        return 3

    # Phase 3: true frontier traversal.  Every changed state is queued as a child
    # frontier and automatically expanded.  Each sibling/path is replayed from a
    # fresh sandbox copy by RecursiveStructureCrawler, so traversal does not rely
    # on fragile deep Escape/backtracking behavior.
    try:
        crawler = RecursiveStructureCrawler(
            source_project=committed_sandbox,
            output_root=output_root / "recursive_crawl",
            stop_at=stop_at,
            max_depth=max(args.max_depth, 0),
            max_actions=max(args.max_actions, 1),
            max_states=max(args.max_states, 1),
            replay_pause_seconds=max(args.replay_pause_seconds, 0.0),
            import_navigation=not args.no_import_navigation,
        )
        crawl_result = crawler.run()
        summary["recursive_crawl"] = crawl_result
    except Exception as exc:
        summary["errors"].append({"stage": "recursive_crawl", "error": repr(exc)})
        summary["recursive_crawl"] = {"status": "failed", "error": repr(exc)}

    if datetime.now() >= stop_at:
        status = "deadline_reached"
    elif summary.get("recursive_crawl", {}).get("status") == "frontier_exhausted":
        status = "frontier_exhausted"
    else:
        status = summary.get("recursive_crawl", {}).get("status", "complete")

    summary["status"] = status
    summary["finished_at"] = datetime.now().isoformat()
    write_json(output_root / "overnight_summary.json", summary)
    print(
        json.dumps(
            {
                "status": status,
                "output_root": str(output_root),
                "stop_at": stop_at.isoformat(),
                "creation_verified": bool((summary.get("creation_verification") or {}).get("verified")),
                "recursive_crawl": summary.get("recursive_crawl"),
            },
            ensure_ascii=False,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
