from pathlib import Path

import pytest

from winwatt_automation.workflows.webwatt_certificate_intake import process_local_intake


def test_xml_intake_is_local_hashed_and_restartable(tmp_path: Path) -> None:
    source = tmp_path / "input.xml"
    source.write_text("<WinWatt32Project><WinWatt32Room/><WinWatt32Room/></WinWatt32Project>", encoding="utf-8")
    output = tmp_path / "result"

    first = process_local_intake(source=source, output_dir=output)
    second = process_local_intake(source=source, output_dir=output)

    assert first["status"] == "review_required"
    assert first["summary"] == {"kind": "xml", "llm_used": False}
    assert first["winwatt_started"] is False
    assert first["llm_used"] is False
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert (output / "xml_intake_summary.json").is_file()
    assert (output / "intake_manifest.json").is_file()


def test_cached_intake_rejects_changed_source(tmp_path: Path) -> None:
    source = tmp_path / "input.xml"
    source.write_text("<a/>", encoding="utf-8")
    output = tmp_path / "result"
    process_local_intake(source=source, output_dir=output)
    source.write_text("<b/>", encoding="utf-8")

    with pytest.raises(ValueError, match="different source bytes"):
        process_local_intake(source=source, output_dir=output)


def test_pdf_intake_requires_local_catalog(tmp_path: Path) -> None:
    source = tmp_path / "input.pdf"
    source.write_bytes(b"%PDF-not-needed-for-this-guard")

    with pytest.raises(ValueError, match="material catalogue"):
        process_local_intake(source=source, output_dir=tmp_path / "result")
