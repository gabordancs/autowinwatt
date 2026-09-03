from winwatt_automation.live_ui.native_menu import (
    is_reliable_native_menu_caption,
    normalize_native_menu_caption,
    verified_native_command,
)


def test_normalize_native_menu_caption_removes_accelerators():
    assert normalize_native_menu_caption("&Projekt && mentés") == "Projekt & mentés"


def test_reliable_native_menu_caption_rejects_empty_and_overlong_values():
    assert is_reliable_native_menu_caption("") is False
    assert is_reliable_native_menu_caption("&Fájl") is True
    assert is_reliable_native_menu_caption("x" * 161) is False
    assert is_reliable_native_menu_caption("FÄ‚Ë‡jl") is False


def test_verified_native_file_command_binding_is_explicit_and_scoped_to_parent():
    assert verified_native_command(1, 3)["stable_key"] == "MainForm.OpenProjekt"
    assert verified_native_command(32, 3) is None


def test_verified_native_project_data_command_has_runtime_evidence():
    command = verified_native_command(1, 7)

    assert command["stable_key"] == "MainForm.ProjektData"
    assert command["runtime_evidence"] == "project_data_dialog_detected_and_closed"


def test_verified_native_xml_export_command_has_runtime_evidence():
    command = verified_native_command(1, 9)

    assert command["stable_key"] == "MainForm.XMLExportAction"
    assert command["runtime_evidence"] == "xml_export_save_dialog_detected_and_cancelled"


def test_verified_native_about_command_has_runtime_evidence():
    command = verified_native_command(97, 99)

    assert command["stable_key"] == "MainForm.HelpAbout"
    assert command["runtime_evidence"] == "about_dialog_detected_and_closed"


def test_verified_native_program_options_command_has_runtime_evidence():
    command = verified_native_command(88, 89)

    assert command["stable_key"] == "MainForm.ProgramOptions"
    assert command["runtime_evidence"] == "program_options_dialog_detected_and_closed"


def test_verified_native_project_options_command_has_runtime_evidence():
    command = verified_native_command(88, 90)

    assert command["stable_key"] == "MainForm.ProjektOptions"
    assert command["runtime_evidence"] == "project_options_dialog_detected_and_closed"


def test_verified_native_help_content_command_has_runtime_evidence():
    command = verified_native_command(97, 98)

    assert command["stable_key"] == "MainForm.HelpContent"
    assert command["runtime_evidence"] == "winwatt_chm_help_window_detected_and_closed"
