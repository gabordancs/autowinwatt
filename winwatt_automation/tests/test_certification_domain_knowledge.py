from pathlib import Path

from winwatt_automation.knowledge.certification_domain import (
    DEFAULT_KNOWLEDGE_PATH,
    DEFAULT_MANIFEST_PATH,
    PROJECT_ROOT,
    audit_domain_knowledge,
    load_domain_knowledge,
    load_source_manifest,
)
from winwatt_automation.scripts.build_certification_source_manifest import build_manifest
from winwatt_automation.scripts.query_certification_domain_knowledge import main as query_main


def test_certification_domain_knowledge_is_source_backed_and_current() -> None:
    manifest = load_source_manifest()
    knowledge = load_domain_knowledge()

    assert knowledge.source_manifest_id == manifest.manifest_id
    assert not audit_domain_knowledge(knowledge, manifest)
    assert {source.role for source in manifest.sources} >= {
        "authoritative",
        "catalog",
        "example",
        "guide",
        "reference",
    }


def test_certification_source_manifest_is_reproducible() -> None:
    manifest = load_source_manifest()
    regenerated = build_manifest(PROJECT_ROOT.parent / "energetika")

    assert regenerated == manifest.model_dump(mode="json")
    source_root = PROJECT_ROOT.parent / "energetika"
    assert {item.relative_path for item in manifest.sources} == {
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*") if path.is_file()
    }


def test_knowledge_checks_cover_source_priority_and_scope_boundary() -> None:
    manifest = load_source_manifest()
    knowledge = load_domain_knowledge()
    source_ids = {source.source_id for source in manifest.sources}
    checks = {check.check_id: check for check in knowledge.knowledge_checks}

    assert "check.source_precedence" in checks
    assert "check.knowledge_only_scope" in checks
    for check in checks.values():
        assert set(check.required_source_ids) <= source_ids


def test_manifest_and_knowledge_files_are_under_versioned_data() -> None:
    assert DEFAULT_MANIFEST_PATH.is_file()
    assert DEFAULT_KNOWLEDGE_PATH.is_file()
    assert DEFAULT_MANIFEST_PATH.parent.name == "knowledge"


def test_query_audit_reports_passed(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["query", "--audit"])

    assert query_main() == 0
    payload = capsys.readouterr().out
    assert '"status": "passed"' in payload
    assert '"source_count": 41' in payload


def test_new_residential_reference_value_is_source_backed() -> None:
    knowledge = load_domain_knowledge()
    claim = next(
        item for item in knowledge.claims
        if item.claim_id == "requirement.new_residential_primary_energy"
    )
    check = next(
        item for item in knowledge.knowledge_checks
        if item.check_id == "check.new_residential_reference_value"
    )

    assert "95 kWh/m²év" in claim.claim
    assert "76 kWh/m²év" in claim.claim
    assert check.required_source_ids == ["legal.energy_performance_decree_9_2023"]
