from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .models import (
    EvidenceRef,
    ExperimentResult,
    Hypothesis,
    KnowledgeStatus,
    SemanticCapability,
    SemanticConcept,
)
if TYPE_CHECKING:
    from winwatt_automation.discovery.models import (
        CandidateCapability, DiscoveryEvidence, StructureKindCandidate, StructureReferenceCandidate,
    )
    from winwatt_automation.research.models import ResearchEvidence, ResearchSource


class KnowledgeStore:
    """Small local store; verified knowledge has a deterministic evidence gate."""

    def __init__(self, path: Path | None = None, capability_path: Path | None = None) -> None:
        package_root = Path(__file__).resolve().parents[3]
        self.path = path or package_root / "data" / "knowledge" / "knowledge_store.json"
        self.capability_path = capability_path or package_root / "data" / "capabilities" / "room_capabilities.json"
        self._data = self._load()
        if not self._data["capabilities"] and self.capability_path.is_file():
            self._import_room_capabilities()

    def _load(self) -> dict[str, Any]:
        if self.path.is_file():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {key: data.get(key, {}) for key in (
                "concepts", "capabilities", "hypotheses", "experiments", "sources", "research_evidence",
                "candidate_capabilities", "discovery_evidence",
                "structure_reference_candidates", "structure_kind_candidates",
            )}
        return {"concepts": {}, "capabilities": {}, "hypotheses": {}, "experiments": {}, "sources": {}, "research_evidence": {}, "candidate_capabilities": {}, "discovery_evidence": {}, "structure_reference_candidates": {}, "structure_kind_candidates": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def _concept_metadata(capability: str) -> tuple[str, str, str | None]:
        known = {
            "room.name": ("Room", "string", None),
            "room.area_m2": ("Room", "float", "m2"),
            "room.height_m": ("Room", "float", "m"),
            "room.temperature_c": ("Room", "float", "C"),
            "room.boundary.external_wall.x_m": ("RoomBoundary", "float", "m"),
            "room.boundary.structure_reference.assign_existing": ("RoomBoundary", "string", None),
        }
        return known.get(capability, ("Unknown", "unknown", None))

    def _import_room_capabilities(self) -> None:
        raw = json.loads(self.capability_path.read_text(encoding="utf-8"))
        for key, value in raw.items():
            verified = bool(value.get("roundtrip_verified")) and value.get("ui_read") == "verified" and value.get("ui_write") == "verified"
            evidence = EvidenceRef(
                kind="legacy_capability_registry",
                path=str(value.get("evidence", "")),
                description="Imported from the existing room capability registry",
                deterministic=verified,
                data={"source": "room_capabilities.json", "roundtrip_verified": value.get("roundtrip_verified", False)},
            )
            capability = SemanticCapability(
                capability=key,
                preferred_transport=value.get("preferred"),
                ui_read=value.get("ui_read", "unknown"),
                ui_write=value.get("ui_write", "unknown"),
                roundtrip_verified=bool(value.get("roundtrip_verified")),
                status=KnowledgeStatus.VERIFIED if verified else KnowledgeStatus.EXPERIMENTED,
                evidence=[evidence],
            )
            entity, data_type, unit = self._concept_metadata(key)
            concept = SemanticConcept(
                concept=key,
                entity=entity,
                data_type=data_type,
                unit=unit,
                status=KnowledgeStatus.VERIFIED if verified else KnowledgeStatus.EXPERIMENTED,
                confidence=1.0 if verified else 0.5,
                evidence=[evidence],
            )
            self._data["capabilities"][key] = capability.model_dump(mode="json")
            self._data["concepts"][key] = concept.model_dump(mode="json")
        self._save()

    def search_concepts(self, query: str) -> list[SemanticConcept]:
        needle = query.casefold()
        return [item for key, value in self._data["concepts"].items() if needle in key.casefold() or needle in str(value).casefold() for item in [SemanticConcept.model_validate(value)]]

    def get_concept(self, concept: str) -> SemanticConcept | None:
        value = self._data["concepts"].get(concept)
        return SemanticConcept.model_validate(value) if value else None

    def get_capability(self, capability: str) -> SemanticCapability | None:
        value = self._data["capabilities"].get(capability)
        return SemanticCapability.model_validate(value) if value else None

    def get_hypothesis(self, hypothesis_id: str) -> Hypothesis | None:
        value = self._data["hypotheses"].get(hypothesis_id)
        return Hypothesis.model_validate(value) if value else None

    def get_experiment(self, experiment_id: str) -> ExperimentResult | None:
        value = self._data["experiments"].get(experiment_id)
        return ExperimentResult.model_validate(value) if value else None

    def get_hypothesis_experiments(self, hypothesis_id: str) -> list[ExperimentResult]:
        hypothesis = self.get_hypothesis(hypothesis_id)
        if hypothesis is None:
            return []
        return [self.get_experiment(item) for item in hypothesis.experiment_ids if self.get_experiment(item) is not None]

    def get_concept_hypotheses(self, concept: str) -> list[Hypothesis]:
        return [item for item in (Hypothesis.model_validate(value) for value in self._data["hypotheses"].values()) if item.target_capability == concept]

    def store_research_source(self, source: ResearchSource) -> ResearchSource:
        """Store source metadata; source text remains in its regenerable local index."""
        self._data["sources"][source.id] = source.model_dump(mode="json")
        self._save()
        return source

    def get_research_source(self, source_id: str) -> ResearchSource | None:
        from winwatt_automation.research.models import ResearchSource
        value = self._data["sources"].get(source_id)
        return ResearchSource.model_validate(value) if value else None

    def list_research_sources(self) -> list[ResearchSource]:
        from winwatt_automation.research.models import ResearchSource
        return [ResearchSource.model_validate(value) for value in self._data["sources"].values()]

    def store_research_evidence(self, evidence: ResearchEvidence) -> ResearchEvidence:
        if self.get_research_source(evidence.source_id) is None:
            raise KeyError(f"unknown research source: {evidence.source_id}")
        self._data["research_evidence"][evidence.evidence_id] = evidence.model_dump(mode="json")
        self._save()
        return evidence

    def get_research_evidence(self, evidence_id: str) -> ResearchEvidence | None:
        from winwatt_automation.research.models import ResearchEvidence
        value = self._data["research_evidence"].get(evidence_id)
        return ResearchEvidence.model_validate(value) if value else None

    def get_concept_research_evidence(self, concept: str) -> list[ResearchEvidence]:
        from winwatt_automation.research.models import ResearchEvidence
        return [item for item in (ResearchEvidence.model_validate(value) for value in self._data["research_evidence"].values()) if concept in item.related_concepts]

    def attach_research_evidence(self, hypothesis_id: str, evidence_id: str) -> Hypothesis:
        """Link non-deterministic manual evidence without changing verification status."""
        hypothesis = self.get_hypothesis(hypothesis_id)
        evidence = self.get_research_evidence(evidence_id)
        if hypothesis is None:
            raise KeyError(f"unknown hypothesis: {hypothesis_id}")
        if evidence is None:
            raise KeyError(f"unknown research evidence: {evidence_id}")
        if hypothesis.target_capability not in evidence.related_concepts:
            raise ValueError("research evidence is not related to the hypothesis capability")
        if evidence_id not in hypothesis.research_evidence_ids:
            hypothesis.research_evidence_ids.append(evidence_id)
            hypothesis.evidence.append(evidence.as_evidence_ref())
            self._data["hypotheses"][hypothesis_id] = hypothesis.model_dump(mode="json")
            concept = self.get_concept(hypothesis.target_capability)
            if concept is not None:
                concept.evidence.append(evidence.as_evidence_ref())
                self._data["concepts"][concept.concept] = concept.model_dump(mode="json")
            capability = self.get_capability(hypothesis.target_capability)
            if capability is not None:
                capability.evidence.append(evidence.as_evidence_ref())
                self._data["capabilities"][capability.capability] = capability.model_dump(mode="json")
            self._save()
        return hypothesis

    def store_discovery_evidence(self, evidence: DiscoveryEvidence) -> DiscoveryEvidence:
        if evidence.deterministic:
            raise ValueError("discovery evidence can never be deterministic verification")
        self._data["discovery_evidence"][evidence.evidence_id] = evidence.model_dump(mode="json")
        self._save()
        return evidence

    def store_candidate_capability(self, candidate: CandidateCapability) -> CandidateCapability:
        if candidate.status is not KnowledgeStatus.HYPOTHESIS:
            raise ValueError("discovery candidates must remain hypotheses")
        self._data["candidate_capabilities"][candidate.candidate_id] = candidate.model_dump(mode="json")
        self._save()
        return candidate

    def list_candidate_capabilities(self, semantic_scope: str | None = None) -> list[CandidateCapability]:
        from winwatt_automation.discovery.models import CandidateCapability
        items = [CandidateCapability.model_validate(value) for value in self._data["candidate_capabilities"].values()]
        return [item for item in items if semantic_scope is None or item.proposed_concept.startswith(semantic_scope)]

    def store_structure_reference_candidate(self, candidate: StructureReferenceCandidate) -> StructureReferenceCandidate:
        if candidate.status is not KnowledgeStatus.HYPOTHESIS:
            raise ValueError("structure reference discovery candidates must remain hypotheses")
        self._data["structure_reference_candidates"][candidate.reference_id] = candidate.model_dump(mode="json")
        self._save()
        return candidate

    def store_structure_kind_candidate(self, candidate: StructureKindCandidate) -> StructureKindCandidate:
        if candidate.status is not KnowledgeStatus.HYPOTHESIS:
            raise ValueError("structure kind discovery candidates must remain hypotheses")
        self._data["structure_kind_candidates"][candidate.proposed_kind] = candidate.model_dump(mode="json")
        self._save()
        return candidate

    def list_structure_reference_candidates(self) -> list[StructureReferenceCandidate]:
        from winwatt_automation.discovery.models import StructureReferenceCandidate
        return [StructureReferenceCandidate.model_validate(value) for value in self._data["structure_reference_candidates"].values()]

    def list_structure_kind_candidates(self) -> list[StructureKindCandidate]:
        from winwatt_automation.discovery.models import StructureKindCandidate
        return [StructureKindCandidate.model_validate(value) for value in self._data["structure_kind_candidates"].values()]

    def get_state_evidence(self, concept: str) -> list[EvidenceRef]:
        item = self.get_concept(concept)
        return [] if item is None else [evidence for evidence in item.evidence if evidence.kind in {"state", "ui_readback", "legacy_capability_registry"}]

    def get_transition_evidence(self, concept: str) -> list[EvidenceRef]:
        item = self.get_concept(concept)
        return [] if item is None else [evidence for evidence in item.evidence if evidence.kind in {"transition", "verification", "save_reopen"}]

    def store_hypothesis(self, hypothesis: Hypothesis) -> Hypothesis:
        if hypothesis.status is not KnowledgeStatus.HYPOTHESIS:
            raise ValueError("new hypotheses must start in hypothesis status")
        if hypothesis.hypothesis_id in self._data["hypotheses"]:
            raise ValueError(f"hypothesis already exists: {hypothesis.hypothesis_id}")
        entity, data_type, unit = self._concept_metadata(hypothesis.target_capability)
        if self.get_concept(hypothesis.target_capability) is None:
            self._data["concepts"][hypothesis.target_capability] = SemanticConcept(
                concept=hypothesis.target_capability, entity=entity, data_type=data_type, unit=unit,
                status=KnowledgeStatus.HYPOTHESIS, confidence=hypothesis.confidence,
                evidence=list(hypothesis.evidence),
            ).model_dump(mode="json")
            self._data["capabilities"][hypothesis.target_capability] = SemanticCapability(
                capability=hypothesis.target_capability, status=KnowledgeStatus.HYPOTHESIS,
                evidence=list(hypothesis.evidence),
            ).model_dump(mode="json")
        self._data["hypotheses"][hypothesis.hypothesis_id] = hypothesis.model_dump(mode="json")
        self._save()
        return hypothesis

    def store_experiment_result(self, result: ExperimentResult) -> ExperimentResult:
        hypothesis = self.get_hypothesis(result.hypothesis_id)
        if hypothesis is None:
            raise KeyError(f"unknown hypothesis: {result.hypothesis_id}")
        if hypothesis.target_capability != result.target_capability:
            raise ValueError("experiment target capability does not match its hypothesis")
        self._data["experiments"][result.experiment_id] = result.model_dump(mode="json")
        if result.experiment_id not in hypothesis.experiment_ids:
            hypothesis.experiment_ids.append(result.experiment_id)
        link = EvidenceRef(kind="experiment", description="Experiment linked to hypothesis", data={"experiment_id": result.experiment_id, "hypothesis_id": result.hypothesis_id})
        hypothesis.evidence.append(link)
        has_deterministic_negative = any(
            item.kind == "verification" and item.deterministic and item.data.get("actual") is not None
            for item in result.evidence
        )
        hypothesis.status = KnowledgeStatus.EXPERIMENTED if result.success else (KnowledgeStatus.REJECTED if has_deterministic_negative else KnowledgeStatus.EXPERIMENTED)
        self._data["hypotheses"][hypothesis.hypothesis_id] = hypothesis.model_dump(mode="json")
        concept = self.get_concept(result.target_capability)
        capability = self.get_capability(result.target_capability)
        if concept is not None and concept.status is not KnowledgeStatus.VERIFIED:
            concept.status = hypothesis.status
            concept.evidence.append(link)
            self._data["concepts"][concept.concept] = concept.model_dump(mode="json")
        if capability is not None and capability.status is not KnowledgeStatus.VERIFIED:
            capability.status = hypothesis.status
            capability.evidence.append(link)
            self._data["capabilities"][capability.capability] = capability.model_dump(mode="json")
        self._save()
        return result

    def promote_to_verified(self, concept: str, result: ExperimentResult) -> SemanticConcept:
        if result.target_capability != concept:
            raise ValueError("experiment target capability does not match the promoted concept")
        hypothesis = self.get_hypothesis(result.hypothesis_id)
        if hypothesis is None or hypothesis.target_capability != concept:
            raise ValueError("experiment does not belong to a hypothesis for this concept")
        stored = self.get_experiment(result.experiment_id)
        if stored is None or stored.hypothesis_id != result.hypothesis_id or stored.target_capability != concept:
            raise ValueError("experiment result must be stored and linked before promotion")
        if not (result.success and result.roundtrip_verified):
            raise ValueError("verified promotion requires a successful save/reopen verification")
        deterministic = [item for item in result.evidence if item.deterministic and item.kind == "verification"]
        if not deterministic:
            raise ValueError("verified promotion requires deterministic verification evidence")
        current = self.get_concept(concept)
        if current is None:
            raise KeyError(f"Unknown semantic concept: {concept}")
        current.status = KnowledgeStatus.VERIFIED
        current.confidence = 1.0
        current.evidence.extend(deterministic)
        self._data["concepts"][concept] = current.model_dump(mode="json")
        hypothesis.status = KnowledgeStatus.VERIFIED
        hypothesis.evidence.extend(deterministic)
        self._data["hypotheses"][hypothesis.hypothesis_id] = hypothesis.model_dump(mode="json")
        capability = self.get_capability(concept)
        if capability is not None:
            capability.status = KnowledgeStatus.VERIFIED
            capability.roundtrip_verified = True
            capability.evidence.extend(deterministic)
            self._data["capabilities"][concept] = capability.model_dump(mode="json")
        self._save()
        return current
