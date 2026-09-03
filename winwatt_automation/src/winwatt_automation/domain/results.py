from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    kind: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class OperationResult(BaseModel):
    success: bool
    requested: int
    completed: int
    verified: bool
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
