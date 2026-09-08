from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from winwatt_automation.research.ui_exploration import ControlSummary, ExplorationAction, WindowSummary
from winwatt_automation.scripts.recursive_structure_crawler import (
    FrontierNode,
    RecursiveStructureCrawler,
    write_json,
)


def _state(name: str, controls: list[ControlSummary]) -> WindowSummary:
    return WindowSummary(identity="main", title="Szerkezetek", class_name="TMainForm", state_fingerprint=name, controls=controls)


class _Explorer:
    def __init__(self) -> None:
        self.root = _state("root", [
            ControlSummary(identity="a", caption="Első", control_type="Button", class_name="TButton", enabled=True),
            ControlSummary(identity="b", caption="Második", control_type="Button", class_name="TButton", enabled=True),
        ])
        self.current = self.root
        self.activations: list[str] = []

    def inspect_window(self) -> WindowSummary:
        return self.current

    def activate_control(self, identity: str, iteration: int) -> ExplorationAction:
        before = self.current
        self.activations.append(identity)
        self.current = _state(f"child-{identity}", [])
        return ExplorationAction(
            action_id=f"action-{identity}", iteration=iteration, window_before=before,
            selected_control=identity, action_type="activate_control", safety_class="safe_navigation",
            state_before=before, state_after=self.current, success=True,
        )

    def go_back(self, iteration: int) -> ExplorationAction:
        before = self.current
        self.current = self.root
        return ExplorationAction(
            action_id="back", iteration=iteration, window_before=before, action_type="go_back",
            safety_class="safe_navigation", state_before=before, state_after=self.root, success=True,
        )


class _Crawler(RecursiveStructureCrawler):
    def __init__(self, tmp_path: Path, *, resume: bool = False) -> None:
        super().__init__(source_project=tmp_path / "source.wwp", output_root=tmp_path / "out", stop_at=datetime.now() + timedelta(minutes=1), max_actions=2, import_navigation=False, resume=resume)
        self.fresh_calls = 0

    def _fresh_explorer(self, branch_id: str):  # type: ignore[override]
        self.fresh_calls += 1
        return object(), _Explorer(), self.output_root / "sandbox"

    def _replay_path(self, explorer, path):  # type: ignore[override]
        return explorer.inspect_window()


def test_siblings_share_one_frontier_session_and_local_reset(tmp_path: Path) -> None:
    crawler = _Crawler(tmp_path)
    result = crawler.run()

    assert result["actions_attempted"] == 2
    assert crawler.fresh_calls == 1
    assert result["performance_counters"]["sandbox_copies"] == 0  # fake launcher; production increments this
    assert result["performance_counters"]["local_resets"] == 2
    assert result["performance_counters"]["children_discovered"] == 2


def test_semantic_fingerprint_ignores_window_session_noise() -> None:
    from winwatt_automation.scripts.recursive_structure_crawler import semantic_state_fingerprint

    controls = [ControlSummary(identity="runtime-a", caption="Elem", control_type="MenuItem", class_name="TMenuItem", enabled=True, parent_identity="parent", ordinal=2)]
    other_controls = [ControlSummary(identity="runtime-b", caption="Elem", control_type="MenuItem", class_name="TMenuItem", enabled=True, parent_identity="parent", ordinal=2)]
    assert semantic_state_fingerprint(_state("raw-one", controls)) == semantic_state_fingerprint(
        WindowSummary(identity="another-hwnd", title="other sandbox path", class_name="TMainForm", state_fingerprint="raw-two", controls=other_controls)
    )


def test_popup_reset_is_local_when_it_returns_to_parent(tmp_path: Path) -> None:
    crawler = _Crawler(tmp_path)
    explorer = _Explorer()
    popup = ControlSummary(identity="menu", caption="Fájl", control_type="MenuItem", class_name="TMenuItem", enabled=True)
    explorer.root = _state("root", [popup])
    explorer.current = explorer.root
    action = explorer.activate_control("menu", 1)

    _, restored = crawler._restore_parent(
        service=object(), explorer=explorer, sandbox=tmp_path / "sandbox", path=[], expected_parent=explorer.root,
        control=popup, action=action,
    )

    assert restored.state_fingerprint == "root"
    assert crawler.counters["popup_resets"] == 1
    assert crawler.counters["project_reopens"] == 0


def test_failed_safety_action_does_not_inject_escape_or_reopen(tmp_path: Path) -> None:
    crawler = _Crawler(tmp_path)
    explorer = _Explorer()
    control = explorer.root.controls[0]
    failed = ExplorationAction(
        action_id="blocked", iteration=1, window_before=explorer.root, selected_control=control.identity,
        action_type="activate_control", safety_class="blocked", state_before=explorer.root,
        state_after=None, success=False, failure="blocked",
    )

    _, restored = crawler._restore_parent(
        service=object(), explorer=explorer, sandbox=tmp_path / "sandbox", path=[], expected_parent=explorer.root,
        control=control, action=failed,
    )

    assert restored.state_fingerprint == "root"
    assert crawler.counters["failed_actions_no_reset"] == 1
    assert crawler.counters["project_reopens"] == 0


def test_successful_in_process_reopen_does_not_call_fresh_launcher(tmp_path: Path, monkeypatch) -> None:
    class Service:
        opened_fresh = False
        def reopen_sandbox_project_in_current_session(self, sandbox):
            return {"success": True, "same_process": True}
        def open_project(self, sandbox):
            self.opened_fresh = True

    crawler = _Crawler(tmp_path)
    service = Service()
    monkeypatch.setattr("winwatt_automation.scripts.recursive_structure_crawler.activate_structures_catalog_native", lambda: True)
    monkeypatch.setattr("winwatt_automation.scripts.recursive_structure_crawler.active_mdi_title", lambda: "Szerkezetek")
    monkeypatch.setattr("winwatt_automation.scripts.recursive_structure_crawler.get_main_window", lambda: object())

    crawler._reopen_same_sandbox(service, tmp_path / "sandbox" / "testwwp.wwp")

    assert not service.opened_fresh
    assert crawler.counters["project_reopens"] == 1
    assert crawler.counters["winwatt_relaunch_fallbacks"] == 0


def test_resume_skips_checkpointed_action_without_relaunch(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    write_json(output / "states.json", [])
    write_json(output / "transitions.json", [])
    write_json(output / "visited_actions.json", [{"state_fingerprint": "root", "control_identity": "a", "relevant_context": "Button||"}])
    write_json(output / "visited_paths.json", [])
    write_json(output / "frontier.json", [{"depth": 0, "path": []}])
    write_json(output / "recursive_summary.json", {"actions_attempted": 1, "replays": 0, "replay_failures": 0, "repeats_avoided": 0, "max_depth_reached": 0, "errors": [], "performance_counters": {}})

    crawler = _Crawler(tmp_path, resume=True)
    result = crawler.run()

    assert crawler.fresh_calls == 1
    assert result["actions_attempted"] == 2
    assert result["performance_counters"]["actions_skipped_duplicate"] >= 1


def test_failed_local_reset_falls_back_to_reopen_of_same_sandbox(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("winwatt_automation.scripts.recursive_structure_crawler.activate_structures_catalog_native", lambda: False)
    class BrokenBackExplorer(_Explorer):
        def go_back(self, iteration: int) -> ExplorationAction:
            before = self.current
            wrong = _state("wrong", [])
            self.current = wrong
            return ExplorationAction(
                action_id="bad-back", iteration=iteration, window_before=before, action_type="go_back",
                safety_class="safe_navigation", state_before=before, state_after=wrong, success=True,
            )

    class FallbackCrawler(_Crawler):
        def _reopen_same_sandbox(self, service, sandbox):  # type: ignore[override]
            self.counters["project_reopens"] += 1
            return _Explorer()

    crawler = FallbackCrawler(tmp_path)
    broken = BrokenBackExplorer()
    broken.activate_control("a", 1)
    restored_explorer, restored = crawler._restore_parent(
        service=object(), explorer=broken, sandbox=tmp_path / "sandbox", path=[], expected_parent=broken.root,
    )

    assert isinstance(restored_explorer, _Explorer)
    assert restored.state_fingerprint == "root"
    assert crawler.counters["reset_failures"] == 1
    assert crawler.counters["project_reopens"] == 1
