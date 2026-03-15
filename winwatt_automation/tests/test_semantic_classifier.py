from pathlib import Path

from winwatt_automation.parser.semantic_classifier import classify_model
from winwatt_automation.parser.xml_parser import parse_hungarian_xml


def test_semantic_classification_and_stable_keys():
    model = classify_model(parse_hungarian_xml(Path("data/raw/Hungarian.xml")))
    main_form = next(form for form in model.forms if form.name == "MainForm")
    open_button = next(item for item in main_form.items if item.name == "OpenProjekt")

    assert open_button.semantic_role == "action"
    assert open_button.normalized_name == "open_projekt"
    assert open_button.stable_key == "MainForm.OpenProjekt"
