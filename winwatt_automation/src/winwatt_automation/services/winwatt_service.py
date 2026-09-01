from __future__ import annotations

import shutil
import time
from pathlib import Path

from pywinauto import Application, keyboard
from pywinauto import Desktop

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
        """Execute the verified native File → Save project command.

        Ctrl+S is accepted by the window but was not evidence that the legacy
        application's project action ran.  Command id 4 under the native File
        menu (parent id 1) is the mapped `MainForm.SaveProjekt` action.
        """
        main = get_main_window()
        native = Application(backend="win32").connect(process=int(main.process_id())).window(handle=int(main.handle))
        file_menu = next(item for item in native.menu().items() if item.item_id() == 1)
        file_menu.click()
        time.sleep(0.15)
        save_item = next(item for item in file_menu.sub_menu().items() if item.item_id() == 4)
        if not save_item.is_enabled():
            raise RuntimeError("WinWatt native SaveProjekt command is disabled")
        save_item.click()
        time.sleep(2.0)

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

    def save_project_as(self, target_path: Path) -> Path:
        """Persist through the verified Hungarian Save-As common dialog."""
        target = target_path.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        main = get_main_window()
        process_id = int(main.process_id())
        native = Application(backend="win32").connect(process=process_id).window(handle=int(main.handle))
        file_menu = next(item for item in native.menu().items() if item.item_id() == 1)
        file_menu.click(); time.sleep(0.15)
        next(item for item in file_menu.sub_menu().items() if item.item_id() == 5).click()
        deadline = time.monotonic() + 6.0
        dialog = None
        while time.monotonic() < deadline:
            dialogs = [item for item in Desktop(backend="uia").windows(top_level_only=True) if item.process_id() == process_id and item.class_name() == "#32770" and "mentés másként" in item.window_text().casefold()]
            if dialogs:
                dialog = dialogs[0]
                break
            time.sleep(0.1)
        if dialog is None:
            raise RuntimeError("WinWatt Save-As dialog did not open")
        filename = dialog.child_window(auto_id="1001", control_type="Edit")
        filename.set_edit_text(str(target))
        dialog.child_window(auto_id="1", control_type="Button").click_input()
        time.sleep(2.0)
        if not target.is_file():
            raise RuntimeError(f"WinWatt Save-As did not create {target}")
        return target
