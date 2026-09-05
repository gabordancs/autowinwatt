"""Short, flushed live proof for the identity-based research loop."""
from __future__ import annotations

import json
import os
from pathlib import Path

from winwatt_automation.dev.live_research_check import load_project_env


def _atomic_json(path: Path, payload: dict) -> None:
    """Durable replacement after every iteration, including timeout/error paths."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def main() -> int:
    load_project_env()
    if not os.environ.get("OPENAI_API_KEY"):
        print("LIVE CHECK BLOCKED: OPENAI_API_KEY unavailable")
        return 2
    if os.environ.get("WINWATT_E2E") != "1":
        print("LIVE CHECK BLOCKED: WINWATT_E2E unavailable")
        return 2

    from winwatt_automation.cli.main import DEFAULT_MANUAL_INDEX, DEFAULT_MANUAL_PATH, _load_manual_index
    from winwatt_automation.discovery.runner import LiveRoomBoundaryDiscoveryUI, ResearchDiscoveryRunner
    from winwatt_automation.experiments.runner import ExperimentRunner
    from winwatt_automation.knowledge.store import KnowledgeStore
    from winwatt_automation.planner.planner import ResearchPlanner
    from winwatt_automation.planner.provider import OpenAIProvider
    from winwatt_automation.research.orchestrator import ResearchOrchestrator

    root = Path.cwd()
    output_dir = root / "data" / "runtime_maps" / "research_sessions"
    audit_path = output_dir / "identity_loop_live_audit.json"
    source_project = root / "tests" / "testwwp.wwp"
    store = KnowledgeStore()
    planner = ResearchPlanner(OpenAIProvider(), store, _load_manual_index(DEFAULT_MANUAL_PATH, DEFAULT_MANUAL_INDEX))
    orchestrator = ResearchOrchestrator(
        planner, store,
        discovery_factory=lambda: ResearchDiscoveryRunner(LiveRoomBoundaryDiscoveryUI(output_dir), store=store),
        experiment_runner=ExperimentRunner(output_dir=output_dir / "experiments"),
    )
    _atomic_json(audit_path, {"status": "started", "iterations": []})
    result = orchestrator.run_identity_loop_check(
        "Tanuld meg, hogyan kell új szerkezetet létrehozni.",
        source_project=source_project.resolve(), output_dir=output_dir.resolve(),
        human_hints=["A Jegyzékek menüben van a Szerkezetek ablak. Meg kell nyitni a felső menüből."],
        on_iteration=lambda payload: _atomic_json(audit_path, payload),
        max_seconds=120,
    )
    print(json.dumps({"audit_path": str(audit_path), **result}, ensure_ascii=False, default=str))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
