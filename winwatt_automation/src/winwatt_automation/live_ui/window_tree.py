"""Window tree dumping and snapshot utilities for live UI automation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from winwatt_automation.live_ui.app_connector import get_main_window


def _safe_control_type(element_info: Any) -> str | None:
    control_type = getattr(element_info, "control_type", None)
    if control_type:
        return str(control_type)

    fallback = getattr(element_info, "friendly_class_name", None)
    if callable(fallback):
        try:
            return str(fallback())
        except Exception:
            return None
    return None


def _node_from_window(window: Any) -> dict[str, Any]:
    element_info = getattr(window, "element_info", window)
    name = getattr(element_info, "name", None) or getattr(element_info, "rich_text", None)

    return {
        "name": name,
        "control_type": _safe_control_type(element_info),
        "class_name": getattr(element_info, "class_name", None),
        "automation_id": getattr(element_info, "automation_id", None),
        "children": [],
    }


def dump_window_tree(window: Any, max_depth: int = 5) -> dict[str, Any]:
    """Recursively dump a window/control subtree into a JSON-serializable dict."""

    root = _node_from_window(window)
    if max_depth <= 0:
        return root

    for child in window.children():
        root["children"].append(dump_window_tree(child, max_depth=max_depth - 1))
    return root


def save_window_tree_snapshot(output_path: str | Path) -> dict[str, Any]:
    """Capture and save the main window tree snapshot to ``output_path``."""

    main_window = get_main_window()
    snapshot = dump_window_tree(main_window)

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("Saved UI tree snapshot to {}", output_file)
    return snapshot
