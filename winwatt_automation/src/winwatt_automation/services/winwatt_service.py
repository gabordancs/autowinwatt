from __future__ import annotations

import shutil
import time
from dataclasses import asdict
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

    def reopen_sandbox_project_in_current_session(self, project_path: Path) -> dict[str, object]:
        """Reopen a sandbox project without deliberately killing WinWatt.

        ``open_project`` is the recovery hammer: its legacy bootstrap kills
        stale processes by design.  Recursive read-only navigation needs a
        cheaper recovery first.  This uses the already verified native project
        open dialog inside the currently owned process and accepts success only
        when the same process remains alive and the normalized path matches.
        """
        target = project_path.resolve()
        if "sandbox" not in {part.casefold() for part in target.parts}:
            raise ValueError("current-session reopen requires a sandbox project")
        from winwatt_automation.live_ui.file_dialog import open_project_file_via_dialog_dict
        from winwatt_automation.runtime_mapping.program_mapper import capture_state_snapshot

        before_main = get_main_window()
        before_pid = int(before_main.process_id())
        before = asdict(capture_state_snapshot("recursive_reopen_before"))
        result = open_project_file_via_dialog_dict(
            str(target),
            before_snapshot=before,
            after_snapshot_provider=lambda: asdict(capture_state_snapshot("recursive_reopen_after")),
        )
        if not result.get("success") or not result.get("path_match_normalized"):
            return {"success": False, "same_process": False, "reason": result.get("error") or "open_dialog_verification_failed"}
        try:
            after_main = get_main_window()
            same_process = int(after_main.process_id()) == before_pid
        except Exception as exc:
            return {"success": False, "same_process": False, "reason": f"main_window_after_reopen_unavailable: {exc!r}"}
        return {"success": bool(same_process), "same_process": bool(same_process), "reason": None if same_process else "process_changed"}

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
        filename = next(item for item in dialog.descendants(control_type="Edit") if item.element_info.automation_id == "1001")
        filename.set_edit_text(str(target))
        save_button = next(item for item in dialog.descendants(control_type="Button") if item.element_info.automation_id == "1")
        save_button.click_input()
        time.sleep(2.0)
        if not target.is_file():
            raise RuntimeError(f"WinWatt Save-As did not create {target}")
        return target
