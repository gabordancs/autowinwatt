from pathlib import Path

import fitz

from winwatt_automation.e2e_review.domain import DocumentEvidence, ReviewCandidate
from winwatt_automation.e2e_review.evidence_locator import locate_candidate
from winwatt_automation.e2e_review.pdf_evidence import render_full_page


def test_exact_native_text_gets_real_bbox(tmp_path: Path):
    pdf=tmp_path/"É02_TERV.pdf"; document=fitz.open(); page=document.new_page(); page.insert_text((72,72),"NAPPALI 24,17 m2"); document.save(pdf); document.close()
    candidate=ReviewCandidate("x","room","FSZ-01","Alapterület [m²]","24,17",unit="m²",evidence=DocumentEvidence("É-02"))
    result=locate_candidate(candidate,tmp_path)
    assert result.evidence.evidence_bbox is not None
    assert result.evidence.extraction_method=="native_pdf_text_exact"


def test_ambiguous_text_remains_missing(tmp_path: Path):
    pdf=tmp_path/"É02_TERV.pdf"; document=fitz.open(); page=document.new_page(); page.insert_text((72,72),"24,17 24,17"); document.save(pdf); document.close()
    candidate=ReviewCandidate("x","room","FSZ-01","Alapterület [m²]","24,17",unit="m²",evidence=DocumentEvidence("É-02"))
    assert locate_candidate(candidate,tmp_path).evidence.evidence_bbox is None


def test_full_page_render_keeps_content_outside_evidence_crop(tmp_path: Path):
    pdf=tmp_path/"É02_TERV.pdf"; document=fitz.open(); page=document.new_page(width=300,height=300); page.insert_text((250,250),"TÁVOLI"); document.save(pdf); document.close()
    candidate=ReviewCandidate("x","room","FSZ-01","Alapterület [m²]","24,17",unit="m²",evidence=DocumentEvidence("É-02", evidence_bbox=(10,10,30,30)))
    data, _=render_full_page(pdf,candidate.evidence,zoom=1)
    assert len(data)>500
