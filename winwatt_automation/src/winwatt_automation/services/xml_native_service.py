"""Native WinWatt XML import/export adapter.

The adapter owns native menu IDs and common-dialog interaction.  Callers see
paths and evidence only; no UI handles or coordinates escape this boundary.
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from pathlib import Path

from pywinauto import Desktop

from winwatt_automation.domain.results import EvidenceItem
from winwatt_automation.live_ui.app_connector import (
    get_cached_main_window,
    get_main_window,
    reset_winwatt_connection_cache,
)
from winwatt_automation.workflows.safe_xml_export_probe import _find_save_dialog, _open_xml_export
from winwatt_automation.workflows.safe_xml_import_probe import _find_open_dialog, _open_xml_import


class NativeXmlService:
    """Perform actual XML file transfer through WinWatt's native commands."""

    @staticmethod
    def _filename_edit(dialog: object) -> object:
        edits = [item for item in dialog.descendants() if item.class_name() == "Edit" and item.is_visible()]
        if edits:
            return max(edits, key=lambda item: item.rectangle().top)
        return next(
            item for item in dialog.descendants(control_type="Edit")
            if str(item.element_info.automation_id) == "1001"
        )

    @staticmethod
    def _confirm_button(dialog: object) -> object:
        buttons = [item for item in dialog.descendants() if item.class_name() == "Button" and item.is_visible()]
        semantic = [item for item in buttons if item.window_text().strip().casefold() not in {"mégse", "cancel", "&mégse"}]
        if semantic:
            return max(semantic, key=lambda item: item.rectangle().left)
        return next(
            item for item in dialog.descendants(control_type="Button")
            if str(item.element_info.automation_id) == "1"
        )

    @staticmethod
    def _wait_for_dialog_to_close(process_id: int, _title: str, timeout: float = 8.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            visible = [
                item for item in Desktop(backend="uia").windows(top_level_only=True)
                if int(item.process_id()) == process_id and item.class_name() == "#32770"
                and item.is_visible()
            ]
            if not visible:
                return True
            time.sleep(0.1)
        return False

    def export_xml(self, target: Path) -> EvidenceItem:
        """Write one XML export and prove it is well-formed XML."""
        target = target.resolve()
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite existing XML export: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        # A Save As operation can invalidate a UIA wrapper while preserving
        # the live native main form.  Resolve a new wrapper rather than using
        # the strict cache guard intended for non-mutating probes.
        reset_winwatt_connection_cache()
        main = get_main_window()
        main.set_focus()
        process_id = int(main.process_id())
        _open_xml_export(main)
        dialog = _find_save_dialog(process_id, timeout=6.0)
        if dialog is None:
            raise RuntimeError("WinWatt XML Export save dialog did not open")
        self._filename_edit(dialog).set_edit_text(str(target))
        self._confirm_button(dialog).click_input()
        if not self._wait_for_dialog_to_close(process_id, "MentĂ©s mĂˇskĂ©nt"):
            raise RuntimeError("WinWatt XML Export dialog did not close after confirmation")
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline and not target.is_file():
            time.sleep(0.1)
        if not target.is_file():
            raise RuntimeError(f"WinWatt XML Export did not create {target}")
        try:
            root = ET.parse(target).getroot()
        except ET.ParseError as exc:
            raise RuntimeError(f"WinWatt XML Export produced malformed XML: {exc}") from exc
        return EvidenceItem(
            kind="xml_export",
            message="Native WinWatt XML export completed and parsed",
            data={"path": str(target), "root_tag": root.tag, "bytes": target.stat().st_size},
        )

    def import_xml(self, source: Path) -> EvidenceItem:
        """Import an existing, well-formed XML file through WinWatt's UI."""
        source = source.resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        try:
            root = ET.parse(source).getroot()
        except ET.ParseError as exc:
            raise ValueError(f"Refusing malformed XML import: {source}: {exc}") from exc
        reset_winwatt_connection_cache()
        main = get_main_window()
        main.set_focus()
        process_id = int(main.process_id())
        _open_xml_import(main)
        dialog = _find_open_dialog(process_id, timeout=6.0)
        if dialog is None:
            raise RuntimeError("WinWatt XML Import open dialog did not open")
        self._filename_edit(dialog).set_edit_text(str(source))
        self._confirm_button(dialog).click_input()
        if not self._wait_for_dialog_to_close(process_id, "Megnyitás"):
            raise RuntimeError("WinWatt XML Import dialog did not close after confirmation")
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if get_cached_main_window().is_enabled():
                return EvidenceItem(
                    kind="xml_import",
                    message="Native WinWatt XML import command completed",
                    data={"path": str(source), "root_tag": root.tag, "bytes": source.stat().st_size},
                )
            time.sleep(0.1)
        raise RuntimeError("WinWatt remained disabled after XML import")
