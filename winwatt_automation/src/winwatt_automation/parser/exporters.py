from __future__ import annotations

import json
from pathlib import Path

from winwatt_automation.models.ui_models import UIModel


def export_ui_model(model: UIModel, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(model.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
    return output
