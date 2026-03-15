from pathlib import Path

from winwatt_automation.parser.exporters import export_ui_model
from winwatt_automation.parser.semantic_classifier import classify_model
from winwatt_automation.parser.xml_parser import parse_hungarian_xml

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    model = classify_model(parse_hungarian_xml(PROJECT_ROOT / "data/raw/Hungarian.xml"))
    output_path = export_ui_model(model, PROJECT_ROOT / "data/parsed/ui_model.json")
    print(f"Exported: {output_path}")


if __name__ == "__main__":
    main()
