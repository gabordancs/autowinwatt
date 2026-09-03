from __future__ import annotations

import json
from pathlib import Path

import pytest

from winwatt_automation.knowledge import EvidenceRef, ExperimentResult, Hypothesis, KnowledgeStatus, KnowledgeStore


def _store(tmp_path: Path) -> KnowledgeStore:
    caps = tmp_path / "room_capabilities.json"
    caps.write_text(json.dumps({"room.area_m2": {
        "ui_read": "verified", "ui_write": "verified", "roundtrip_verified": True, "preferred": "ui", "evidence": "area.json",
    }}), encoding="utf-8")
    return KnowledgeStore(tmp_path / "knowledge.json", caps)


def _result(*, experiment_id: str, hypothesis_id: str, capability: str, success: bool = True, actual: float = 1.37) -> ExperimentResult:
    return ExperimentResult(
        experiment_id=experiment_id, hypothesis_id=hypothesis_id, target_capability=capability,
        success=success, expected=1.37, actual=actual, roundtrip_verified=success,
        evidence=[EvidenceRef(kind="verification", deterministic=True, data={"expected": 1.37, "actual": actual})],
    )


def test_external_wall_capability_starts_unseeded_then_completes_lifecycle(tmp_path: Path) -> None:
    store = _store(tmp_path)
    capability = "room.boundary.external_wall.x_m"
    assert store.get_concept(capability) is None
    hypothesis = store.store_hypothesis(Hypothesis(
        hypothesis_id="hyp_wall_x", target_capability=capability,
        semantic_guess="The external-wall geometry X field in metres", confidence=0.72,
    ))
    assert hypothesis.status is KnowledgeStatus.HYPOTHESIS
    assert store.get_concept(capability).status is KnowledgeStatus.HYPOTHESIS
    result = _result(experiment_id="exp_wall_x", hypothesis_id=hypothesis.hypothesis_id, capability=capability)
    store.store_experiment_result(result)
    assert store.get_hypothesis(hypothesis.hypothesis_id).status is KnowledgeStatus.EXPERIMENTED
    assert store.get_concept(capability).status is KnowledgeStatus.EXPERIMENTED
    assert [item.experiment_id for item in store.get_hypothesis_experiments(hypothesis.hypothesis_id)] == ["exp_wall_x"]
    assert [item.hypothesis_id for item in store.get_concept_hypotheses(capability)] == ["hyp_wall_x"]
    verified = store.promote_to_verified(capability, result)
    assert verified.status is KnowledgeStatus.VERIFIED
    assert store.get_hypothesis(hypothesis.hypothesis_id).status is KnowledgeStatus.VERIFIED
    assert store.get_capability(capability).roundtrip_verified is True


def test_promotion_rejects_wrong_capability_or_hypothesis_links(tmp_path: Path) -> None:
    store = _store(tmp_path)
    capability = "room.boundary.external_wall.x_m"
    store.store_hypothesis(Hypothesis(hypothesis_id="hyp_wall", target_capability=capability, semantic_guess="wall x"))
    result = _result(experiment_id="exp_wall", hypothesis_id="hyp_wall", capability=capability)
    store.store_experiment_result(result)
    with pytest.raises(ValueError, match="target capability"):
        store.promote_to_verified("room.area_m2", result)
    mismatched = _result(experiment_id="exp_wrong", hypothesis_id="hyp_wall", capability="room.area_m2")
    with pytest.raises(ValueError, match="does not match"):
        store.store_experiment_result(mismatched)


def test_deterministic_negative_readback_rejects_hypothesis(tmp_path: Path) -> None:
    store = _store(tmp_path)
    capability = "room.boundary.external_wall.x_m"
    store.store_hypothesis(Hypothesis(hypothesis_id="hyp_negative", target_capability=capability, semantic_guess="wall x"))
    result = _result(experiment_id="exp_negative", hypothesis_id="hyp_negative", capability=capability, success=False, actual=2.0)
    store.store_experiment_result(result)
    assert store.get_hypothesis("hyp_negative").status is KnowledgeStatus.REJECTED
    assert store.get_concept(capability).status is KnowledgeStatus.REJECTED
