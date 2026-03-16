"""Workflow: trigger project-open dialog from Fájl submenu by popup index."""

from __future__ import annotations

from typing import Any

from loguru import logger

from winwatt_automation.commands.menu_commands import invoke_open_project_dialog_by_index
from winwatt_automation.live_ui.app_connector import connect_to_winwatt, prepare_main_window_for_menu_interaction

OPEN_PROJECT_INDEX = 1


def run_demo_open_project_dialog_by_index(index: int = OPEN_PROJECT_INDEX) -> dict[str, Any]:
    connect_to_winwatt()
    prepare_main_window_for_menu_interaction()

    result = invoke_open_project_dialog_by_index(index)
    if result.get("dialog_detected"):
        logger.info("Open-project dialog detected for index={} title={}", index, result.get("dialog_title"))
    else:
        logger.warning("No open-project dialog detected for index={}", index)
    return result
