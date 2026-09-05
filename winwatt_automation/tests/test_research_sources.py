from __future__ import annotations

from pathlib import Path

import pytest

from winwatt_automation.knowledge.models import EvidenceRef, ExperimentResult, Hypothesis, KnowledgeStatus
from winwatt_automation.knowledge.store import KnowledgeStore
from winwatt_automation.research.manual_index import ManualIndex
from winwatt_automation.research.models import ResearchEvidence


def _store(tmp_path: Path) -> KnowledgeStore:
    return KnowledgeStore(path=tmp_path / "knowledge.json", capability_path=tmp_path / "no_capabilities.json")


def test_manual_index_is_searchable_and_preserves_page_provenance(tmp_path: Path) -> None:
    index = ManualIndex(tmp_path / "manual.pdf", tmp_path / "manual_index.json")
    source = index.build_from_pages([
        "Bevezetés\nEz csak egy rövid leírás.",
        "Határoló szerkezetek\nKülső fal esetén a felület adatai megadhatók.",
    ])

    results = index.search("külső fal")

    assert source.type == "manual"
    assert results[0]["page"] == 2
    assert results[0]["source_id"] == source.id
    assert "Külső fal" in results[0]["excerpt"]


def test_manual_evidence_stays_hypothesis_and_cannot_promote(tmp_path: Path) -> None:
    store = _store(tmp_path)
    index = ManualIndex(tmp_path / "manual.pdf", tmp_path / "manual_index.json")
    source = index.build_from_pages(["Külső fal\nA szerkezet felületéhez további adat tartozhat."])
    store.store_research_source(source)
    concept = "room.boundary.external_wall.solar_absorptance"
    hypothesis = store.store_hypothesis(Hypothesis(
        hypothesis_id="hyp_wall_absorptance", target_capability=concept,
        semantic_guess="A manual szerint a külső falhoz abszorpciós adat tartozhat.", confidence=0.72,
    ))
    evidence = store.store_research_evidence(ResearchEvidence(
        evidence_id="manual_wall_absorptance", source_id=source.id, page=1,
        section="Külső fal", excerpt="A szerkezet felületéhez további adat tartozhat.",
        claim="A manual külső falhoz felületi paramétert említ.", related_concepts=[concept], confidence=0.72,
    ))
    linked = store.attach_research_evidence(hypothesis.hypothesis_id, evidence.evidence_id)

    assert linked.status is KnowledgeStatus.HYPOTHESIS
    assert linked.research_evidence_ids == [evidence.evidence_id]
    assert store.get_concept(concept).status is KnowledgeStatus.HYPOTHESIS
    assert store.get_concept_research_evidence(concept)[0].deterministic is False

    manual_only_result = ExperimentResult(
        experiment_id="manual_is_not_an_experiment", hypothesis_id=hypothesis.hypothesis_id,
        target_capability=concept, success=True, roundtrip_verified=True,
        evidence=[EvidenceRef(kind="research_manual", deterministic=False, description="manual claim")],
    )
    store.store_experiment_result(manual_only_result)
    with pytest.raises(ValueError, match="deterministic"):
        store.promote_to_verified(concept, manual_only_result)


def test_research_evidence_must_match_linked_hypothesis_capability(tmp_path: Path) -> None:
    store = _store(tmp_path)
    index = ManualIndex(tmp_path / "manual.pdf", tmp_path / "manual_index.json")
    source = index.build_from_pages(["Külső fal"])
    store.store_research_source(source)
    store.store_hypothesis(Hypothesis(hypothesis_id="hyp", target_capability="room.boundary.external_wall.u", semantic_guess="guess"))
    evidence = store.store_research_evidence(ResearchEvidence(
        evidence_id="other", source_id=source.id, page=1, excerpt="Külső fal", claim="claim",
        related_concepts=["room.area_m2"],
    ))
    with pytest.raises(ValueError, match="not related"):
        store.attach_research_evidence("hyp", evidence.evidence_id)
