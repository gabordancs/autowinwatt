"""Read WinWatt's native Win32 menu structure without invoking commands."""

from __future__ import annotations

import re
from typing import Any


_ACCELERATOR_PATTERN = re.compile(r"&(?!&)")

# These bindings were verified visually against WinWatt gólya 9.60 and matched
# to MainForm TAction entries in Hungarian.xml.  They are intentionally scoped
# to their observed native parent command IDs; unknown IDs remain unbound.
VERIFIED_NATIVE_COMMANDS: dict[tuple[int, int], dict[str, str]] = {
    (1, 2): {
        "item_name": "NewProjekt",
        "stable_key": "MainForm.NewProjekt",
        "verification": "visual_static_xml_and_runtime_dialog_probe",
        "runtime_evidence": "new_project_dialog_detected_and_cancelled",
    },
    (
        1,
        3,
    ): {
        "item_name": "OpenProjekt",
        "stable_key": "MainForm.OpenProjekt",
        "verification": "visual_static_xml_and_runtime_dialog_probe",
        "runtime_evidence": "project_open_dialog_detected_and_cancelled",
    },
    (1, 4): {"item_name": "SaveProjekt", "stable_key": "MainForm.SaveProjekt", "verification": "visual_and_static_xml"},
    (1, 6): {"item_name": "CloseProjekt", "stable_key": "MainForm.CloseProjekt", "verification": "visual_and_static_xml"},
    (1, 7): {
        "item_name": "ProjektData",
        "stable_key": "MainForm.ProjektData",
        "verification": "visual_static_xml_and_runtime_dialog_probe",
        "runtime_evidence": "project_data_dialog_detected_and_closed",
    },
    (1, 9): {
        "item_name": "XMLExportAction",
        "stable_key": "MainForm.XMLExportAction",
        "verification": "visual_static_xml_and_runtime_dialog_probe",
        "runtime_evidence": "xml_export_save_dialog_detected_and_cancelled",
    },
    (1, 10): {
        "item_name": "XMLImportAction",
        "stable_key": "MainForm.XMLImportAction",
        "verification": "visual_static_xml_and_runtime_dialog_probe",
        "runtime_evidence": "xml_import_open_dialog_detected_and_cancelled",
    },
    (1, 8): {"item_name": "DeleteProjekt", "stable_key": "MainForm.DeleteProjekt", "verification": "visual_and_static_xml"},
    (1, 18): {"item_name": "ETAction", "stable_key": "MainForm.ETAction", "verification": "visual_and_static_xml"},
    (1, 19): {
        "item_name": "CreateReportAction",
        "stable_key": "MainForm.CreateReportAction",
        "verification": "visual_static_xml_and_runtime_dialog_probe",
        "runtime_evidence": "custom_reports_template_picker_detected_and_cancelled",
    },
    (1, 31): {"item_name": "ExitApplication", "stable_key": "MainForm.ExitApplication", "verification": "visual_and_static_xml"},
    (97, 99): {
        "item_name": "HelpAbout",
        "stable_key": "MainForm.HelpAbout",
        "verification": "visual_static_xml_and_runtime_dialog_probe",
        "runtime_evidence": "about_dialog_detected_and_closed",
    },
    (97, 98): {
        "item_name": "HelpContent",
        "stable_key": "MainForm.HelpContent",
        "verification": "visual_static_xml_and_runtime_window_probe",
        "runtime_evidence": "winwatt_chm_help_window_detected_and_closed",
    },
    (88, 89): {
        "item_name": "ProgramOptions",
        "stable_key": "MainForm.ProgramOptions",
        "verification": "visual_static_xml_and_runtime_dialog_probe",
        "runtime_evidence": "program_options_dialog_detected_and_closed",
    },
    (88, 90): {
        "item_name": "ProjektOptions",
        "stable_key": "MainForm.ProjektOptions",
        "verification": "visual_static_xml_and_runtime_dialog_probe",
        "runtime_evidence": "project_options_dialog_detected_and_closed",
    },
}


def normalize_native_menu_caption(value: str | None) -> str:
    """Remove Win32 accelerator markers while preserving display text."""

    escaped_ampersand = "\0"
    text = str(value or "").replace("&&", escaped_ampersand)
    return _ACCELERATOR_PATTERN.sub("", text).replace(escaped_ampersand, "&").strip()


def is_reliable_native_menu_caption(value: str | None) -> bool:
    """Return false for empty or clearly corrupted owner-drawn menu text."""

    text = normalize_native_menu_caption(value)
    if not text:
        return False

    printable = sum(character.isprintable() for character in text)
    if printable / len(text) < 0.95:
        return False

    if any(character in text for character in {"Ã", "Â", "Ä", "Ë", "�"}):
        return False

    # Legacy owner-drawn text sometimes arrives as a repeated, long garbage string.
    return len(text) <= 160


def verified_native_command(parent_command_id: int | None, command_id: int | None) -> dict[str, str] | None:
    """Return an explicit, evidence-backed static binding for a native menu item."""

    if parent_command_id is None or command_id is None:
        return None
    binding = VERIFIED_NATIVE_COMMANDS.get((int(parent_command_id), int(command_id)))
    return dict(binding) if binding else None


def _item_payload(item: Any, index: int, parent_command_id: int | None = None) -> dict[str, Any]:
    raw_text = item.text()
    submenu = item.sub_menu()
    command_id = int(item.item_id())
    children = [_item_payload(child, child_index, command_id) for child_index, child in enumerate(submenu.items())] if submenu else []
    return {
        "index": index,
        "command_id": command_id,
        "caption_raw": raw_text,
        "caption": normalize_native_menu_caption(raw_text),
        "caption_reliable": is_reliable_native_menu_caption(raw_text),
        "enabled": bool(item.is_enabled()),
        "verified_static_binding": verified_native_command(parent_command_id, command_id),
        "children": children,
    }


def enumerate_native_menu(main_window: Any | None = None) -> dict[str, Any]:
    """Return the native menu hierarchy and command IDs without clicking any item."""

    if main_window is None:
        from winwatt_automation.live_ui.app_connector import get_cached_main_window

        main_window = get_cached_main_window()

    from pywinauto import Application

    process_id = int(main_window.process_id())
    handle = int(main_window.handle)
    window = Application(backend="win32").connect(process=process_id).window(handle=handle)
    menu = window.menu()
    return {
        "backend": "win32_native_menu",
        "process_id": process_id,
        "window_handle": handle,
        "items": [_item_payload(item, index) for index, item in enumerate(menu.items())],
    }
