from __future__ import annotations

from pathlib import Path

from winwatt_automation.discovery.models import DiscoveryGoal, StructureClassificationGoal
from winwatt_automation.discovery.runner import ResearchDiscoveryRunner
from winwatt_automation.knowledge.models import KnowledgeStatus
from winwatt_automation.knowledge.store import KnowledgeStore


class FakeDiscoveryUI:
    def __init__(self) -> None:
        self.inspected: list[str] = []
        self.closed = False

    def prepare_sandbox(self, source_project: Path, session_id: str) -> Path:
        target = source_project.parent / session_id / source_project.name
        target.parent.mkdir(parents=True)
        target.write_bytes(source_project.read_bytes())
        return target

    def open_boundary_selector(self, sandbox_project: Path, room_name: str) -> str:
        return "TSelectBoundarisForm"

    def visible_library_types(self, selector: str) -> list[str]:
        return ["Külső fal", "Padlásfödém", "Ablak"]

    def inspect_type(self, selector: str, caption: str):
        self.inspected.append(caption)
        return ({"items": [caption]}, {"detail": {"window_class": "TBoundaryModifyForm", "controls": [
            {"caption": "X", "control_type": "Text", "class": "TLabel", "enabled": True},
            {"caption": "", "control_type": "Edit", "class": "TEdit", "enabled": True},
        ]}}, "TBoundaryModifyForm")

    def close_selector(self, selector: str) -> None:
        self.closed = True


class BlockingDiscoveryUI(FakeDiscoveryUI):
    def open_boundary_selector(self, sandbox_project: Path, room_name: str) -> str:
        raise RuntimeError("foreground focus guard rejected an unrelated dialog")


def test_bounded_boundary_discovery_records_hypotheses_not_verified(tmp_path: Path) -> None:
    source = tmp_path / "source.wwp"
    source.write_bytes(b"sandbox template")
    store = KnowledgeStore(path=tmp_path / "knowledge.json", capability_path=tmp_path / "none.json")
    ui = FakeDiscoveryUI()
    runner = ResearchDiscoveryRunner(ui, store=store)

    result = runner.run(DiscoveryGoal(
        operation="enumerate_room_boundary_structure_types", source_project=str(source), max_ui_actions=9,
    ))

    assert result.visited_windows == ["TRoomModifyForm", "TSelectBoundarisForm", "TBoundaryModifyForm"]
    assert [item.proposed_concept for item in result.candidates] == [
        "room.boundary.structure_type.kulso_fal", "room.boundary.structure_type.padlasfodem", "room.boundary.structure_type.ablak",
    ]
    assert all(item.status is KnowledgeStatus.HYPOTHESIS for item in result.candidates)
    assert all(not evidence.deterministic for evidence in result.evidence)
    assert ui.closed is True
    assert len(store.list_candidate_capabilities("room.boundary.structure_type")) == 3


def test_discovery_stops_at_action_budget_without_any_uncontrolled_operation(tmp_path: Path) -> None:
    source = tmp_path / "source.wwp"
    source.write_bytes(b"sandbox template")
    ui = FakeDiscoveryUI()
    result = ResearchDiscoveryRunner(ui).run(DiscoveryGoal(
        operation="enumerate_room_boundary_structure_types", source_project=str(source), max_ui_actions=5,
    ))

    assert result.stopped_reason == "max_ui_actions"
    assert ui.inspected == ["Külső fal"]
    # Catalog enumeration still records all observed types even when the
    # bounded detail-inspection budget permits only one.
    assert len(result.candidates) == 3


def test_discovery_records_startup_focus_block_as_a_bounded_audited_result(tmp_path: Path) -> None:
    source = tmp_path / "source.wwp"
    source.write_bytes(b"sandbox template")
    result = ResearchDiscoveryRunner(BlockingDiscoveryUI()).run(DiscoveryGoal(
        operation="enumerate_room_boundary_structure_types", source_project=str(source),
    ))
    assert result.stopped_reason == "blocked_before_catalog"
    assert "foreground focus guard" in result.errors[0]
    assert result.candidates == []


def test_structure_classification_groups_by_detail_evidence_not_caption(tmp_path: Path) -> None:
    source = tmp_path / "source.wwp"
    source.write_bytes(b"sandbox template")
    store = KnowledgeStore(path=tmp_path / "knowledge.json", capability_path=tmp_path / "none.json")
    result = ResearchDiscoveryRunner(FakeDiscoveryUI(), store=store).classify_room_boundary_structures(
        StructureClassificationGoal(source_project=str(source), max_representatives=3, max_ui_actions=12),
    )

    assert result.catalog_references_count == 3
    assert len(result.structure_references) == 3
    assert len(result.structure_kinds) == 1
    assert result.structure_kinds[0].classification_basis.startswith("same native detail form")
    assert len(result.structure_kinds[0].member_structure_references) == 3
    assert result.workflow_summary["committed"] is False
    assert all(item.status is KnowledgeStatus.HYPOTHESIS for item in result.structure_references)
    assert all(item.status is KnowledgeStatus.HYPOTHESIS for item in result.structure_kinds)
    assert len(store.list_structure_reference_candidates()) == 3
    assert len(store.list_structure_kind_candidates()) == 1


def test_structure_classification_budget_remains_bounded(tmp_path: Path) -> None:
    source = tmp_path / "source.wwp"
    source.write_bytes(b"sandbox template")
    ui = FakeDiscoveryUI()
    result = ResearchDiscoveryRunner(ui).classify_room_boundary_structures(
        StructureClassificationGoal(source_project=str(source), max_representatives=3, max_ui_actions=5),
    )
    assert result.stopped_reason == "max_ui_actions"
    assert ui.inspected == [ui.visible_library_types("selector")[0]]
