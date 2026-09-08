"""Unattended, sandbox-only runtime mapper for the WinWatt UI graph.

The shared :class:`GlobalMappingStore` is the durable evidence base.  This
command imports legacy evidence once, then delegates real UI exploration to
the proven recursive Structure Catalog crawler in ``background_mode``.  It is
deliberately LLM-free: prioritisation is deterministic and every branch gets
its own disposable sandbox.
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from winwatt_automation.knowledge.global_mapping import GlobalMappingStore, LegacyMappingImporter
from winwatt_automation.scripts.recursive_structure_crawler import (
    RecursiveStructureCrawler,
    parse_stop_at,
    write_json,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _count(store: GlobalMappingStore) -> dict[str, int]:
    return {"states": len(store.data["states"]), "transitions": len(store.data["transitions"])}


def _operation_coverage(crawler_result: dict[str, Any] | None) -> dict[str, int]:
    coverage = {name: 0 for name in ("create", "edit", "assign", "copy", "rename", "delete", "save", "reopen")}
    for edge in (crawler_result or {}).get("transition_records", []):
        operation = edge.get("operation")
        if edge.get("success") and operation in coverage:
            coverage[operation] += 1
    coverage["reopen"] = int((crawler_result or {}).get("performance_counters", {}).get("project_reopens", 0))
    return coverage


def _deadline(hours: float, stop_at: str | None) -> datetime:
    deadline = datetime.now() + timedelta(hours=max(hours, 0.001))
    if stop_at:
        deadline = min(deadline, parse_stop_at(stop_at))
    return deadline


def _run_root(value: Path | None, *, resume: bool) -> Path:
    if value:
        return value.resolve()
    if resume:
        raise ValueError("--resume requires --output-root so the previous checkpoint is unambiguous")
    run_id = f"background_{datetime.now():%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:8]}"
    return PROJECT_ROOT / "data" / "runtime_maps" / "background_mapping" / run_id


def _summary(
    *, run_id: str, started: datetime, mode: str, store: GlobalMappingStore,
    before_runtime: dict[str, int], crawler_result: dict[str, Any] | None,
    import_result: dict[str, Any] | None, error: str | None = None,
) -> dict[str, Any]:
    elapsed = max((datetime.now() - started).total_seconds(), 0.001)
    after = _count(store)
    counters = (crawler_result or {}).get("performance_counters", {})
    actions = int((crawler_result or {}).get("actions_attempted", 0))
    operations = _operation_coverage(crawler_result)
    return {
        "run_id": run_id,
        "kind": "unattended_background_mapper",
        "started_at": started.isoformat(),
        "finished_at": datetime.now().isoformat(),
        "elapsed_seconds": round(elapsed, 3),
        "mode": mode,
        "safety": {
            "sandbox_only": True,
            "llm_used": False,
            "commit_candidates_executed": mode == "aggressive-sandbox-map",
            "known_edges": "replay/traversal hints only; globally known edges are not exploration work",
        },
        "legacy_import": import_result,
        "global_store": {"path": str(store.root), "before_runtime": before_runtime, "after_runtime": after},
        "new_semantic_states": max(0, after["states"] - before_runtime["states"]),
        "new_transitions": max(0, after["transitions"] - before_runtime["transitions"]),
        "new_windows_dialogs_editors": len({
            (edge.get("to_state"), edge.get("to_semantic_state"))
            for edge in (crawler_result or {}).get("transition_records", [])
            if edge.get("success") and edge.get("state_changed")
        }),
        "max_depth": (crawler_result or {}).get("max_depth_reached", 0),
        "frontier_remaining": (crawler_result or {}).get("frontier_remaining", 0),
        "recoveries": {
            "branch_recoveries": counters.get("branch_recoveries", 0),
            "branch_failures": counters.get("errors", 0),
            "project_reopens": counters.get("project_reopens", 0),
            "winwatt_relaunch_fallbacks": counters.get("winwatt_relaunch_fallbacks", 0),
            "replay_failures": (crawler_result or {}).get("replay_failures", 0),
            "destroyed_or_replaced_sandboxes": counters.get("sandboxes_discarded", 0),
        },
        "actions_per_hour": round(actions / (elapsed / 3600), 2),
        "states_per_hour": round(max(0, after["states"] - before_runtime["states"]) / (elapsed / 3600), 2),
        "transitions_per_hour": round(max(0, after["transitions"] - before_runtime["transitions"]) / (elapsed / 3600), 2),
        "crud_save_reopen_coverage": operations,
        "crawler": crawler_result,
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM-free unattended sandbox Background Mapper")
    parser.add_argument("--project", type=Path, help="Source .wwp project; copied to disposable sandboxes")
    parser.add_argument("--output-root", type=Path, help="Durable run directory; required with --resume")
    parser.add_argument("--store-dir", type=Path, default=PROJECT_ROOT / "data" / "knowledge" / "global_mapping")
    parser.add_argument("--import-existing", action="store_true", help="Only import/index existing evidence unless --project is supplied")
    parser.add_argument("--dry-run", action="store_true", help="Show existing frontier without runtime UI work")
    parser.add_argument("--frontier-limit", type=int, default=30)
    parser.add_argument("--mode", choices=("safe-map", "sandbox-map", "aggressive-sandbox-map"), default="aggressive-sandbox-map")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-runtime-hours", type=float, default=6.0)
    parser.add_argument("--stop-at", help="Optional local hard stop in HH:MM; earlier of this and --max-runtime-hours wins")
    parser.add_argument("--max-depth", type=int, default=18)
    parser.add_argument("--max-actions", type=int, default=12000)
    parser.add_argument("--max-states", type=int, default=5000)
    parser.add_argument("--replay-pause-seconds", type=float, default=0.08)
    parser.add_argument("--guide")
    parser.add_argument("--demonstrations-dir", type=Path)
    parser.add_argument("--no-import-navigation", action="store_true")
    args = parser.parse_args()

    store = GlobalMappingStore(args.store_dir.resolve())
    result: dict[str, Any] = {"store": str(store.root), "dry_run": args.dry_run}
    # A normal runtime starts from all accumulated evidence, but remains
    # idempotent due to the import manifest.
    import_result = LegacyMappingImporter(project_root=PROJECT_ROOT, store=store).import_existing(dry_run=args.dry_run)
    result["import"] = import_result
    result["useful_frontier"] = store.useful_frontier()[:max(0, args.frontier_limit)]
    result.update({"known_states": len(store.data["states"]), "known_transitions": len(store.data["transitions"])})
    if args.dry_run or (args.import_existing and not args.project):
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if not args.project:
        parser.error("--project is required for unattended runtime exploration")

    try:
        output_root = _run_root(args.output_root, resume=args.resume)
    except ValueError as exc:
        parser.error(str(exc))
    output_root.mkdir(parents=True, exist_ok=True)
    started = datetime.now()
    run_id = output_root.name
    before_runtime = _count(store)
    deadline = _deadline(args.max_runtime_hours, args.stop_at)
    audit_path = output_root / "background_audit.json"
    write_json(audit_path, {
        "run_id": run_id, "status": "running", "started_at": started.isoformat(),
        "deadline": deadline.isoformat(), "mode": args.mode, "global_store": str(store.root),
        "runtime_policy": {"priority": "depth+novelty", "skip_globally_known_edges": True,
                           "fresh_sandbox_per_branch": True, "recover_branch_failure": True},
    })
    crawler = RecursiveStructureCrawler(
        source_project=args.project,
        output_root=output_root / "crawl",
        stop_at=deadline,
        max_depth=max(args.max_depth, 0),
        max_actions=max(args.max_actions, 1),
        max_states=max(args.max_states, 1),
        replay_pause_seconds=max(args.replay_pause_seconds, 0.0),
        import_navigation=not args.no_import_navigation,
        resume=args.resume,
        guide=args.guide,
        demonstrations_dir=args.demonstrations_dir,
        global_store_dir=store.root,
        background_mode=True,
        aggressive_sandbox=args.mode == "aggressive-sandbox-map",
    )
    crawler_result: dict[str, Any] | None = None
    error: str | None = None
    exit_code = 0
    try:
        crawler_result = crawler.run()
    except KeyboardInterrupt:
        crawler.checkpoint_interrupted()
        error = "interrupted_by_user"
        exit_code = 130
    except Exception as exc:  # Branch failures are recovered in crawler; this is a wrapper-level failure.
        crawler.checkpoint_interrupted()
        error = repr(exc)
        exit_code = 2
    finally:
        # The crawler owns a separate store instance and checkpoints it after
        # every branch.  Reload rather than saving this older instance here:
        # otherwise a wrapper-level final save could overwrite fresh runtime
        # observations with the pre-run snapshot.
        store = GlobalMappingStore(store.root)
        if crawler_result is not None:
            crawler_result = {**crawler_result, "transition_records": crawler.transitions}
        summary = _summary(run_id=run_id, started=started, mode=args.mode, store=store,
                           before_runtime=before_runtime, crawler_result=crawler_result,
                           import_result=import_result, error=error)
        write_json(output_root / "background_summary.json", summary)
        write_json(audit_path, {**summary, "status": "interrupted" if error == "interrupted_by_user" else ("failed" if error else "completed")})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
