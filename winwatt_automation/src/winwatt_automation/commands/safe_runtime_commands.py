"""Strict, logged dispatch of the evidence-backed safe WinWatt commands."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from winwatt_automation.runtime_logging.run_recorder import finalize_run, record_event, start_run, update_status
from winwatt_automation.workflows.safe_about_probe import run_safe_about_probe
from winwatt_automation.workflows.safe_custom_reports_probe import run_safe_custom_reports_probe
from winwatt_automation.workflows.safe_help_content_probe import run_safe_help_content_probe
from winwatt_automation.workflows.safe_new_project_probe import run_safe_new_project_probe
from winwatt_automation.workflows.safe_program_options_probe import run_safe_program_options_probe
from winwatt_automation.workflows.safe_project_data_probe import run_safe_project_data_probe
from winwatt_automation.workflows.safe_project_open_probe import run_safe_project_open_probe
from winwatt_automation.workflows.safe_project_options_probe import run_safe_project_options_probe
from winwatt_automation.workflows.safe_xml_export_probe import run_safe_xml_export_probe
from winwatt_automation.workflows.safe_xml_import_probe import run_safe_xml_import_probe

SafeWorkflow = Callable[[], dict[str, Any]]

_COMMANDS: dict[str, tuple[str, SafeWorkflow]] = {
    "uj projekt ellenorzese": ("MainForm.NewProjekt", run_safe_new_project_probe),
    "új projekt ellenőrzése": ("MainForm.NewProjekt", run_safe_new_project_probe),
    "projekt megnyitasa ellenorzese": ("MainForm.OpenProjekt", run_safe_project_open_probe),
    "projekt megnyitása ellenőrzése": ("MainForm.OpenProjekt", run_safe_project_open_probe),
    "nevjegy": ("MainForm.HelpAbout", run_safe_about_probe),
    "névjegy": ("MainForm.HelpAbout", run_safe_about_probe),
    "program beallitasok ellenorzese": ("MainForm.ProgramOptions", run_safe_program_options_probe),
    "program beállítások ellenőrzése": ("MainForm.ProgramOptions", run_safe_program_options_probe),
    "projekt beallitasok ellenorzese": ("MainForm.ProjektOptions", run_safe_project_options_probe),
    "projekt adatok ellenorzese": ("MainForm.ProjektData", run_safe_project_data_probe),
    "sugo tartalom ellenorzese": ("MainForm.HelpContent", run_safe_help_content_probe),
    "xml export ellenorzese": ("MainForm.XMLExportAction", run_safe_xml_export_probe),
    "xml import ellenorzese": ("MainForm.XMLImportAction", run_safe_xml_import_probe),
    "egyedi riport sablon ellenorzese": ("MainForm.CreateReportAction", run_safe_custom_reports_probe),
}


def resolve_safe_command(text: str) -> tuple[str, SafeWorkflow] | None:
    """Resolve an exact approved Hungarian command; never infer a mutating action."""
    return _COMMANDS.get(" ".join((text or "").strip().lower().split()))


def execute_safe_command(text: str) -> dict[str, Any]:
    """Execute an approved constrained workflow and persist an auditable run log."""
    resolved = resolve_safe_command(text)
    if resolved is None:
        return {
            "accepted": False,
            "success": False,
            "reason": "unknown_or_unsafe_command",
            "input": text,
            "allowed_commands": sorted(_COMMANDS),
        }

    stable_key, workflow = resolved
    run_ctx = start_run(
        f"safe_runtime_command {stable_key}",
        {"safe_mode": "safe", "tags": ["safe_command", stable_key]},
    )
    update_status(run_ctx, "running", "Running constrained safe command.", {"input": text, "stable_key": stable_key})
    record_event(run_ctx, "command_accepted", {"input": text, "stable_key": stable_key})
    try:
        result = workflow()
        success = bool(result.get("success"))
        record_event(run_ctx, "workflow_result", result)
        finalize_run(
            run_ctx,
            success=success,
            exit_code=0 if success else 1,
            summary={"short_summary": result, "last_error": None if success else "workflow_postcondition_failed"},
        )
        return {"accepted": True, "stable_key": stable_key, "success": success, "result": result, "run_id": run_ctx.run_id}
    except Exception as error:
        error_payload = {"error_type": type(error).__name__, "error": str(error)}
        record_event(run_ctx, "workflow_exception", error_payload)
        finalize_run(run_ctx, success=False, exit_code=1, summary={"short_summary": error_payload, "last_error": error_payload["error"]})
        return {"accepted": True, "stable_key": stable_key, "success": False, "error": error_payload, "run_id": run_ctx.run_id}
