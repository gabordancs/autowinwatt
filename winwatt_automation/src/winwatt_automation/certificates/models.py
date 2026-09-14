from __future__ import annotations
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field
class CertificateBuildInput(BaseModel):
    certificate_pdf: Path
    output_dir: Path
    catalog_xml: Path
    xml_template: Path | None = None
    allow_llm: bool = False
    execute_winwatt: bool = False
    output_wwp: Path | None = None
class Evidence(BaseModel):
    page: int
    excerpt: str
    confidence: float = Field(ge=0, le=1)
class ExtractedValue(BaseModel):
    key: str
    value: str | float | int
    evidence: Evidence
class MaterialCandidate(BaseModel):
    name: str
    material_id: str | None = None
    path: str | None = None
    lambda_wmk: float | None = None
    density_kgm3: float | None = None
    heat_capacity_kjkgk: float | None = None
class MaterialDecision(BaseModel):
    source_name: str
    status: Literal["catalog", "review", "special", "new"]
    candidate: MaterialCandidate | None = None
    reason: str
    confidence: float = Field(default=0.0, ge=0, le=1)
    decision_mode: Literal["catalog_match", "manual_review", "special"] = "manual_review"
class CertificateBuildResult(BaseModel):
    output_dir: Path
    deterministic_values: list[ExtractedValue]
    material_decisions: list[MaterialDecision]
    unresolved: list[str]
    llm_used: bool = False
    xml_path: Path | None = None
    wwp_path: Path | None = None
