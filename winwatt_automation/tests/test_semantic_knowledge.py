from __future__ import annotations

import json
from pathlib import Path

import pytest

from winwatt_automation.knowledge import (
    EvidenceRef,
    ExperimentResult,
    Hypothesis,
    KnowledgeStatus,
    KnowledgeStore,
)


def _capabilities(path: Path) -> Path:
    payload = {
        "room.area_m2": {
            "ui_read": "verified", "ui_write": "verified", "roundtrip_verified": True,
            "preferred": "ui", "evidence": "data/evidence/area.json",
        }
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_imported_room_capability_is_deterministic_verified_knowledge(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.json", _capabilities(tmp_path / "capabilities.json"))
    concept = store.get_concept("room.area_m2")
    assert concept is not None
    assert concept.status is KnowledgeStatus.VERIFIED
    assert concept.unit == "m2"
    assert store.get_capability("room.area_m2").roundtrip_verified is True
    assert [item.concept for item in store.search_concepts("area")] == ["room.area_m2"]


def test_hypothesis_never_enters_verified_state(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.json", _capabilities(tmp_path / "capabilities.json"))
    hypothesis = Hypothesis(hypothesis_id="h_unknown", target_capability="room.unknown", semantic_guess="Possibly a room coefficient", confidence=0.72)
    assert store.store_hypothesis(hypothesis).status is KnowledgeStatus.HYPOTHESIS
    with pytest.raises(ValueError, match="verified"):
        Hypothesis(hypothesis_id="bad", target_capability="room.unknown", semantic_guess="bad", status="verified")


def test_promotion_requires_deterministic_roundtrip_evidence(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.json", _capabilities(tmp_path / "capabilities.json"))
    incomplete = ExperimentResult(experiment_id="one", hypothesis_id="h", target_capability="room.area_m2", success=True, roundtrip_verified=True)
    with pytest.raises(ValueError, match="deterministic"):
        store.promote_to_verified("room.area_m2", incomplete)
    verified = ExperimentResult(
        experiment_id="two", hypothesis_id="h", target_capability="room.area_m2", success=True, roundtrip_verified=True,
        evidence=[EvidenceRef(kind="verification", deterministic=True, data={"expected": 31.7, "actual": 31.7})],
    )
    assert store.promote_to_verified("room.area_m2", verified).confidence == 1.0
