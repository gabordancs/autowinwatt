from pathlib import Path

from winwatt_automation.commands.registry import CommandRegistry
from winwatt_automation.parser.semantic_classifier import classify_model
from winwatt_automation.parser.xml_parser import parse_hungarian_xml


def test_command_registry_searches_by_multiple_fields():
    model = classify_model(parse_hungarian_xml(Path("data/raw/Hungarian.xml")))
    registry = CommandRegistry()
    registry.build_from_ui_model(model)

    assert registry.find_by_name("OpenProjekt")
    assert registry.find_by_form("MainForm")
    assert registry.find_by_caption("Save Project")
    assert registry.find_by_item_type("TAction")
