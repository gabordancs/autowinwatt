"""Deterministic thermal-boundary classification from explicit zone adjacency."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


ZoneType = Literal["heated", "unheated", "exterior", "ground", "unknown"]

@dataclass(frozen=True)
class BoundaryCandidate:
    id: str
    room_id: str
    adjacent_zone: ZoneType
    structure_id: str | None
    x_m: float | None
    y_m: float | None
    area_m2: float | None
    evidence_ids: tuple[str,...]=()
    confidence: float=0.0
    status: str="pending"
    classification: str="unclassified"

    def to_dict(self) -> dict: return asdict(self)


def classify_boundary(candidate: BoundaryCandidate, *, tolerance_m2: float=0.01) -> BoundaryCandidate:
    if candidate.adjacent_zone=="unknown":
        return BoundaryCandidate(**{**asdict(candidate),"status":"unresolved","classification":"unknown_adjacency"})
    if candidate.adjacent_zone=="heated":
        return BoundaryCandidate(**{**asdict(candidate),"status":"accepted","classification":"internal"})
    if candidate.x_m is None or candidate.y_m is None or candidate.area_m2 is None:
        return BoundaryCandidate(**{**asdict(candidate),"status":"unresolved","classification":"missing_xy_area"})
    if abs(candidate.x_m*candidate.y_m-candidate.area_m2)>tolerance_m2:
        return BoundaryCandidate(**{**asdict(candidate),"status":"unresolved","classification":"xy_area_conflict"})
    kind={"exterior":"external_air","ground":"ground_contact","unheated":"unheated_adjacency"}[candidate.adjacent_zone]
    return BoundaryCandidate(**{**asdict(candidate),"status":"accepted","classification":kind,"confidence":max(candidate.confidence,0.8)})
