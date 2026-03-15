import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))
    package_dir = str(SRC_DIR / "winwatt_automation")
    package = sys.modules.get("winwatt_automation")
    if package is not None and hasattr(package, "__path__") and package_dir not in package.__path__:
        package.__path__.append(package_dir)

from winwatt_automation.parser.exporters import export_ui_model
from winwatt_automation.parser.semantic_classifier import classify_model
from winwatt_automation.parser.xml_parser import parse_hungarian_xml

if __name__ == "__main__":
    model = classify_model(parse_hungarian_xml(PROJECT_ROOT / "data/raw/Hungarian.xml"))
    out = export_ui_model(model, PROJECT_ROOT / "data/parsed/ui_model.json")
    print(f"UI model exported to {out}")
