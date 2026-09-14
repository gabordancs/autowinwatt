"""Local-only certificate extraction; it never infers geometry from prose."""
from __future__ import annotations
import hashlib, re
from pathlib import Path
from .models import Evidence, ExtractedValue
def extract_pdf_pages(pdf_path: Path) -> list[str]:
    # Keep catalogue-only and manifest tests usable in lightweight developer
    # environments; PDF support remains a declared runtime dependency.
    from pypdf import PdfReader
    return [(page.extract_text() or "") for page in PdfReader(str(pdf_path)).pages]
def source_digest(pdf_path: Path) -> str:
    return hashlib.sha256(pdf_path.read_bytes()).hexdigest()
def extract_known_values(pages: list[str]) -> list[ExtractedValue]:
    patterns={"heated_area_m2":r"(?:fűtött\s+(?:nettó\s+)?alapterület|AN)\s*[:=]?\s*([0-9 .]+,[0-9]+)\s*m[²2]","heated_volume_m3":r"(?:fűtött\s+térfogat|V)\s*[:=]?\s*([0-9 .]+,[0-9]+)\s*m[³3]","a_v":r"A\s*/\s*V\s*[:=]?\s*([0-9]+,[0-9]+)"}
    found=[]
    for index,page in enumerate(pages,1):
        compact=" ".join(page.split())
        for key,pattern in patterns.items():
            match=re.search(pattern,compact,re.I)
            if match and not any(item.key==key for item in found):
                found.append(ExtractedValue(key=key,value=float(match.group(1).replace(" ","").replace(",",".")),evidence=Evidence(page=index,excerpt=match.group(0),confidence=.98)))
    return found
def candidate_material_lines(pages: list[str]) -> list[str]:
    lines=[]
    for page in pages:
        lines.extend(" ".join(line.split()) for line in page.splitlines() if re.search(r"\b(?:mm|cm|m)\b",line,re.I) and len(line.strip())>=6)
    return list(dict.fromkeys(lines))
