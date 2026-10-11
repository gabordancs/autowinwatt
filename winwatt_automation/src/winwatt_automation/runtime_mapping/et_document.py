"""Stable entry points for WinWatt's certification-document editor."""
from __future__ import annotations

import ctypes
import time
from pathlib import Path
from typing import Any

from pywinauto import Application
from pywinauto import Desktop
from pywinauto.controls.win32_controls import ComboBoxWrapper

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


def configure_et_scope(
    dialog: Any, *, building_name: str | None = None,
    zone_name: str | None = None, structure_scope: str = "all",
) -> dict[str, Any]:
    """Select a valid certificate scope before the wizard's Next action."""
    native = Desktop(backend="win32").window(handle=int(dialog.handle)).wrapper_object()
    combos = sorted(
        [item for item in native.descendants() if item.class_name() == "TComboBox" and item.is_visible()],
        key=lambda item: item.rectangle().top,
    )
    if len(combos) < 2:
        raise RuntimeError(f"Expected building and certification-zone selectors, found {len(combos)}")
    building = ComboBoxWrapper(combos[0].handle)
    building_values = [value for value in building.item_texts() if value.strip()]
    if not building_values:
        raise RuntimeError("The ET building selector is empty")
    chosen_building = building_name or building_values[-1]
    if chosen_building not in building_values:
        raise RuntimeError(f"Building {chosen_building!r} is absent from ET selector: {building_values!r}")
    building.select(chosen_building)
    time.sleep(0.5)

    # Selecting the building repopulates the dependent certification-zone
    # selector. A zone is optional because WinWatt also supports whole-building
    # certificates; when explicitly requested it becomes mandatory.
    native = Desktop(backend="win32").window(handle=int(dialog.handle)).wrapper_object()
    combos = sorted(
        [item for item in native.descendants() if item.class_name() == "TComboBox" and item.is_visible()],
        key=lambda item: item.rectangle().top,
    )
    zone = ComboBoxWrapper(combos[1].handle)
    zone_values = [value for value in zone.item_texts() if value.strip()]
    chosen_zone = None
    if zone_name is not None:
        matching_zones = [
            value for value in zone_values
            if value == zone_name or value.endswith(f" {zone_name}")
        ]
        if len(matching_zones) != 1:
            raise RuntimeError(f"Certification zone {zone_name!r} is absent: {zone_values!r}")
        zone.select(matching_zones[0])
        chosen_zone = matching_zones[0]
        time.sleep(0.25)

    labels = {
        "all": "Valamennyi",
        "heated_boundary": "Csak a fűtött teret határolók",
    }
    if structure_scope not in labels:
        raise ValueError(f"Unknown structure scope: {structure_scope!r}")
    scope_buttons = [
        item for item in native.descendants()
        if item.class_name() == "TButton" and item.window_text() == labels[structure_scope]
        and item.is_visible() and item.is_enabled()
    ]
    if len(scope_buttons) != 1:
        raise RuntimeError(f"Expected one structure-scope button {labels[structure_scope]!r}")
    scope_buttons[0].click()
    time.sleep(0.35)
    return {
        "building": chosen_building,
        "available_buildings": building_values,
        "zone": chosen_zone,
        "available_zones": zone_values,
        "structure_scope": structure_scope,
    }
