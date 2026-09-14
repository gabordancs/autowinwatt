"""Local, evidence-first extraction of architectural dimension chains.

The extractor deliberately does *not* infer a wall length from room area.
It accepts a dimension only if the drawing provides a dimension line, two
oblique end ticks, a nearby numeric label and extension-line evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from pathlib import Path
import re
from typing import Iterable, Literal

Point = tuple[float, float]
Orientation = Literal["horizontal", "vertical"]
_NUMBER = re.compile(r"^\s*(\d{1,2}(?:[,.]\d{1,3})?)\s*$")


@dataclass(frozen=True)
class Line:
    start: Point
    end: Point
    width: float = 0.0

    @property
    def length(self) -> float:
        return math.dist(self.start, self.end)

    @property
    def angle_deg(self) -> float:
        return math.degrees(math.atan2(self.end[1] - self.start[1], self.end[0] - self.start[0])) % 180

    @property
    def midpoint(self) -> Point:
        return ((self.start[0] + self.end[0]) / 2, (self.start[1] + self.end[1]) / 2)


@dataclass(frozen=True)
class TextLabel:
    value_m: float
    center: Point
    bbox: tuple[float, float, float, float]
    raw: str


@dataclass(frozen=True)
class DimensionEvidence:
    page: int
    orientation: Orientation
    value_m: float
    dimension_start: Point
    dimension_end: Point
    text: str
    text_center: Point
    tick_count: int
    extension_count: int
    confidence: float

    def json(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WallSegment:
    room: str
    wall_id: str
    plan_length_m: float
    height_m: float
    area_m2: float
    azimuth_deg: int
    evidence: DimensionEvidence

    def json(self) -> dict:
        result = asdict(self)
        result["evidence"] = self.evidence.json()
        return result


def _axis(line: Line, tolerance_deg: float = 3.0) -> Orientation | None:
    angle = line.angle_deg
    if min(abs(angle), abs(180 - angle)) <= tolerance_deg:
        return "horizontal"
    if abs(angle - 90) <= tolerance_deg:
        return "vertical"
    return None


def _is_tick(line: Line, min_length: float, max_length: float) -> bool:
    return min_length <= line.length <= max_length and 25 <= line.angle_deg <= 65 or (
        min_length <= line.length <= max_length and 115 <= line.angle_deg <= 155
    )


def _distance_to_axis(point: Point, orientation: Orientation, coordinate: float) -> float:
    return abs(point[1] - coordinate) if orientation == "horizontal" else abs(point[0] - coordinate)


def _axis_coordinate(point: Point, orientation: Orientation) -> float:
    return point[0] if orientation == "horizontal" else point[1]


def _text_labels(page: object) -> list[TextLabel]:
    labels: list[TextLabel] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                raw = span.get("text", "")
                match = _NUMBER.match(raw)
                if not match:
                    continue
                value = float(match.group(1).replace(",", "."))
                # Dimension labels are metre-scale.  Excludes level marks,
                # drawings numbers and long document identifiers.
                if not 0.1 <= value <= 30:
                    continue
                x0, y0, x1, y1 = span["bbox"]
                labels.append(TextLabel(value, ((x0 + x1) / 2, (y0 + y1) / 2), (x0, y0, x1, y1), raw))
    return labels


def _drawing_lines(page: object) -> list[Line]:
    lines: list[Line] = []
    for drawing in page.get_drawings():
        for item in drawing.get("items", []):
            if item[0] != "l":
                continue
            start, end = item[1], item[2]
            lines.append(Line((float(start.x), float(start.y)), (float(end.x), float(end.y)), float(drawing.get("width") or 0)))
    return lines


def extract_page_dimension_chains(page: object, page_number: int, *, tick_min_pt: float = 1.5, tick_max_pt: float = 12.0, tolerance_pt: float = 3.0) -> list[DimensionEvidence]:
    """Return high-confidence dimension values from one PyMuPDF page.

    A pair of oblique ticks establishes the candidate extent.  A collinear
    horizontal/vertical drawing segment and a numeric label between those
    ticks establish the actual dimension chain.  Perpendicular extension
    lines are counted as independent evidence rather than assumed.
    """
    lines = _drawing_lines(page)
    ticks = [line for line in lines if _is_tick(line, tick_min_pt, tick_max_pt)]
    axes = [line for line in lines if _axis(line) and line.length >= 8]
    labels = _text_labels(page)
    # A text label may have many incidental pairs of short diagonal drawing
    # lines around it. Keep just the strongest geometrically centred match.
    best_for_label: dict[tuple[int, int, str], tuple[float, DimensionEvidence]] = {}
    for first_index, first in enumerate(ticks):
        for second in ticks[first_index + 1:]:
            # Dimension ticks have matching slope and define a horizontal or
            # vertical baseline between their midpoints.
            if abs(first.angle_deg - second.angle_deg) > 8:
                continue
            dx = abs(first.midpoint[0] - second.midpoint[0])
            dy = abs(first.midpoint[1] - second.midpoint[1])
            if max(dx, dy) < 12:
                continue
            orientation: Orientation = "horizontal" if dx >= dy else "vertical"
            perpendicular = dy if orientation == "horizontal" else dx
            if perpendicular > tolerance_pt:
                continue
            coordinate = (first.midpoint[1] + second.midpoint[1]) / 2 if orientation == "horizontal" else (first.midpoint[0] + second.midpoint[0]) / 2
            first_axis, second_axis = sorted((_axis_coordinate(first.midpoint, orientation), _axis_coordinate(second.midpoint, orientation)))
            # At least one piece of the baseline must be drawn between ticks;
            # it can be interrupted by the printed dimension label.
            baselines = [line for line in axes if _axis(line) == orientation and _distance_to_axis(line.midpoint, orientation, coordinate) <= tolerance_pt and not (_axis_coordinate(line.midpoint, orientation) < first_axis - 2 or _axis_coordinate(line.midpoint, orientation) > second_axis + 2)]
            if not baselines:
                continue
            span = second_axis - first_axis
            between = [label for label in labels if first_axis - 3 <= _axis_coordinate(label.center, orientation) <= second_axis + 3 and _distance_to_axis(label.center, orientation, coordinate) <= 18 and abs(_axis_coordinate(label.center, orientation) - (first_axis + second_axis) / 2) <= max(8, span * .24)]
            if not between:
                continue
            # Extension lines cross the baseline around the end ticks and are
            # perpendicular to it. Their existence prevents accepting random
            # diagonal hatching as a dimension chain.
            perpendicular_axis: Orientation = "vertical" if orientation == "horizontal" else "horizontal"
            extensions = []
            for tick in (first, second):
                tick_axis = _axis_coordinate(tick.midpoint, orientation)
                matches = [line for line in axes if _axis(line) == perpendicular_axis and abs(_axis_coordinate(line.midpoint, orientation) - tick_axis) <= tolerance_pt and _distance_to_axis(line.midpoint, orientation, coordinate) <= max(20, line.length / 2 + tolerance_pt)]
                if matches:
                    extensions.append(max(matches, key=lambda line: line.length))
            for label in between:
                extension_count = len(extensions)
                confidence = 0.55 + 0.15 + min(0.2, 0.1 * extension_count) + 0.1
                evidence = DimensionEvidence(
                    page=page_number, orientation=orientation, value_m=label.value_m,
                    dimension_start=(first_axis, coordinate) if orientation == "horizontal" else (coordinate, first_axis),
                    dimension_end=(second_axis, coordinate) if orientation == "horizontal" else (coordinate, second_axis),
                    text=label.raw, text_center=label.center, tick_count=2,
                    extension_count=extension_count, confidence=round(min(confidence, 1.0), 2),
                )
                centring = abs(_axis_coordinate(label.center, orientation) - (first_axis + second_axis) / 2) / max(span, 1)
                score = evidence.confidence - centring - .02 * abs(span - 40)
                key = (round(label.center[0]), round(label.center[1]), label.raw)
                if key not in best_for_label or score > best_for_label[key][0]:
                    best_for_label[key] = (score, evidence)
    return sorted((item[1] for item in best_for_label.values()), key=lambda item: (-item.confidence, item.page, item.value_m))


def extract_pdf_dimension_chains(pdf_path: Path) -> list[DimensionEvidence]:
    """Read dimension evidence locally from a vector PDF plan."""
    try:
        import fitz
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("Dimension-chain extraction needs local PyMuPDF") from exc
    document = fitz.open(pdf_path)
    try:
        return [evidence for index, page in enumerate(document, 1) for evidence in extract_page_dimension_chains(page, index)]
    finally:
        document.close()


def wall_segment_from_evidence(*, room: str, wall_id: str, evidence: DimensionEvidence, height_m: float, azimuth_deg: int) -> WallSegment:
    """Create a WinWatt-ready wall segment only from accepted evidence."""
    if evidence.tick_count != 2 or evidence.extension_count < 2 or evidence.confidence < 0.8:
        raise ValueError("Dimension evidence is incomplete; keep this wall for human review")
    return WallSegment(room, wall_id, evidence.value_m, height_m, round(evidence.value_m * height_m, 2), azimuth_deg, evidence)
