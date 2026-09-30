from winwatt_automation.scripts.run_heating_certification_workflow import (
    validate_workflow_reports,
)


def test_workflow_report_gate_accepts_two_matching_roundtrips() -> None:
    zone = {
        "profile_id": "profile", "status": "passed", "roundtrip_passed": True,
        "source_unchanged": True,
    }
    heating = {
        "profile_id": "profile", "status": "passed",
        "system_roundtrip_passed": True, "zone_roundtrip_passed": True,
        "source_unchanged": True, "copy_changed": True,
    }
    assert validate_workflow_reports(
        zone=zone, heating=heating, profile_id="profile",
        source_sha256="same", final_source_sha256="same",
    ) == []


def test_workflow_report_gate_lists_failed_postconditions() -> None:
    errors = validate_workflow_reports(
        zone={"profile_id": "wrong", "status": "failed"},
        heating={"profile_id": "profile", "status": "passed"},
        profile_id="profile", source_sha256="before", final_source_sha256="after",
    )
    assert "zone profile mismatch" in errors
    assert "heating-system roundtrip failed" in errors
    assert "workflow changed the original source" in errors
