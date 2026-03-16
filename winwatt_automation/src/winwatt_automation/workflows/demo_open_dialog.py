"""Demo workflow: open WinWatt's project-open dialog from the Fájl menu."""

from __future__ import annotations

from winwatt_automation.commands.menu_commands import invoke_open_project_dialog, open_file_menu
from winwatt_automation.live_ui.app_connector import connect_to_winwatt
from winwatt_automation.live_ui.waits import wait_for_dialog


def run_demo_open_dialog(timeout: float = 5.0):
    """Open the project-open dialog and return the dialog wrapper."""

    connect_to_winwatt()
    open_file_menu()
    invoke_open_project_dialog()
    return wait_for_dialog(timeout=timeout)
