"""Rebase reviewed PDF transcriptions onto a direct-PDF-only provenance policy."""
from __future__ import annotations

import argparse
import difflib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from pypdf import PdfReader


def _normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


def _ascii_tokens(value: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.findall(r"[a-z0-9]+", folded.casefold())


def _is_printed(value: str, joined: str) -> bool:
    if _normalize(value) in joined:
        return True
    expected = _ascii_tokens(value)
    actual = _ascii_tokens(joined)
    if not expected:
        return False
    matches = sum(
        1 for token in expected
        if any(difflib.SequenceMatcher(None, token, candidate).ratio() >= 0.85 for candidate in actual)
    )
    return matches / len(expected) >= 0.6


def _rewrite_sources(value: Any) -> Any:
    if isinstance(value, dict):
        result = {key: _rewrite_sources(child) for key, child in value.items()}
        source = result.get("source")
        if isinstance(source, dict) and source.get("kind") == "embedded_pdf":
            source["kind"] = "pdf"
        return result
    if isinstance(value, list):
        return [_rewrite_sources(child) for child in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--decisions", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    spec = json.loads(args.spec.resolve(strict=True).read_text(encoding="utf-8"))
    if spec.get("input_policy", {}).get("construction_input") != "pdf_only":
        raise ValueError("spec is not PDF-only")
    decisions = json.loads(args.decisions.resolve(strict=True).read_text(encoding="utf-8"))
    pages = [page.extract_text() or "" for page in PdfReader(args.pdf.resolve(strict=True)).pages]
    joined = _normalize("\n".join(pages))

    required_printed_values = [
        str(decisions.get("address") or ""),
        str(decisions.get("building_name") or ""),
        str(decisions.get("room_name") or ""),
    ]
    missing = [value for value in required_printed_values if value and not _is_printed(value, joined)]
    if missing:
        raise ValueError(f"reviewed decision values are not printed in the PDF: {missing}")

    rebased = _rewrite_sources(decisions)
    rebased["input_policy"] = {
        "construction_input": "pdf_only",
        "reference_xml_role": "post_export_validation_only",
        "xml_values_allowed_during_build": False,
    }
    rebased["source_pdf"] = spec["source"]["pdf"]
    rebased["address_source"] = {"kind": "pdf", "page": 1}
    rebased["building_name_source"] = {"kind": "pdf", "page": 1}
    rebased["room_name_source"] = spec["calculation_zone"]["zone_name"]["source"]
    room_decision = rebased.get("room_count_decision") or {}
    room_decision["basis"] = (
        "The direct source PDF prints one calculation zone, F1, with 32.8 m2 and "
        "88.6 m3; the user confirmed that no additional WinWatt rooms should be invented."
    )
    rebased["room_count_decision"] = room_decision

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rebased, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
