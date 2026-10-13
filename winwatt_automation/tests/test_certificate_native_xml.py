from winwatt_automation.certificates.native_xml import (
    _boundary_gradient,
    _boundary_u,
    _building_specs,
    _explicit_glass_ratio,
    _kind,
    _native_integer,
)


def test_panel_type_mapping_matches_winwatt_native_readback() -> None:
    assert _kind("külső fal") == "OutsideWall"
    assert _kind("talajon fekvő padló") == "Roof1"
    assert _kind("tető") == "Roof1"
    assert _kind("padló (talajra fektetett ISO 13370)") == "Roof1"
    assert _kind("talajjal érintkező fal (ISO 13370)") == "OutsideWall"
    assert _kind("ablak (külső, fa vagy PVC)") == "OutsideWindow"
    assert _kind("ajtó (külső)") == "OutsideDoor"


def test_explicit_glass_ratio_only_uses_structured_or_stated_source_value() -> None:
    assert _explicit_glass_ratio({"note": "90% üvegezési arány"}) == 90
    assert _explicit_glass_ratio({"glass_ratio_percent": 75}) == 75
    assert _explicit_glass_ratio({"note": "sablonérték 79%"}) is None


def test_rooflight_uses_a_window_panel_schema() -> None:
    assert _kind("felülvilágító") == "OutsideWindow"


def test_explicit_buildings_replace_the_legacy_single_project_building() -> None:
    model = {"project": {"name": "Legacy"}, "buildings": [{"name": "Meglévő"}, {"name": "Bővítmény"}]}
    assert [item["name"] for item in _building_specs(model)] == ["Meglévő", "Bővítmény"]
    assert _building_specs({"project": {"name": "Legacy", "address": "Cím"}}) == [{"name": "Legacy", "address": "Cím"}]


def test_boundary_uses_explicit_inclination_and_source_transmittance() -> None:
    assert _boundary_gradient({"inclination": "vertical"}) == 90
    assert _boundary_gradient({"inclination_deg": 10}) == 10
    assert _boundary_u({"u_layer": 1.277}) == 1.277
    assert _boundary_u({
        "linear_transmittance_w_mk": 2.555, "length_m": 5.9, "area_m2": 15.9,
    }) == 2.555 * 5.9 / 15.9


def test_native_integer_fields_are_lossless_and_fail_closed() -> None:
    assert _native_integer(90.0, "Gradient") == 90
    assert _native_integer("10", "Gradient") == 10

    import pytest

    with pytest.raises(ValueError, match="exact integer"):
        _native_integer(10.5, "Gradient")
