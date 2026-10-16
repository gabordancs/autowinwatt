from winwatt_automation.artifacts import is_external_artifact_path


def test_runtime_and_binary_artifacts_are_externalized() -> None:
    assert is_external_artifact_path("winwatt_automation/data/runtime_maps/run/report.json")
    assert is_external_artifact_path("energetika/Alkalmazott_Epuletenergetika.pdf")
    assert is_external_artifact_path("winwatt_automation/tests/testwwp.wwp")
    assert is_external_artifact_path("somewhere/worker.checkpoint.json")


def test_source_and_curated_knowledge_stay_in_git() -> None:
    assert not is_external_artifact_path("winwatt_automation/src/winwatt_automation/app.py")
    assert not is_external_artifact_path(
        "winwatt_automation/data/knowledge/certification_domain_knowledge.json"
    )
