"""Stable, UI-independent review domain model.

The model intentionally retains the raw machine value on every transition.
It is shared by the spreadsheet adapter, local SQLite review queue and GUI.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class ReviewStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class DocumentEvidence:
    source_pdf: str | None
    page: int | None = None
    sheet_no: str | None = None
    evidence_bbox: tuple[float, float, float, float] | None = None
    context_bbox: tuple[float, float, float, float] | None = None
    context_margin: float = 36.0
    extraction_method: str = "spreadsheet_import"
    confidence: float = 0.0

    @property
    def location_status(self) -> str:
        return "located" if self.evidence_bbox else "missing_evidence_location"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("evidence_bbox", "context_bbox"):
            if value[key] is not None:
                value[key] = list(value[key])
        value["location_status"] = self.location_status
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DocumentEvidence":
        value = dict(value)
        value.pop("location_status", None)
        for key in ("evidence_bbox", "context_bbox"):
            if value.get(key) is not None:
                value[key] = tuple(float(item) for item in value[key])
        return cls(**value)


@dataclass(frozen=True)
class ReviewCandidate:
    candidate_id: str
    entity_type: str
    entity_id: str
    field_name: str
    machine_value: str | float | int | None
    reviewed_value: str | float | int | None = None
    unit: str | None = None
    evidence: DocumentEvidence = field(default_factory=lambda: DocumentEvidence(None))
    status: ReviewStatus = ReviewStatus.PENDING
    reviewer: str | None = None
    reviewed_at: str | None = None
    note: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None
    source_columns: dict[str, Any] = field(default_factory=dict)

    @property
    def canonical_value(self) -> str | float | int | None:
        return self.reviewed_value if self.status in {ReviewStatus.ACCEPTED, ReviewStatus.EDITED} else None

    def transition(
        self,
        status: ReviewStatus,
        *,
        reviewer: str,
        reviewed_value: str | float | int | None = None,
        note: str | None = None,
    ) -> "ReviewCandidate":
        if status is ReviewStatus.EDITED and reviewed_value is None:
            raise ValueError("Edited review requires reviewed_value")
        if status is ReviewStatus.ACCEPTED:
            reviewed_value = self.machine_value if reviewed_value is None else reviewed_value
        if status not in {ReviewStatus.ACCEPTED, ReviewStatus.EDITED}:
            reviewed_value = None
        payload = self.to_dict()
        payload["evidence"] = self.evidence
        return ReviewCandidate(
            **{
                **payload,
                "status": status,
                "reviewed_value": reviewed_value,
                "reviewer": reviewer,
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "note": note if note is not None else self.note,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        value["evidence"] = self.evidence.to_dict()
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReviewCandidate":
        value = dict(value)
        value["status"] = ReviewStatus(value.get("status", ReviewStatus.PENDING))
        value["evidence"] = DocumentEvidence.from_dict(value.get("evidence") or {})
        return cls(**value)


def numeric_value(value: object, unit: str | None) -> float | None:
    """Parse only physical/numeric fields; free text intentionally stays free text."""
    if unit not in {"m", "m²", "m³", "cm", "mm", "W/m²K", "°", "%"}:
        return None
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).strip().replace(" ", "").replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"{value!r} is not a valid {unit} value") from exc
