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

    def get_state_evidence(self, concept: str) -> list[EvidenceRef]:
        item = self.get_concept(concept)
        return [] if item is None else [evidence for evidence in item.evidence if evidence.kind in {"state", "ui_readback", "legacy_capability_registry"}]

    def get_transition_evidence(self, concept: str) -> list[EvidenceRef]:
        item = self.get_concept(concept)
        return [] if item is None else [evidence for evidence in item.evidence if evidence.kind in {"transition", "verification", "save_reopen"}]

    def store_hypothesis(self, hypothesis: Hypothesis) -> Hypothesis:
        self._data["hypotheses"][hypothesis.hypothesis_id] = hypothesis.model_dump(mode="json")
        self._save()
        return hypothesis

    def store_experiment_result(self, result: ExperimentResult) -> ExperimentResult:
        self._data["experiments"][result.experiment_id] = result.model_dump(mode="json")
        self._save()
        return result

    def promote_to_verified(self, concept: str, result: ExperimentResult) -> SemanticConcept:
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
        capability = self.get_capability(concept)
        if capability is not None:
            capability.status = KnowledgeStatus.VERIFIED
            capability.roundtrip_verified = True
            capability.evidence.extend(deterministic)
            self._data["capabilities"][concept] = capability.model_dump(mode="json")
        self._save()
        return current
