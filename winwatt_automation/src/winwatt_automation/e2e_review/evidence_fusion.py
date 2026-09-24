"""Explainable room stamp ↔ topology-cell matching without an LLM."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import hypot
from typing import Iterable


Point=tuple[float,float]

@dataclass(frozen=True)
class RoomStamp:
    id: str
    name: str
    declared_area_m2: float | None
    bbox: tuple[float,float,float,float] | None
    evidence_ids: tuple[str,...]=()

@dataclass(frozen=True)
class TopologyCell:
    id: str
    polygon: tuple[Point,...]
    area_m2: float | None
    evidence_ids: tuple[str,...]=()

@dataclass(frozen=True)
class CandidateMatch:
    room_stamp_id: str
    cell_id: str | None
    score: float
    spatial_score: float
    area_residual_percent: float | None
    topology_score: float
    evidence_ids: tuple[str,...]
    status: str
    reason: str

    def to_dict(self) -> dict: return asdict(self)

def _centroid(points: tuple[Point,...]) -> Point:
    return (sum(p[0] for p in points)/len(points),sum(p[1] for p in points)/len(points))

def _inside(point: Point, polygon: tuple[Point,...]) -> bool:
    x,y=point; inside=False
    for (x1,y1),(x2,y2) in zip(polygon,polygon[1:]+polygon[:1]):
        if (y1>y)!=(y2>y) and x < (x2-x1)*(y-y1)/(y2-y1)+x1: inside=not inside
    return inside

def match_room_stamp(stamp: RoomStamp, cells: Iterable[TopologyCell], *, accept_score: float=0.8) -> CandidateMatch:
    if stamp.bbox is None:
        return CandidateMatch(stamp.id,None,0,0,None,0,stamp.evidence_ids,"unresolved","missing room-stamp bbox")
    x0,y0,x1,y1=stamp.bbox; center=((x0+x1)/2,(y0+y1)/2); diagonal=max(hypot(x1-x0,y1-y0),1.0)
    best: CandidateMatch | None=None
    for cell in cells:
        if len(cell.polygon)<3: continue
        centroid=_centroid(cell.polygon); distance=hypot(center[0]-centroid[0],center[1]-centroid[1])
        contained=_inside(center,cell.polygon)
        spatial=1.0 if contained else max(0.0,1-distance/(diagonal*4))
        if stamp.declared_area_m2 and cell.area_m2 is not None:
            residual=abs(cell.area_m2-stamp.declared_area_m2)/stamp.declared_area_m2*100
            area_score=max(0.0,1-residual/10)
        else:
            residual=None; area_score=0.5
        topology=1.0 if contained else 0.5
        score=round(0.5*spatial+0.35*area_score+0.15*topology,4)
        match=CandidateMatch(stamp.id,cell.id,score,round(spatial,4),None if residual is None else round(residual,4),topology,tuple(sorted(set(stamp.evidence_ids+cell.evidence_ids))),"accepted" if score>=accept_score else "pending","contained room stamp and area consistency" if contained else "nearest topology cell; needs review")
        if best is None or match.score>best.score: best=match
    return best or CandidateMatch(stamp.id,None,0,0,None,0,stamp.evidence_ids,"unresolved","no valid topology cells")
