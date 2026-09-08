from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from winwatt_automation.research.ui_exploration import ControlSummary
from winwatt_automation.scripts.background_mapper import _deadline, _summary
from winwatt_automation.scripts.recursive_structure_crawler import RecursiveStructureCrawler
from winwatt_automation.knowledge.global_mapping import GlobalMappingStore


def test_background_deadline_is_bounded_by_hours() -> None:
    deadline = _deadline(0.01, None)
    assert datetime.now() < deadline <= datetime.now() + timedelta(minutes=1)


def test_background_priority_prefers_deep_anonymous_navigation(tmp_path: Path) -> None:
    crawler = RecursiveStructureCrawler(
        source_project=tmp_path / "source.wwp", output_root=tmp_path / "run",
        stop_at=datetime.now() + timedelta(minutes=1), import_navigation=False, background_mode=True,
    )
    anonymous_menu = ControlSummary(identity="anonymous", caption="", control_type="MenuItem", class_name="TMenuItem", enabled=True)
    noisy_scroll = ControlSummary(identity="scroll", caption="Scroll", control_type="Button", class_name="TButton", enabled=True)
    assert crawler._background_score(None, anonymous_menu, child_state=None, depth=4) > crawler._background_score(None, noisy_scroll, child_state=None, depth=0)


def test_summary_counts_only_runtime_additions(tmp_path: Path) -> None:
    store = GlobalMappingStore(tmp_path / "global")
    store.merge_state({"fingerprint": "old"}, artifact=tmp_path / "legacy.json")
    before = {"states": 1, "transitions": 0}
    summary = _summary(run_id="run", started=datetime.now() - timedelta(seconds=2), mode="safe-map", store=store, before_runtime=before, crawler_result={"actions_attempted": 2, "performance_counters": {}}, import_result={})
    assert summary["new_semantic_states"] == 0
    assert summary["actions_per_hour"] > 0
