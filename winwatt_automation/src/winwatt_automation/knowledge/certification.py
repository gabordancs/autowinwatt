"""Typed access to the curated WinWatt certification knowledge package."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PATH = PROJECT_ROOT / "data" / "knowledge" / "certification_knowledge.json"


class KnowledgeEvidence(BaseModel):
    path: str = Field(min_length=1)
    assertion: str = Field(min_length=1)


class CertificationFact(BaseModel):
    fact_id: str = Field(min_length=1)
    status: str = Field(pattern=r"^(observed|verified)$")
    claim: str = Field(min_length=1)
    evidence: list[KnowledgeEvidence] = Field(min_length=1)
    tool_ids: list[str] = Field(default_factory=list)


class CertificationWorkflow(BaseModel):
    workflow_id: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    tool_ids: list[str] = Field(default_factory=list)
    entrypoint: str = Field(min_length=1)
    success_gate: list[str] = Field(min_length=1)


class CertificationKnowledge(BaseModel):
    schema_version: int = 1
    knowledge_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    runtime_invariants: list[str] = Field(min_length=1)
    promotion_rule: list[str] = Field(min_length=1)
    facts: list[CertificationFact] = Field(min_length=1)
    workflows: list[CertificationWorkflow] = Field(min_length=1)
    open_gaps: list[str] = Field(default_factory=list)

    def fact(self, fact_id: str) -> CertificationFact | None:
        return next((item for item in self.facts if item.fact_id == fact_id), None)


def load_certification_knowledge(path: Path = DEFAULT_PATH) -> CertificationKnowledge:
    return CertificationKnowledge.model_validate_json(path.read_text(encoding="utf-8"))


def missing_evidence_paths(
    knowledge: CertificationKnowledge, project_root: Path = PROJECT_ROOT,
) -> list[str]:
    return sorted({
        evidence.path
        for fact in knowledge.facts
        for evidence in fact.evidence
        if not (project_root / evidence.path).is_file()
    })


def as_compact_json(knowledge: CertificationKnowledge) -> str:
    return json.dumps(knowledge.model_dump(mode="json"), ensure_ascii=False, indent=2)
