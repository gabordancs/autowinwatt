from pathlib import Path

from winwatt_automation.discovery.models import DiscoveryGoal, DiscoveryResult
from winwatt_automation.knowledge.store import KnowledgeStore
from winwatt_automation.planner.models import ResearchPlan
from winwatt_automation.research.orchestrator import ResearchBudget, ResearchOrchestrator


class FakePlanner:
    def __init__(self, plans: list[ResearchPlan]) -> None:
        self.plans = plans
        self.calls = 0
        self.manual_index = type("Index", (), {"search": staticmethod(lambda *_args, **_kwargs: [{"page": 1}])})()

    def plan(self, _goal: str, _hints=None, _trace=None):
        value = self.plans[min(self.calls, len(self.plans) - 1)]
        self.calls += 1
        return type("Result", (), {"plan": value})()


class FakeDiscovery:
    def run(self, goal: DiscoveryGoal) -> DiscoveryResult:
        return DiscoveryResult(session_id="disc", goal=goal, sandbox_project=goal.source_project, visited_windows=["TSelectBoundarisForm"], stopped_reason="completed")


def _plan(kind: str, target: str = "room.boundary") -> ResearchPlan:
    return ResearchPlan(goal="goal", interpreted_scope="boundary research", recommended_next_target=target, reasoning_summary="bounded next step", research_step_type=kind)


def test_orchestrator_runs_discovery_then_stops_repeated_action(tmp_path: Path) -> None:
    source = tmp_path / "source.wwp"; source.write_bytes(b"x")
    store = KnowledgeStore(path=tmp_path / "knowledge.json", capability_path=tmp_path / "none.json")
    result = ResearchOrchestrator(FakePlanner([_plan("capability_enumeration")]), store, FakeDiscovery).run(
        "learn boundaries", source_project=source, output_dir=tmp_path, budget=ResearchBudget(max_iterations=3),
    )
    assert result.outcome == "partially_learned"
    assert result.windows_visited == ["TSelectBoundarisForm"]
    assert result.iterations[-1].capability_gap is not None


def test_orchestrator_stops_without_raw_ui_for_unsupported_scope(tmp_path: Path) -> None:
    source = tmp_path / "source.wwp"; source.write_bytes(b"x")
    store = KnowledgeStore(path=tmp_path / "knowledge.json", capability_path=tmp_path / "none.json")
    result = ResearchOrchestrator(FakePlanner([_plan("unsupported")]), store, FakeDiscovery).run(
        "create a structure", source_project=source, output_dir=tmp_path, budget=ResearchBudget(max_iterations=2),
    )
    assert result.outcome == "partially_learned"
    assert result.actions_taken[0].kind == "stop"
    assert result.iterations[0].capability_gap.missing_primitive == "controlled_ui_discovery_for_requested_scope"

