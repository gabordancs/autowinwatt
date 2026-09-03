from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    EvidenceRef,
    ExperimentResult,
    Hypothesis,
    KnowledgeStatus,
    SemanticCapability,
    SemanticConcept,
)


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
            return {key: data.get(key, {}) for key in ("concepts", "capabilities", "hypotheses", "experiments")}
        return {"concepts": {}, "capabilities": {}, "hypotheses": {}, "experiments": {}}

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
