import base64
import json
from pathlib import Path

from pypdf import PdfWriter

from winwatt_automation.certificates.oeny_reconstruction import (
    PARSER_VERSION,
    build_one_zone_candidate,
    build_reconstruction_spec,
    extract_structure_records,
    write_reconstruction_intake,
)


def _pdf_bytes() -> bytes:
    import io

    target = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.add_metadata({"/Producer": "WinWatt 9.56 test"})
    writer.write(target)
    return target.getvalue()


def _xml(path: Path) -> None:
    encoded = base64.b64encode(_pdf_bytes()).decode("ascii")
    path.write_text(
        f"""<UploadRequest>
<Header><EnergyClassification>A</EnergyClassification><Co2Emission>A</Co2Emission></Header>
<BuildingData><ClientName>Teszt Elek</ClientName><TopographicalNumber>123</TopographicalNumber>
<BuildingPurpose>SingleFamilyHome</BuildingPurpose><YearOfConstruct>2001</YearOfConstruct>
<UsefulFloorArea>100.00</UsefulFloorArea><ConditionedVolume>300.00</ConditionedVolume>
<BuildingAreaToVolumeRatio>0.80</BuildingAreaToVolumeRatio></BuildingData>
<EfficiencyCategories><CurrentValues><SummariesEnergyRating><Value>75.00</Value></SummariesEnergyRating>
<Co2><Value>18.00</Value></Co2><HeatLossFactor><Value>0.40</Value></HeatLossFactor></CurrentValues></EfficiencyCategories>
<CertifierDetails><SoftwareAndVersion>WinWatt 9.56 (2026. 4. 30.)</SoftwareAndVersion></CertifierDetails>
<BoundaryAndOpeningStructures><BoundaryAndOpeningStructure/><BoundaryAndOpeningStructure/></BoundaryAndOpeningStructures>
<Photos><Photo/><Photo/></Photos><CalculationsPdfFileContent>{encoded}</CalculationsPdfFileContent>
</UploadRequest>""",
        encoding="utf-8",
    )


def test_build_reconstruction_spec_reads_xml_and_embedded_pdf(tmp_path: Path) -> None:
    source = tmp_path / "12345678.xml"
    _xml(source)

    spec, pdf = build_reconstruction_spec(source)

    assert pdf.startswith(b"%PDF-")
    assert spec["certificate_id"] == "12345678"
    assert spec["parser_version"] == PARSER_VERSION
    assert spec["fields"]["useful_floor_area_m2"]["value"] == 100.0
    assert spec["inventory"]["boundary_and_opening_structure_groups"] == 2
    assert spec["inventory"]["photos"] == 2
    assert len(spec["photos"]) == 2
    assert spec["photos"][0]["base64_valid"] is False
    assert "Photos" not in spec["xml_sections"]
    assert spec["engine"]["source_version"] == "9.56"
    assert spec["engine"]["mode"] == "current_engine_reconstruction"
    assert spec["execution"] == {"llm_used": False, "winwatt_started": False}
    assert spec["model_draft"]["project"]["heated_area_m2"] == 100.0
    assert spec["model_draft"]["rooms"] == []


def test_intake_is_restartable_and_checks_cached_pdf(tmp_path: Path) -> None:
    source = tmp_path / "12345678.xml"
    _xml(source)
    output = tmp_path / "out"

    first = write_reconstruction_intake(source, output)
    second = write_reconstruction_intake(source, output)

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert (output / "12345678" / "source_calculation.pdf").is_file()
    assert (output / "12345678" / "reconstruction_spec.json").is_file()
    assert (output / "12345678" / "model_draft.json").is_file()


def test_intake_rebuilds_same_source_after_parser_upgrade(tmp_path: Path) -> None:
    source = tmp_path / "12345678.xml"
    _xml(source)
    output = tmp_path / "out"
    write_reconstruction_intake(source, output)
    spec_path = output / "12345678" / "reconstruction_spec.json"
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    payload["parser_version"] = "older-parser"
    spec_path.write_text(json.dumps(payload), encoding="utf-8")

    rebuilt = write_reconstruction_intake(source, output)

    repaired = json.loads(spec_path.read_text(encoding="utf-8"))
    assert rebuilt.cache_hit is False
    assert repaired["parser_version"] == PARSER_VERSION


def test_structure_parser_keeps_printed_values_and_marks_allocation_unresolved() -> None:
    records = extract_structure_records([
        "Szerkezet típusok:\nFal A\nTípusa: külső fal\n"
        "Rétegtervi hőátbocsátási tényező: 0.169 W/m2K\n"
        "Eredő hőátbocsátási tényező: 0.219 W/m2K\n"
        "Ablak A\nTípusa: ablak (külső, fa vagy PVC)\n"
        "x méret: 1,2 m\ny méret: 1,5 m\n"
        "Hőátbocsátási tényező: 1.100 W/m2K\n"
        "Üvegezési arány: 70 %\nÜvegezés g értéke: 0.550\n"
    ])
    assert records[0]["name"] == "Fal A"
    assert records[0]["u_layer"] == 0.169
    assert records[0]["u_effective"] == 0.219
    assert records[1]["x_m"] == 1.2
    assert records[1]["y_m"] == 1.5
    assert records[1]["glazing_ratio_percent"] == 70.0
    assert records[1]["room_allocation"] == "unresolved"


def test_structure_parser_does_not_treat_ground_y_parameter_as_geometry() -> None:
    records = extract_structure_records([
        "Padló\nTípusa: padló (talajra fektetett ISO 13370)\ny méret: 1 m\n"
    ])
    assert records[0]["y_m"] is None


def test_one_zone_candidate_uses_exact_totals_and_explicit_decisions() -> None:
    spec = {
        "certificate_id": "12345678",
        "parser_version": PARSER_VERSION,
        "source": {
            "xml": {"path": "source.xml", "sha256": "a" * 64},
            "embedded_pdf": {"sha256": "b" * 64},
        },
        "engine": {"mode": "current_engine_reconstruction"},
        "fields": {
            "useful_floor_area_m2": {"value": 32.8},
            "conditioned_volume_m3": {"value": 88.56},
        },
        "structure_records": [{
            "name": "Fal", "type": "külső fal", "u_layer": 0.5,
            "u_effective": 0.7, "source": {"kind": "embedded_pdf", "page": 2},
        }],
        "system_records": [],
    }
    decisions = {
        "schema": "autowinwatt-oeny-reconstruction-decisions/v1",
        "certificate_id": "12345678",
        "room_name": "F1",
        "room_count_decision": {"accepted": True, "basis": "PDF has one calculation zone"},
        "wall_geometry_decision": {
            "accepted": True,
            "method": "effective_zone_height_and_exact_printed_area",
            "owner": "human_user",
        },
        "boundaries": [{
            "name": "Fal ÉK", "structure": "Fal", "winwatt_type": "külső fal",
            "area_m2": 10.0,
        }],
        "layers": [{"structure": "Fal", "sequence": 1, "name": "Tégla", "thickness_cm": 30}],
        "material_approvals": [{
            "structure": "Fal", "sequence": 1, "source_name": "Tégla",
            "catalog_material_id": "7", "catalog_material_name": "Tömör tégla",
            "approved": True, "owner": "human_user",
        }],
    }

    model = build_one_zone_candidate(spec, decisions)

    assert model["rooms"] == [{
        "name": "F1", "building": "B1", "area_m2": 32.8, "height_m": 2.7,
        "volume_m3": 88.56, "temperature_c": 20.0, "reviewed": True,
        "review_basis": decisions["room_count_decision"],
    }]
    assert model["boundaries"][0]["room"] == "F1"
    assert model["boundaries"][0]["x_m"] == 10 / 2.7
    assert model["boundaries"][0]["y_m"] == 2.7
    assert model["boundaries"][0]["x_m"] * model["boundaries"][0]["y_m"] == 10.0
    assert model["boundaries"][0]["geometry_derivation"]["not_as_built_measurement"] is True
    assert model["project"]["require_wall_xy"] is True
    assert model["layers"][0]["name"] == "Tégla"
    assert model["layers"][0]["catalog_material_id"] == "7"
    assert model["layers"][0]["reviewed"] is True


def test_one_zone_candidate_rejects_unaccepted_room_decision() -> None:
    spec = {"certificate_id": "1"}
    decisions = {
        "schema": "autowinwatt-oeny-reconstruction-decisions/v1",
        "certificate_id": "1",
        "room_count_decision": {"accepted": False},
    }
    try:
        build_one_zone_candidate(spec, decisions)
    except ValueError as exc:
        assert "not accepted" in str(exc)
    else:
        raise AssertionError("unaccepted room decision must fail")


def test_one_zone_candidate_keeps_wall_xy_open_without_explicit_decision() -> None:
    spec = {
        "certificate_id": "1", "parser_version": PARSER_VERSION,
        "source": {"xml": {"path": "x", "sha256": "a"}, "embedded_pdf": {"sha256": "b"}},
        "engine": {"mode": "current_engine_reconstruction"},
        "fields": {"useful_floor_area_m2": {"value": 10}, "conditioned_volume_m3": {"value": 27}},
        "structure_records": [{"name": "Fal", "type": "külső fal", "source": {}}],
    }
    decisions = {
        "schema": "autowinwatt-oeny-reconstruction-decisions/v1",
        "certificate_id": "1", "room_count_decision": {"accepted": True},
        "boundaries": [{"name": "Fal", "structure": "Fal", "winwatt_type": "külső fal", "area_m2": 12}],
    }
    model = build_one_zone_candidate(spec, decisions)
    assert "x_m" not in model["boundaries"][0]
    assert "y_m" not in model["boundaries"][0]
    assert model["project"]["require_wall_xy"] is False
