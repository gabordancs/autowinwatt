from __future__ import annotations

from pathlib import Path

from winwatt_automation.scripts import inspect_live_ui


def test_save_control_names_writes_unique_sorted_names(tmp_path: Path):
    snapshot = {
        "name": "Main",
        "children": [
            {"name": "Save", "children": []},
            {"name": "Open", "children": [{"name": "Save", "children": []}]},
            {"name": "", "children": []},
        ],
    }

    output = inspect_live_ui._save_control_names(snapshot, tmp_path / "control_names.txt")

    assert output.exists()
    assert output.read_text(encoding="utf-8").splitlines() == ["Main", "Open", "Save"]


def test_build_parser_supports_screenshot_flag():
    parser = inspect_live_ui._build_parser()

    args = parser.parse_args(["--screenshot"])

    assert args.screenshot is True
    assert args.no_controls_export is False
