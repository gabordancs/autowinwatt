import json
from pathlib import Path

from winwatt_automation.certificates.preflight import run_preflight, validate_model_contract


def model() -> dict:
    return {
        "project": {"name": "Teszt", "heated_area_m2": 10, "heated_volume_m3": 30, "require_wall_xy": True},
        "rooms": [{"name": "Szoba", "area_m2": 10, "height_m": 3, "volume_m3": 30, "temperature_c": 20}],
        "structures": [{"name": "Fal", "type": "külső fal", "u_effective": 0.5}],
        "layers": [],
        "boundaries": [{
            "room": "Szoba", "name": "Fal 1", "structure": "Fal", "winwatt_type": "külső fal",
            "x_m": 2, "y_m": 2, "area_m2": 4, "u_effective": 0.5,
            "heat_loss_wk": 2, "azimuth_deg": 90,
        }],
    }


def readback(path: Path, *, compass: int = 90) -> None:
    path.write_text(f"""<WinWatt32Project>
<WinWatt32Building/><WinWatt32Panel><ItemHeader><ItemName>Fal</ItemName></ItemHeader><k>0.5</k></WinWatt32Panel>
<WinWatt32Room><ItemHeader><ItemName>Szoba</ItemName></ItemHeader><Area>10</Area><CalculatedVolume>30</CalculatedVolume>
<Heating><Temp>20</Temp></Heating><Boundary><Name>Fal 1</Name><A>4</A><x>2</x><y>2</y><Type>0</Type><Compass>{compass}</Compass><U>0.5</U></Boundary>
</WinWatt32Room></WinWatt32Project>""", encoding="utf-8")


def test_envelope_preflight_passes_exact_readback(tmp_path: Path) -> None:
    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(model()), encoding="utf-8")
    readback_path = tmp_path / "readback.xml"
    readback(readback_path)

    report = run_preflight(
        model_path=model_path, readback_xml=readback_path,
        output_dir=tmp_path / "out", scope="envelope",
    )

    assert report["status"] == "passed"
    assert report["readiness"]["geometry_ready"] is True
    assert report["readiness"]["xml_readback_ready"] is True
    assert report["llm_used"] is False


def test_full_certificate_requires_systems_and_calculation(tmp_path: Path) -> None:
    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(model()), encoding="utf-8")
    readback_path = tmp_path / "readback.xml"
    readback(readback_path)

    report = run_preflight(
        model_path=model_path, readback_xml=readback_path,
        output_dir=tmp_path / "out", scope="full_certificate",
    )

    assert report["status"] == "review_required"
    assert report["readiness"]["systems_ready"] is False
    assert report["readiness"]["calculation_ready"] is False


def test_g5_calculation_scope_passes_reviewed_system_without_results(tmp_path: Path) -> None:
    payload = model()
    payload["systems"] = [{
        "name": "Fűtés", "type": "heating", "heat_generator": "elektromos",
        "reviewed": True,
    }]
    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(payload), encoding="utf-8")
    readback_path = tmp_path / "readback.xml"
    readback(readback_path)

    report = run_preflight(
        model_path=model_path, readback_xml=readback_path,
        output_dir=tmp_path / "out", scope="g5_calculation",
    )

    assert report["status"] == "passed"
    assert report["readiness"]["g5_calculation_input_ready"] is True
    assert report["readiness"]["calculation_ready"] is False
    assert report["next_actions"] == []


def test_g5_calculation_scope_lists_missing_human_system_review(tmp_path: Path) -> None:
    payload = model()
    payload["systems"] = [{"name": "Fűtés", "type": "heating"}]
    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(payload), encoding="utf-8")
    readback_path = tmp_path / "readback.xml"
    readback(readback_path)

    report = run_preflight(
        model_path=model_path, readback_xml=readback_path,
        output_dir=tmp_path / "out", scope="g5_calculation",
    )

    assert report["status"] == "review_required"
    assert report["readiness"]["g5_calculation_input_ready"] is False
    assert report["next_actions"][0]["check_id"] == "g5.systems_review"
    assert "human system review is missing" in report["next_actions"][0]["issues"][0]


def test_readback_difference_fails_gate(tmp_path: Path) -> None:
    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(model()), encoding="utf-8")
    readback_path = tmp_path / "readback.xml"
    readback(readback_path, compass=180)

    report = run_preflight(
        model_path=model_path, readback_xml=readback_path,
        output_dir=tmp_path / "out", scope="envelope",
    )

    assert report["status"] == "failed"
    check = next(item for item in report["checks"] if item["check_id"] == "winwatt.readback")
    assert any("surface_by_azimuth" in issue for issue in check["issues"])


def test_model_contract_rejects_dangling_references_and_invalid_xy() -> None:
    payload = model()
    payload["boundaries"][0].update({"room": "Nincs", "area_m2": 5})
    checks = validate_model_contract(payload)

    assert next(item for item in checks if item["check_id"] == "model.references")["status"] == "failed"
    assert next(item for item in checks if item["check_id"] == "model.wall_geometry")["status"] == "failed"
