from winwatt_automation.runtime_mapping.mdi_state_model import _slug, diff_menu_structures


def test_mdi_state_slug_is_stable_and_ascii() -> None:
    assert _slug("Helyiségek") == "helyisegek"


def test_menu_structure_diff_records_first_state() -> None:
    current = [{"index": 0, "caption": "Fájl", "children": []}]
    result = diff_menu_structures(None, current)
    assert result["kind"] == "initial_state"
    assert result["changed"] is True


def test_menu_structure_diff_ignores_equal_state() -> None:
    current = [{"index": 0, "caption": "Fájl", "children": []}]
    result = diff_menu_structures(current, current)
    assert result["kind"] == "menu_structure_diff"
    assert result["changed"] is False
    assert result["current"] is None


def test_menu_structure_diff_records_change() -> None:
    previous = [{"index": 0, "caption": "Fájl", "children": []}]
    current = [{"index": 0, "caption": "Fájl", "children": []}, {"index": 1, "caption": "Elem", "children": []}]
    result = diff_menu_structures(previous, current)
    assert result["changed"] is True
    assert result["previous"] == previous
    assert result["current"] == current
