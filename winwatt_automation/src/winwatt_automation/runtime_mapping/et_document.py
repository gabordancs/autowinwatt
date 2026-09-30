"""Stable entry points for WinWatt's certification-document editor."""
from __future__ import annotations

import ctypes
import time
from pathlib import Path
from typing import Any

from pywinauto import Application

from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.runtime_mapping.program_mapper import prepare_fresh_winwatt_session
from winwatt_automation.runtime_mapping.room_deep_explorer import (
    _active_window,
    _dismiss_secondary_windows,
    _project_session_is_ready,
)


ET_COMMAND_ID = 18
ET_FORM_CLASS = "TETDocumentForm"


def active_et_window(process_id: int) -> Any:
    """Resolve the active ET form or a child dialog opened from it."""
    return _active_window(process_id)


def open_et_document(*, project_path: str, reuse_session: bool = True) -> Any:
    """Open File/ETAction using its verified native command id."""
    project = Path(project_path).resolve(strict=True)
    if reuse_session and _project_session_is_ready(str(project)):
        main = get_main_window()
        _dismiss_secondary_windows(int(main.process_id()), attempts=12)
    else:
        prepare_fresh_winwatt_session(project_path=str(project))
        main = get_main_window()

    process_id = int(main.process_id())
    native = Application(backend="win32").connect(process=process_id).window(
        handle=int(main.handle)
    )
    file_menu = next(
        item for item in native.menu().items()
        if int(item.item_id()) == 1
    )
    file_menu.click()
    time.sleep(0.15)
    et_item = next(
        item for item in file_menu.sub_menu().items()
        if int(item.item_id()) == ET_COMMAND_ID
    )
    if not et_item.is_enabled():
        raise RuntimeError("ETAction command 18 is disabled for the opened project")
    et_item.click()

    # Owner-drawn Delphi menus occasionally acknowledge pywinauto's click
    # without dispatching the TAction.  Command 18 is version-profile bound
    # and independently verified, so use WM_COMMAND as a deterministic retry.
    time.sleep(0.4)
    first_observed = _active_window(process_id)
    if first_observed.class_name() != ET_FORM_CLASS:
        if not ctypes.windll.user32.PostMessageW(int(main.handle), 0x0111, ET_COMMAND_ID, 0):
            raise ctypes.WinError()

    deadline = time.monotonic() + 15.0
    observed: Any | None = None
    while time.monotonic() < deadline:
        try:
            observed = _active_window(process_id)
        except RuntimeError:
            # Delphi disables the main form just before publishing the modal
            # ET window, leaving a brief interval with no enabled top-level.
            time.sleep(0.15)
            continue
        if observed.class_name() == ET_FORM_CLASS:
            return observed
        time.sleep(0.15)
    raise RuntimeError(
        f"ETAction did not open {ET_FORM_CLASS}; observed "
        f"{observed.class_name() if observed is not None else None!r}"
    )
