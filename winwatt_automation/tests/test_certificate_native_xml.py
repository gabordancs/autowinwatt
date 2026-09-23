from winwatt_automation.certificates.native_xml import _building_specs, _explicit_glass_ratio, _kind


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
