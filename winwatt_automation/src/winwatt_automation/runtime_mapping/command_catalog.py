"""Evidence-backed command catalog for safe WinWatt automation."""

from __future__ import annotations

from typing import Any

from winwatt_automation.live_ui.native_menu import VERIFIED_NATIVE_COMMANDS


SAFE_WORKFLOWS: dict[str, dict[str, Any]] = {
    "MainForm.NewProjekt": {
        "workflow": "safe_new_project_probe",
        "callable": "winwatt_automation.workflows.safe_new_project_probe.run_safe_new_project_probe",
        "safety_level": "probe_only",
        "allowed_effect": "open_and_cancel_file_dialog",
        "forbidden_effects": ["confirm_file_name", "create_project", "save_project"],
        "postconditions": ["dialog_dismissed", "main_window_enabled_after"],
    },
    "MainForm.OpenProjekt": {
        "workflow": "safe_project_open_probe",
        "callable": "winwatt_automation.workflows.safe_project_open_probe.run_safe_project_open_probe",
        "safety_level": "probe_only",
        "allowed_effect": "open_and_cancel_project_open_dialog",
        "forbidden_effects": ["select_project", "confirm_file_name", "modify_project"],
        "postconditions": ["dialog_dismissed", "main_window_enabled_after"],
    },
    "MainForm.HelpAbout": {
        "workflow": "safe_about_probe",
        "callable": "winwatt_automation.workflows.safe_about_probe.run_safe_about_probe",
        "safety_level": "read_only_dialog",
        "allowed_effect": "open_and_close_about_dialog",
        "forbidden_effects": ["modify_project", "modify_settings"],
        "postconditions": ["dialog_dismissed", "main_window_enabled_after"],
    },
    "MainForm.ProgramOptions": {
        "workflow": "safe_program_options_probe",
        "callable": "winwatt_automation.workflows.safe_program_options_probe.run_safe_program_options_probe",
        "safety_level": "read_only_dialog",
        "allowed_effect": "open_inspect_and_close_program_options",
        "forbidden_effects": ["change_control_value", "press_ok", "save_settings"],
        "postconditions": ["dialog_dismissed", "main_window_enabled_after"],
    },
    "MainForm.ProjektOptions": {
        "workflow": "safe_project_options_probe",
        "callable": "winwatt_automation.workflows.safe_project_options_probe.run_safe_project_options_probe",
        "safety_level": "read_only_dialog",
        "allowed_effect": "open_inspect_and_close_project_options",
        "forbidden_effects": ["change_control_value", "press_ok", "load_settings", "save_settings"],
        "postconditions": ["dialog_dismissed", "main_window_enabled_after"],
    },
    "MainForm.HelpContent": {
        "workflow": "safe_help_content_probe",
        "callable": "winwatt_automation.workflows.safe_help_content_probe.run_safe_help_content_probe",
        "safety_level": "read_only_external_window",
        "allowed_effect": "open_inspect_and_close_new_winwatt_chm_help_window",
        "forbidden_effects": ["interact_with_preexisting_help_window", "modify_project", "modify_settings"],
        "postconditions": ["help_dismissed", "main_window_enabled_after"],
    },
    "MainForm.ProjektData": {
        "workflow": "safe_project_data_probe",
        "callable": "winwatt_automation.workflows.safe_project_data_probe.run_safe_project_data_probe",
        "safety_level": "read_only_dialog_privacy_preserving",
        "allowed_effect": "open_inspect_structural_metadata_and_close_project_data",
        "forbidden_effects": ["read_or_emit_field_values", "change_control_value", "press_ok", "clipboard_import", "clipboard_export"],
        "postconditions": ["dialog_dismissed", "main_window_enabled_after"],
    },
    "MainForm.XMLExportAction": {
        "workflow": "safe_xml_export_probe",
        "callable": "winwatt_automation.workflows.safe_xml_export_probe.run_safe_xml_export_probe",
        "safety_level": "probe_only",
        "allowed_effect": "open_and_cancel_xml_export_save_dialog",
        "forbidden_effects": ["confirm_file_name", "write_export_file", "overwrite_existing_file"],
        "postconditions": ["dialog_dismissed", "main_window_enabled_after"],
    },
    "MainForm.XMLImportAction": {
        "workflow": "safe_xml_import_probe",
        "callable": "winwatt_automation.workflows.safe_xml_import_probe.run_safe_xml_import_probe",
        "safety_level": "probe_only",
        "allowed_effect": "open_and_cancel_xml_import_file_dialog",
        "forbidden_effects": ["select_file", "confirm_import", "modify_project"],
        "postconditions": ["dialog_dismissed", "main_window_enabled_after"],
    },
    "MainForm.CreateReportAction": {
        "workflow": "safe_custom_reports_probe",
        "callable": "winwatt_automation.workflows.safe_custom_reports_probe.run_safe_custom_reports_probe",
        "safety_level": "probe_only",
        "allowed_effect": "open_and_cancel_custom_report_template_picker",
        "forbidden_effects": ["select_report_template", "create_report", "write_report_file"],
        "postconditions": ["dialog_dismissed", "main_window_enabled_after"],
    },
}

UNEXPOSED_OBSERVATIONS: list[dict[str, Any]] = [
    {
        "stable_key": "MainForm.DatabaseAction",
        "item_name": "DatabaseAction",
        "native_menu": {"parent_command_id": None, "command_id": 87},
        "static_caption": "Adatbázis...",
        "runtime_observation": "native invocation produced no modal or separate top-level window within 0.8 seconds; main window remained enabled",
        "admission": "not_exposed",
        "reason": "possible internal MDI transition is not yet identified or reversible",
    }
]


def build_runtime_command_catalog(*, application: str = "WinWatt gólya", version: str = "9.60") -> dict[str, Any]:
    """Return only commands with explicit native and runtime evidence."""
    commands: list[dict[str, Any]] = []
    for (parent_command_id, command_id), binding in sorted(VERIFIED_NATIVE_COMMANDS.items()):
        stable_key = binding["stable_key"]
        workflow = SAFE_WORKFLOWS.get(stable_key)
        if workflow is None:
            continue
        commands.append(
            {
                "stable_key": stable_key,
                "item_name": binding["item_name"],
                "native_menu": {"parent_command_id": parent_command_id, "command_id": command_id},
                "binding_verification": binding["verification"],
                "runtime_evidence": binding.get("runtime_evidence"),
                **workflow,
            }
        )
    return {
        "schema_version": 1,
        "application": application,
        "version": version,
        "catalog_policy": "Only entries with a verified native binding and an explicitly constrained safe workflow are exposed.",
        "commands": commands,
        "unexposed_observations": UNEXPOSED_OBSERVATIONS,
    }
