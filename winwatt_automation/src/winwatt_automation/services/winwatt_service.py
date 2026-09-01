from __future__ import annotations

import shutil
import time
from pathlib import Path

from pywinauto import keyboard

from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.runtime_mapping.program_mapper import prepare_fresh_winwatt_session


class WinWattService:
    """Small semantic boundary around project/session operations."""

    def create_sandbox(self, source_project: Path, sandbox_project: Path) -> Path:
        source = source_project.resolve()
        target = sandbox_project.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Project template does not exist: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target

    def open_project(self, project_path: Path) -> None:
        prepare_fresh_winwatt_session(project_path=str(project_path.resolve()))

    def save_project(self) -> None:
        main = get_main_window()
        main.set_focus()
        keyboard.send_keys("^s")
        time.sleep(1.5)

    def close_project_gracefully(self) -> None:
        """Let WinWatt flush its project file before a restart verification.

        ``prepare_fresh_winwatt_session`` deliberately kills stale processes
        for mapping recovery. That is unsuitable immediately after a write:
        old WinWatt builds may still have pending file serialization after
        Ctrl+S. Close the saved project through its normal application route
        first; the next open remains a defensive fallback only.
        """
        main = get_main_window()
        main.set_focus()
        keyboard.send_keys("%{F4}")
        time.sleep(2.0)
