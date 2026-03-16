from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from winwatt_automation.runtime_mapping.models import RuntimeStateDiff


def to_dict_dataclass(data: Any) -> Any:
    if is_dataclass(data):
        return asdict(data)
    if isinstance(data, list):
        return [to_dict_dataclass(item) for item in data]
    if isinstance(data, dict):
        return {key: to_dict_dataclass(value) for key, value in data.items()}
    return data


def write_json(path: str | Path, data: Any) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(to_dict_dataclass(data), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def write_markdown_summary(path: str | Path, diff: RuntimeStateDiff | dict[str, Any]) -> None:
    payload = to_dict_dataclass(diff)
    summary = payload.get("summary", {})
    lines = [
        "# Runtime state comparison",
        "",
        f"- State A: `{payload.get('state_a')}`",
        f"- State B: `{payload.get('state_b')}`",
        f"- Shared top menus: {summary.get('shared_top_menus', 0)}",
        f"- Actions only in A: {summary.get('actions_only_in_a', 0)}",
        f"- Actions only in B: {summary.get('actions_only_in_b', 0)}",
        f"- Dialogs only in A: {summary.get('dialogs_only_in_a', 0)}",
        f"- Dialogs only in B: {summary.get('dialogs_only_in_b', 0)}",
        f"- Windows only in A: {summary.get('windows_only_in_a', 0)}",
        f"- Windows only in B: {summary.get('windows_only_in_b', 0)}",
    ]
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_output_dirs(base_dir: str | Path) -> dict[str, Path]:
    base = Path(base_dir)
    no_project = base / "state_no_project"
    project_open = base / "state_project_open"
    diff_dir = base / "diff"
    for directory in (no_project, project_open, diff_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return {
        "base": base,
        "state_no_project": no_project,
        "state_project_open": project_open,
        "diff": diff_dir,
    }
