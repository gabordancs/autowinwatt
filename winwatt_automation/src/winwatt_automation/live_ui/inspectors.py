from __future__ import annotations

from pathlib import Path

from winwatt_automation.live_ui.window_tree import save_window_tree_snapshot
from winwatt_automation.scripts.inspect_live_ui import _save_control_names, _save_main_window_screenshot


def inspect_live_ui_tree(output_path: str | Path) -> dict:
    """Capture the current WinWatt UI Automation tree and persist it to JSON."""

    return save_window_tree_snapshot(Path(output_path))


def export_control_names(snapshot: dict, output_path: str | Path) -> Path:
    """Persist the unique control names discovered in a UI snapshot."""

    return _save_control_names(snapshot, Path(output_path))


def capture_main_window_screenshot(output_path: str | Path) -> Path:
    """Save a screenshot of the current WinWatt main window."""

    return _save_main_window_screenshot(Path(output_path))
