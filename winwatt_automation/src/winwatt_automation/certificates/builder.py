from __future__ import annotations
import json
from .llm_cli import resolve_unresolved
from .local_extract import candidate_material_lines,extract_known_values,extract_pdf_pages,source_digest
from .materials import load_catalog,match_by_name
from .models import CertificateBuildInput,CertificateBuildResult
class CertificateProjectBuilder:
    """Build an evidence-first intermediate model; native UI is a later adapter."""
    def build(self,request: CertificateBuildInput) -> CertificateBuildResult:
        pdf=request.certificate_pdf.resolve(); output=request.output_dir.resolve(); output.mkdir(parents=True,exist_ok=True)
        pages=extract_pdf_pages(pdf); values=extract_known_values(pages); catalog=load_catalog(request.catalog_xml.resolve())
        decisions=[match_by_name(line,catalog) for line in candidate_material_lines(pages)]; unresolved=[item.source_name for item in decisions if item.status=="review"]
        llm_used=False; llm_result=None
        if request.allow_llm and unresolved: llm_result=resolve_unresolved(unresolved); llm_used=True
        manifest={"source":{"pdf":str(pdf),"sha256":source_digest(pdf),"pages":len(pages)},"values":[item.model_dump(mode="json") for item in values],"material_decisions":[item.model_dump(mode="json") for item in decisions],"unresolved":unresolved,"llm_used":llm_used,"llm_result":llm_result,"next_step":"Provide an approved structured geometry mapping before native XML generation; raw PDF prose is insufficient evidence for room-boundary allocation."}
        (output/"certificate_build_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        return CertificateBuildResult(output_dir=output,deterministic_values=values,material_decisions=decisions,unresolved=unresolved,llm_used=llm_used)
