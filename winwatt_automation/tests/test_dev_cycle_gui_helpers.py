from __future__ import annotations

from winwatt_automation.controller.gui_helpers import build_map_command, command_preview


def test_build_map_command_matches_manual_style():
    command = build_map_command(
        python_executable=r"C:\\Users\\dancsg\\AppData\\Local\\Programs\\Python\\Python314\\python.exe",
        safe_mode="safe",
    )

    assert command == [
        r"C:\\Users\\dancsg\\AppData\\Local\\Programs\\Python\\Python314\\python.exe",
        "-m",
        "winwatt_automation.scripts.map_full_program",
        "--safe-mode",
        "safe",
    ]


def test_build_map_command_includes_project_path_when_provided():
    command = build_map_command(
        python_executable="python",
        safe_mode="off",
        project_path=r"C:\\projects\\mintaprojekt.wwp",
    )

    assert command == [
        "python",
        "-m",
        "winwatt_automation.scripts.map_full_program",
        "--safe-mode",
        "off",
        "--project-path",
        r"C:\\projects\\mintaprojekt.wwp",
    ]


def test_preview_contains_module_name():
    preview = command_preview(build_map_command("python", "caution", "--max-submenu-depth 2"))
    assert "winwatt_automation.scripts.map_full_program" in preview
    assert "--safe-mode caution" in preview
    assert "--max-submenu-depth 2" in preview
