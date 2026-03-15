from pathlib import Path

from winwatt_automation.parser.xml_parser import parse_hungarian_xml


def test_parse_hungarian_xml_extracts_forms_and_items():
    xml_path = Path("data/raw/Hungarian.xml")
    model = parse_hungarian_xml(xml_path)

    assert len(model.forms) >= 2
    assert any(form.name == "MainForm" for form in model.forms)

    main_form = next(form for form in model.forms if form.name == "MainForm")
    assert any(item.name == "OpenProjekt" for item in main_form.items)
