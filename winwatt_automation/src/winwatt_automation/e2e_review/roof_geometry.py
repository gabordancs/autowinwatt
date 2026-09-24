"""3D roof-boundary area from an explicitly evidenced roof plane."""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

Point3=tuple[float,float,float]

@dataclass(frozen=True)
class RoofBoundaryCandidate:
    room_id: str
    plane_id: str
    polygon3d: tuple[Point3,...]
    opening_area_m2: float=0.0
    evidence_ids: tuple[str,...]=()
    status: str="pending"

def _cross(left: Point3,right: Point3) -> Point3:
    return (left[1]*right[2]-left[2]*right[1],left[2]*right[0]-left[0]*right[2],left[0]*right[1]-left[1]*right[0])

def _sub(left: Point3,right: Point3) -> Point3: return (left[0]-right[0],left[1]-right[1],left[2]-right[2])

def polygon_area_3d(points: tuple[Point3,...]) -> float:
    if len(points)<3: raise ValueError("roof polygon needs at least three vertices")
    origin=points[0]; area=0.0
    for a,b in zip(points[1:],points[2:]):
        cross=_cross(_sub(a,origin),_sub(b,origin)); area+=sqrt(sum(value*value for value in cross))/2
    return area

def net_roof_area(candidate: RoofBoundaryCandidate) -> float:
    gross=polygon_area_3d(candidate.polygon3d)
    if candidate.opening_area_m2<0 or candidate.opening_area_m2>gross: raise ValueError("opening area must be between zero and gross roof area")
    return gross-candidate.opening_area_m2
