"""Deterministic candidate-to-PDF text evidence locator.

It only attaches a bbox when the exact machine value has one unambiguous hit
on the declared source PDF. Ambiguous/missing hits remain explicitly missing.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re

from .domain import DocumentEvidence, ReviewCandidate


def resolve_source_pdf(source: str | None, pdf_root: Path) -> Path | None:
    if not source: return None
    token=source.replace("É","E").replace("-","").replace(" ","").split("+")[0].casefold()
    matches=[]
    for path in pdf_root.glob("*.pdf"):
        name=path.name.replace("É","E").replace("-","").replace(" ","").casefold()
        if token and token in name: matches.append(path)
    return matches[0] if len(matches)==1 else None


def _needle(candidate: ReviewCandidate) -> str | None:
    value=candidate.machine_value
    if value is None: return None
    text=str(value).strip()
    if len(text)<2: return None
    # Full natural-language notes tend to vary during PDF extraction; do not
    # turn fuzzy resemblance into fake evidence coordinates.
    return text if len(text)<=80 and "\n" not in text else None


def locate_candidate(candidate: ReviewCandidate, pdf_root: Path) -> ReviewCandidate:
    if candidate.evidence.evidence_bbox: return candidate
    pdf=resolve_source_pdf(candidate.evidence.source_pdf,pdf_root); needle=_needle(candidate)
    if pdf is None or needle is None: return candidate
    import fitz
    document=fitz.open(pdf)
    try:
        matches=[]
        variants=[needle]
        if "," in needle: variants.append(needle.replace(",","."))
        if "." in needle: variants.append(needle.replace(".",","))
        for page_index,page in enumerate(document,start=1):
            for variant in variants:
                for rect in page.search_for(variant, quads=False):
                    matches.append((page_index,rect))
        # A candidate text must have one result. If a number occurs repeatedly
        # in a title block/dimension chain, a reviewer must choose it.
        if len(matches)!=1: return candidate
        page,rect=matches[0]
        bbox=(round(rect.x0,2),round(rect.y0,2),round(rect.x1,2),round(rect.y1,2))
        evidence=DocumentEvidence(source_pdf=str(pdf),page=page,sheet_no=candidate.evidence.sheet_no,evidence_bbox=bbox,context_margin=candidate.evidence.context_margin,extraction_method="native_pdf_text_exact",confidence=0.99)
        return replace(candidate,evidence=evidence)
    finally:
        document.close()
