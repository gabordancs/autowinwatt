from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from winwatt_automation.config import PARSED_DATA_DIR, RAW_DATA_DIR
from winwatt_automation.parser.catalog_builder import (
    build_actions_catalog,
    build_controls_catalog,
    build_dialog_catalog,
    build_forms_catalog,
    build_menu_tree,
    build_static_runtime_map,
    build_workflow_seeds,
)
from winwatt_automation.parser.semantic_classifier import classify_model
from winwatt_automation.parser.xml_parser import parse_hungarian_xml


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def build_program_map(xml_path: Path = RAW_DATA_DIR / "Hungarian.xml", output_dir: Path = PARSED_DATA_DIR) -> dict[str, Any]:
    ui_model = classify_model(parse_hungarian_xml(xml_path))

    forms_catalog = build_forms_catalog(ui_model)
    controls_catalog = build_controls_catalog(ui_model)
    actions_catalog = build_actions_catalog(ui_model)
    menu_tree = build_menu_tree(ui_model)
    dialog_catalog = build_dialog_catalog(ui_model)
    workflow_seeds = build_workflow_seeds(ui_model)
    static_runtime_map = build_static_runtime_map(ui_model)

    outputs = {
        "forms_catalog": _write_json(output_dir / "forms_catalog.json", forms_catalog),
        "controls_catalog": _write_json(output_dir / "controls_catalog.json", controls_catalog),
        "actions_catalog": _write_json(output_dir / "actions_catalog.json", actions_catalog),
        "menu_tree": _write_json(output_dir / "menu_tree.json", menu_tree),
        "dialog_catalog": _write_json(output_dir / "dialog_catalog.json", dialog_catalog),
        "workflow_seeds": _write_json(output_dir / "workflow_seeds.json", workflow_seeds),
        "static_runtime_map": _write_json(output_dir / "static_runtime_map.json", static_runtime_map),
    }

    return {
        "outputs": outputs,
        "counts": {
            "forms": len(forms_catalog),
            "controls": len(controls_catalog),
            "actions": len(actions_catalog),
            "dialogs": len(dialog_catalog),
            "workflow_seeds": len(workflow_seeds),
        },
    }
