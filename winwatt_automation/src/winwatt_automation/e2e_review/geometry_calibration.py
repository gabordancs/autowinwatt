"""Deterministic dimension-chain calibration.

The calibration is intentionally conservative: one nominal drawing scale is
never enough. At least two consistent dimension anchors are required before
any pixel value is promoted to a metric length.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class DimensionAnchor:
    evidence_id: str
    pixel_length: float
    measured_length_m: float


@dataclass(frozen=True)
class GeometryCalibration:
    meters_per_pixel: float | None
    anchor_count: int
    residual_percent: float | None
    confidence: float
    status: str
    anchors: tuple[DimensionAnchor, ...]
    reason: str | None = None

    def to_dict(self) -> dict:
        value=asdict(self); value["anchors"]=[asdict(anchor) for anchor in self.anchors]; return value


def calibrate(anchors: Iterable[DimensionAnchor], *, max_residual_percent: float = 2.0) -> GeometryCalibration:
    valid=tuple(anchor for anchor in anchors if anchor.pixel_length > 0 and anchor.measured_length_m > 0)
    if len(valid) < 2:
        return GeometryCalibration(None,len(valid),None,0.0,"unresolved",valid,"at least two positive dimension anchors are required")
    ratios=[anchor.measured_length_m/anchor.pixel_length for anchor in valid]
    scale=median(ratios)
    residuals=[abs(ratio-scale)/scale*100 for ratio in ratios]
    residual=median(residuals)
    if max(residuals)>max_residual_percent:
        return GeometryCalibration(None,len(valid),residual,0.0,"conflict",valid,f"dimension anchors disagree by up to {max(residuals):.3f}%")
    confidence=round(min(0.99,0.55+0.1*len(valid)+max(0.0,0.25-residual/10)),3)
    return GeometryCalibration(scale,len(valid),residual,confidence,"accepted",valid)


def pixels_to_meters(pixel_length: float, calibration: GeometryCalibration) -> float:
    if calibration.status != "accepted" or calibration.meters_per_pixel is None:
        raise ValueError("metric conversion requires an accepted GeometryCalibration")
    return pixel_length*calibration.meters_per_pixel
