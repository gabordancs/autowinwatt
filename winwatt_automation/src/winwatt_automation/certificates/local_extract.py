"""Local-only certificate extraction; it never infers geometry from prose."""
from __future__ import annotations
import hashlib, re
from pathlib import Path
from .models import Evidence, ExtractedValue
def extract_pdf_pages(pdf_path: Path) -> list[str]:
    """Read text locally, preferring pypdf with a PyMuPDF fallback."""
    try:
        from pypdf import PdfReader
        return [(page.extract_text() or "") for page in PdfReader(str(pdf_path)).pages]
    except ModuleNotFoundError:
        try:
            import fitz  # PyMuPDF is bundled in the local workspace runtime.
        except ModuleNotFoundError as exc:
            raise RuntimeError("PDF extraction needs pypdf or local PyMuPDF (fitz)") from exc
        document = fitz.open(pdf_path)
        try:
            return [page.get_text() or "" for page in document]
        finally:
            document.close()
def source_digest(pdf_path: Path) -> str:
    return hashlib.sha256(pdf_path.read_bytes()).hexdigest()
def extract_known_values(pages: list[str]) -> list[ExtractedValue]:
    patterns={
        "heated_area_m2":r"fűtött\s+(?:nettó\s+)?alapterület\s*[:=]?\s*([0-9][0-9 .]*[,.][0-9]+)\s*m[²2]",
        "useful_floor_area_m2":r"hasznos\s+alapterület\s*[:=]?\s*([0-9][0-9 .]*[,.][0-9]+)\s*m[²2]",
        "heated_volume_m3":r"V\s*:\s*([0-9][0-9 .]*[,.][0-9]+)\s*m[³3]\s*\(Fűtött\s+épület",
        "a_v":r"A\s*/\s*V\s*:\s*([0-9][0-9 .]*[,.][0-9]+)\s*m[²2]/m[³3]",
        "area_volume_ratio_m2_m3":r"felület-térfogat\s+aránya\s*:\s*([0-9][0-9 .]*[,.][0-9]+)\s*m[²2]/m[³3]",
        "transmission_wk":r"ΣAU\s*\+\s*ΣlΨ\s*:\s*([0-9][0-9 .]*[,.][0-9]+)\s*W/K",
        "summaries_energy_rating_kwh_m2a":r"összesített\s+energetikai\s+jellemző\s*:\s*([0-9][0-9 .]*[,.][0-9]+)\s*kWh/m[²2]a",
        "co2_kg_m2a":r"fajlagos\s+sz[ée]n(?:-)?dioxid\s+kibocsátás\s*:\s*([0-9][0-9 .]*[,.][0-9]+)\s*kg/m[²2]a",
        "heat_loss_factor_w_m3k":r"fajlagos\s+hőveszteségtényező\s*:\s*([0-9][0-9 .]*[,.][0-9]+)\s*W/m[³3]K",
    }
    found=[]
    for index,page in enumerate(pages,1):
        compact=" ".join(page.split())
        for key,pattern in patterns.items():
            match=re.search(pattern,compact,re.I)
            if match and not any(item.key==key for item in found):
                found.append(ExtractedValue(key=key,value=float(match.group(1).replace(" ","").replace(",",".")),evidence=Evidence(page=index,excerpt=match.group(0),confidence=.98)))
    return found
def candidate_material_lines(pages: list[str]) -> list[str]:
    """Return prose-like material candidates, never bare dimension rows.

    Certificate layouts often emit dimensions such as ``77.000 m`` on their
    own line.  They are geometry evidence, not material names, and must not
    pollute catalogue matching or an optional narrowly-scoped LLM review.
    """
    lines=[]
    for page in pages:
        for raw_line in page.splitlines():
            line = " ".join(raw_line.split())
            if not re.search(r"\b(?:mm|cm|m)\b", line, re.I) or len(line) < 6:
                continue
            # A leading number or an assignment label indicates a measured
            # geometric dimension rather than a catalogue/material caption.
            if (
                re.match(r"^[0-9]", line)
                or "=" in line
                or re.match(r"^[xy]\s+méret\s*:", line, re.I)
                or line.startswith("[")
                or re.search(r"\bkWh/m|\bkg/m|\bW/m", line, re.I)
            ):
                continue
            lines.append(line)
    return list(dict.fromkeys(lines))
