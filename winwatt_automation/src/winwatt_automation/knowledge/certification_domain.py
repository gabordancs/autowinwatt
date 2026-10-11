"""Versioned, source-backed knowledge for Hungarian energy certification."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST_PATH = (
    PROJECT_ROOT / "data" / "knowledge" / "certification_source_manifest.json"
)
DEFAULT_KNOWLEDGE_PATH = (
    PROJECT_ROOT / "data" / "knowledge" / "certification_domain_knowledge.json"
)


class CertificationSource(BaseModel):
    source_id: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    media_type: str = Field(min_length=1)
    role: Literal["authoritative", "method", "reference", "catalog", "example", "guide", "support"]
    metadata: dict[str, object] = Field(default_factory=dict)


class CertificationSourceManifest(BaseModel):
    schema_version: int = 1
    manifest_id: str = Field(min_length=1)
    source_root: str = Field(min_length=1)
    sources: list[CertificationSource] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_source_ids(self) -> "CertificationSourceManifest":
        ids = [source.source_id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate source_id in certification source manifest")
        return self

    def source(self, source_id: str) -> CertificationSource:
        for source in self.sources:
            if source.source_id == source_id:
                return source
        raise KeyError(source_id)


class SourceCitation(BaseModel):
    source_id: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    assertion: str = Field(min_length=1)


class DomainClaim(BaseModel):
    claim_id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    status: Literal["authoritative", "verified", "observed", "inferred", "needs_review"]
    claim: str = Field(min_length=1)
    citations: list[SourceCitation] = Field(min_length=1)


class WorkflowStage(BaseModel):
    stage_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    required_inputs: list[str] = Field(default_factory=list)
    completion_evidence: list[str] = Field(min_length=1)
    citations: list[SourceCitation] = Field(default_factory=list)


class ResponsibilityBoundary(BaseModel):
    boundary_id: str = Field(min_length=1)
    owner: Literal["ai", "deterministic_code", "human_professional"]
    responsibility: str = Field(min_length=1)
    must_not_claim: list[str] = Field(default_factory=list)


class KnowledgeCheck(BaseModel):
    check_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_points: list[str] = Field(min_length=1)
    required_source_ids: list[str] = Field(min_length=1)


class CertificationDomainKnowledge(BaseModel):
    schema_version: int = 1
    knowledge_id: str = Field(min_length=1)
    source_manifest_id: str = Field(min_length=1)
    source_priority: list[str] = Field(min_length=1)
    claims: list[DomainClaim] = Field(min_length=1)
    workflow: list[WorkflowStage] = Field(min_length=1)
    responsibility_boundaries: list[ResponsibilityBoundary] = Field(min_length=1)
    knowledge_checks: list[KnowledgeCheck] = Field(min_length=1)


def load_source_manifest(
    path: Path = DEFAULT_MANIFEST_PATH,
) -> CertificationSourceManifest:
    return CertificationSourceManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_domain_knowledge(
    path: Path = DEFAULT_KNOWLEDGE_PATH,
) -> CertificationDomainKnowledge:
    return CertificationDomainKnowledge.model_validate_json(path.read_text(encoding="utf-8"))


def audit_domain_knowledge(
    knowledge: CertificationDomainKnowledge,
    manifest: CertificationSourceManifest,
    repository_root: Path = PROJECT_ROOT.parent,
) -> list[str]:
    """Return stable audit errors for stale files and invalid source references."""
    errors: list[str] = []
    if knowledge.source_manifest_id != manifest.manifest_id:
        errors.append(
            f"manifest_id mismatch: {knowledge.source_manifest_id} != {manifest.manifest_id}"
        )

    source_by_id = {source.source_id: source for source in manifest.sources}
    referenced_ids: set[str] = set()
    for claim in knowledge.claims:
        referenced_ids.update(citation.source_id for citation in claim.citations)
    for stage in knowledge.workflow:
        referenced_ids.update(citation.source_id for citation in stage.citations)
    for check in knowledge.knowledge_checks:
        referenced_ids.update(check.required_source_ids)

    for source_id in sorted(referenced_ids):
        if source_id not in source_by_id:
            errors.append(f"unknown source_id: {source_id}")

    source_root = (repository_root / manifest.source_root).resolve()
    for source in manifest.sources:
        path = source_root / Path(source.relative_path)
        if not path.is_file():
            errors.append(f"missing source file: {source.source_id}: {path}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != source.sha256:
            errors.append(f"source hash mismatch: {source.source_id}")
        if path.stat().st_size != source.size_bytes:
            errors.append(f"source size mismatch: {source.source_id}")
    return errors


def knowledge_summary_json(knowledge: CertificationDomainKnowledge) -> str:
    return json.dumps(knowledge.model_dump(mode="json"), ensure_ascii=False, indent=2)
