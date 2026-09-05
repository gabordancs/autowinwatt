from __future__ import annotations

from pathlib import Path

import pytest

from winwatt_automation.research.manual_index import ManualIndex


def test_winwatt_pdf_extracts_and_finds_external_wall(tmp_path: Path) -> None:
    pdf = Path(__file__).resolve().parents[2] / "WinWatt.pdf"
    if not pdf.is_file():
        pytest.skip("WinWatt.pdf is an optional local research source")
    index = ManualIndex(pdf, tmp_path / "index.json")
    source = index.build()
    results = index.search("külső fal")
    assert source.metadata["page_count"] >= 100
    assert results
    assert all(result["page"] > 0 for result in results)
