from __future__ import annotations

import fitz
import pytest

from winwatt_automation.certificates.dimension_chains import (
    DimensionEvidence,
    extract_page_dimension_chains,
    wall_segment_from_evidence,
)


def _synthetic_dimension_page() -> fitz.Page:
    document = fitz.open()
    page = document.new_page(width=300, height=200)
    # Dimension baseline, two 45 degree end ticks and the two extensions.
    page.draw_line((60, 80), (110, 80))
    page.draw_line((130, 80), (180, 80))
    page.draw_line((57, 77), (63, 83))
    page.draw_line((177, 77), (183, 83))
    page.draw_line((60, 50), (60, 100))
    page.draw_line((180, 50), (180, 100))
    page.insert_text((108, 77), "2,29", fontsize=9)
    return page


def test_extracts_dimension_chain_from_vector_evidence():
    evidence = extract_page_dimension_chains(_synthetic_dimension_page(), 1)
    assert len(evidence) == 1
    assert evidence[0].value_m == 2.29
    assert evidence[0].orientation == "horizontal"
    assert evidence[0].extension_count >= 2
    assert evidence[0].confidence >= 0.8


def test_wall_requires_complete_evidence():
    incomplete = DimensionEvidence(1, "horizontal", 2.29, (0, 0), (1, 0), "2,29", (0, 0), 2, 1, .9)
    with pytest.raises(ValueError):
        wall_segment_from_evidence(room="B10a", wall_id="top", evidence=incomplete, height_m=2.84, azimuth_deg=36)
