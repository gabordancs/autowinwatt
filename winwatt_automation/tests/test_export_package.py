from pathlib import Path

import pytest

from winwatt_automation.certificates.export_package import ExportPackageError, build_export_manifest


def _write(path: Path, content: bytes) -> str:
    path.write_bytes(content)
    return path.name


def _complete_package(tmp_path: Path) -> dict:
    return {
        "wwp": _write(tmp_path / "project.wwp", b"wwp"),
        "native_xml": _write(tmp_path / "native.xml", b"<WinWatt32Project Type='NativeExport'/>") ,
        "calculation_pdf": _write(tmp_path / "calculation.pdf", b"%PDF-1.4\nfixture"),
        "certificate_xml": _write(tmp_path / "certificate.xml", b"<UploadRequest/>") ,
        "photos": [
            _write(tmp_path / "photo-01.jpg", b"jpeg-fixture"),
            _write(tmp_path / "photo-02.png", b"png-fixture"),
        ],
    }


def test_complete_q7_package_gets_hashes_and_xml_roots(tmp_path: Path) -> None:
    manifest = build_export_manifest(tmp_path, _complete_package(tmp_path), source_project_sha256="abc")

    assert manifest["schema"] == "autowinwatt.q7-export-package/v1"
    assert manifest["source_project_sha256"] == "abc"
    assert manifest["artifacts"]["native_xml"][0]["xml_root"] == "WinWatt32Project"
    assert manifest["artifacts"]["certificate_xml"][0]["xml_root"] == "UploadRequest"
    assert len(manifest["artifacts"]["photos"]) == 2
    assert all(len(items[0]["sha256"]) == 64 for key, items in manifest["artifacts"].items() if key != "photos")


def test_missing_q7_artifact_is_rejected(tmp_path: Path) -> None:
    artifacts = _complete_package(tmp_path)
    del artifacts["calculation_pdf"]

    with pytest.raises(ExportPackageError, match="calculation_pdf"):
        build_export_manifest(tmp_path, artifacts)


def test_malformed_xml_is_rejected(tmp_path: Path) -> None:
    artifacts = _complete_package(tmp_path)
    (tmp_path / "certificate.xml").write_text("<UploadRequest>", encoding="utf-8")

    with pytest.raises(ExportPackageError, match="Hibás XML"):
        build_export_manifest(tmp_path, artifacts)


def test_artifact_outside_package_is_rejected(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    artifacts = _complete_package(package)
    outside = tmp_path / "outside.wwp"
    outside.write_bytes(b"wwp")
    artifacts["wwp"] = outside

    with pytest.raises(ExportPackageError, match="kívül"):
        build_export_manifest(package, artifacts)
