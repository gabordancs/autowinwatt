from pathlib import Path

from winwatt_automation.parser.exporters import export_ui_model
from winwatt_automation.parser.semantic_classifier import classify_model
from winwatt_automation.parser.xml_parser import parse_hungarian_xml

if __name__ == "__main__":
    model = classify_model(parse_hungarian_xml(Path("data/raw/Hungarian.xml")))
    out = export_ui_model(model, Path("data/parsed/ui_model.json"))
    print(f"Exported: {out}")
