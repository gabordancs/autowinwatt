"""Read-only PDF viewport calculations and rendering."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .domain import DocumentEvidence


@dataclass(frozen=True)
class PdfViewport:
    page: int
    crop: tuple[float, float, float, float]
    missing_evidence_location: bool


def viewport_for_evidence(evidence: DocumentEvidence, page_width: float, page_height: float) -> PdfViewport:
    if evidence.context_bbox:
        crop = evidence.context_bbox
    elif evidence.evidence_bbox:
        x0, y0, x1, y1 = evidence.evidence_bbox
        margin = evidence.context_margin
        crop = (x0 - margin, y0 - margin, x1 + margin, y1 + margin)
    else:
        crop = (0.0, 0.0, page_width, page_height)
    x0, y0, x1, y1 = crop
    return PdfViewport(evidence.page or 1, (max(0.0, x0), max(0.0, y0), min(page_width, x1), min(page_height, y1)), evidence.evidence_bbox is None)


def render_viewport(pdf: Path, evidence: DocumentEvidence, *, zoom: float = 1.5) -> tuple[bytes, PdfViewport]:
    import fitz
    document = fitz.open(pdf)
    try:
        page = document[(evidence.page or 1) - 1]
        viewport = viewport_for_evidence(evidence, page.rect.width, page.rect.height)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=fitz.Rect(*viewport.crop), alpha=False)
        return pixmap.tobytes("png"), viewport
    finally:
        document.close()
