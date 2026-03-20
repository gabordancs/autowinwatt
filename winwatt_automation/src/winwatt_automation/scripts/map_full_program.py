from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
import subprocess
import sys
import time

from loguru import logger

from winwatt_automation.live_ui.app_connector import get_cached_main_window, log_cache_usage_summary
from winwatt_automation.live_ui.menu_helpers import log_popup_snapshot_summary
from winwatt_automation.runtime_logging import append_terminal_line, finalize_run, record_event, start_run, update_status
from winwatt_automation.runtime_logging.progress_display import launch_progress_overlay
from winwatt_automation.runtime_mapping.menu_text import normalize_menu_title
from winwatt_automation.runtime_mapping.program_mapper import (
    DEFAULT_TEST_PROJECT_PATH,
    build_full_runtime_program_map,
    log_action_catalog_summary,
)
from winwatt_automation.logging_config import configure_logging
from winwatt_automation.runtime_mapping.config import configure_diagnostics


def _parse_top_menus(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    normalized = [
        normalize_menu_title(item)
        for item in raw.replace(";", ",").split(",")
        if item.strip()
    ]
    return normalized or None


def _parse_bool(raw: str) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "y"}


def _window_is_gone(main_window: object) -> bool:
    exists = getattr(main_window, "exists", None)
    if callable(exists):
        try:
            return not bool(exists(timeout=0.2))
        except Exception:
            pass

    is_visible = getattr(main_window, "is_visible", None)
    if callable(is_visible):
        try:
            return not bool(is_visible())
        except Exception:
            pass

    return False


def _wait_for_window_to_close(main_window: object, *, timeout_s: float = 5.0, poll_interval_s: float = 0.2) -> bool:
    deadline = time.monotonic() + max(timeout_s, poll_interval_s)
    while time.monotonic() < deadline:
        if _window_is_gone(main_window):
            return True
        time.sleep(poll_interval_s)
    return _window_is_gone(main_window)


def _close_winwatt_after_mapping() -> dict[str, str | bool | None]:
    try:
        main_window = get_cached_main_window()
    except Exception as exc:
        return {"closed": False, "method": None, "error": f"main_window_unavailable:{exc}"}

    process_id = None
    process_id_getter = getattr(main_window, "process_id", None)
    if callable(process_id_getter):
        try:
            process_id = int(process_id_getter())
        except Exception:
            process_id = None

    close = getattr(main_window, "close", None)
    if callable(close):
        try:
            close()
            if _wait_for_window_to_close(main_window):
                return {"closed": True, "method": "window.close", "error": None}
            logger.warning("WinWatt close() did not close the window within timeout")
        except Exception as exc:
            logger.warning("WinWatt close() failed: {}", exc)

    try:
        from pywinauto import keyboard

        set_focus = getattr(main_window, "set_focus", None)
        if callable(set_focus):
            set_focus()
        keyboard.send_keys("%{F4}")
        if _wait_for_window_to_close(main_window):
            return {"closed": True, "method": "alt+f4", "error": None}
        logger.warning("WinWatt Alt+F4 did not close the window within timeout")
    except Exception as exc:
        logger.warning("WinWatt Alt+F4 fallback failed: {}", exc)

    if process_id is not None:
        try:
            taskkill = subprocess.run(
                ["taskkill", "/PID", str(process_id), "/T"],
                text=True,
                capture_output=True,
                check=False,
            )
            if taskkill.returncode == 0:
                return {"closed": True, "method": "taskkill_pid", "error": None}
            stderr = taskkill.stderr.strip() or taskkill.stdout.strip() or "taskkill_failed"
            return {"closed": False, "method": "taskkill_pid", "error": stderr}
        except Exception as exc:
            return {"closed": False, "method": "taskkill_pid", "error": f"taskkill_exception:{exc}"}

    return {"closed": False, "method": None, "error": "close_failed"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Map full WinWatt runtime structure")
    parser.add_argument("--project-path", default=DEFAULT_TEST_PROJECT_PATH)
    parser.add_argument("--safe-mode", default="off", choices=["safe", "hybrid", "caution", "blocked", "off", "unsafe"])
    parser.add_argument("--output-dir", default="data/runtime_maps")
    parser.add_argument("--state-id-prefix", default="state")
    parser.add_argument("--top-menus", default=None)
    parser.add_argument("--max-submenu-depth", type=int, default=-1, help="Use -1 for unlimited submenu traversal depth")
    parser.add_argument("--include-disabled", default="true")
    parser.add_argument("--progress-overlay", action="store_true", help="Show a non-activating status HUD while mapping runs")
    parser.add_argument("--diagnostic-fast-mode", action="store_true", help="Diagnostic mode: disable global popup scan, reduce cache validation, and avoid placeholder-triggered relists")
    parser.add_argument("--placeholder-traversal-focus", action="store_true", help="Diagnostic mode: focus logs and traversal behavior around geometry placeholder rows")
    parser.add_argument("--placeholder-modal-policy", default="submenu_only", choices=["submenu_only", "allow_modal_probe"], help="How placeholder traversal handles modal dialogs opened by geometry click points")
    parser.add_argument("--recent-projects-policy", default="skip_recent_projects", choices=["skip_recent_projects", "probe_recent_projects", "open_sample_recent_project"], help="How the File > recent projects area is handled during runtime mapping")
    parser.add_argument("--log-profile", default="concise", choices=["concise", "diagnostic"], help="Concise keeps INFO high-signal, diagnostic exposes low-level DEBUG details.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    command = " ".join(["python", *sys.argv])
    configure_logging(log_profile=args.log_profile)
    configure_diagnostics(
        diagnostic_fast_mode=args.diagnostic_fast_mode,
        placeholder_traversal_focus=args.placeholder_traversal_focus,
        placeholder_modal_policy=args.placeholder_modal_policy,
        recent_projects_policy=args.recent_projects_policy,
        log_profile=args.log_profile,
    )
    run_ctx = start_run(
        command=command,
        context={
            "cwd": str(Path.cwd()),
            "safe_mode": args.safe_mode,
            "project_path": args.project_path or DEFAULT_TEST_PROJECT_PATH,
            "tags": ["map_full_program", "runtime_mapping"],
        },
    )
    sink_level = "DEBUG" if args.log_profile == "diagnostic" else "INFO"
    sink_id = logger.add(lambda msg: append_terminal_line(run_ctx, str(msg).rstrip("\n")), level=sink_level)
    update_status(run_ctx, "starting", "Runtime mapping is starting…")
    if args.progress_overlay:
        launch_progress_overlay(run_ctx.status_path)

    try:
        def _event_recorder(event_type: str, payload: dict[str, object]) -> None:
            record_event(run_ctx, event_type, payload)
            message_map = {
                "state_mapped": f"Állapot feltérképezve: {payload.get('state_id')}",
                "project_open_result": "Projektmegnyitás eredménye rögzítve.",
                "project_open_recovery": "Projektmegnyitás utáni helyreállítás futott.",
                "runtime_diff": "A két runtime állapot diffje elkészült.",
                "knowledge_verification": "A tudásverifikáció elkészült.",
            }
            if event_type in message_map:
                update_status(run_ctx, "running", message_map[event_type], {"event_type": event_type, **payload})

        result = build_full_runtime_program_map(
            project_path=args.project_path,
            safe_mode=args.safe_mode,
            output_dir=args.output_dir,
            state_id_prefix=args.state_id_prefix,
            top_menus=_parse_top_menus(args.top_menus),
            max_submenu_depth=args.max_submenu_depth,
            include_disabled=_parse_bool(args.include_disabled),
            event_recorder=_event_recorder,
        )
        log_cache_usage_summary()
        log_popup_snapshot_summary()
        log_action_catalog_summary()

        no_project = result["state_no_project"]
        project_open = result["state_project_open"]
        diff = asdict(result["diff"])

        print("Runtime mapping completed")
        print(f"- no_project top_menus: {len(no_project.top_menus)}")
        print(f"- project_open top_menus: {len(project_open.top_menus)}")
        print(f"- diff summary: {diff.get('summary', {})}")
        logger.info(
            "Runtime mapping completed summary no_project_top_menus={} project_open_top_menus={} diff_summary={} log_profile={}",
            len(no_project.top_menus),
            len(project_open.top_menus),
            diff.get("summary", {}),
            args.log_profile,
        )

        record_event(
            run_ctx,
            "runtime_mapping_summary",
            {
                "no_project_top_menus": len(no_project.top_menus),
                "project_open_top_menus": len(project_open.top_menus),
                "diff_summary": diff.get("summary", {}),
            },
        )
        update_status(
            run_ctx,
            "running",
            "A runtime mapping összesítése elkészült.",
            {
                "no_project_top_menus": len(no_project.top_menus),
                "project_open_top_menus": len(project_open.top_menus),
                "diff_summary": diff.get("summary", {}),
            },
        )

        skipped = sum(1 for action in no_project.actions + project_open.actions if not action.get("attempted", False))
        recovery = ((result.get("project_open_result") or {}).get("recovery") or {}) if result.get("project_open_result") else {}
        finalize_run(
            run_ctx,
            success=True,
            exit_code=0,
            summary={
                "short_summary": {
                    "no_project top_menus": len(no_project.top_menus),
                    "project_open top_menus": len(project_open.top_menus),
                    "diff summary": diff.get("summary", {}),
                },
                "no_project_top_menus": len(no_project.top_menus),
                "project_open_top_menus": len(project_open.top_menus),
                "diff_summary": diff.get("summary", {}),
                "skipped_by_safety": skipped,
                "modal_detected": len(no_project.dialogs) + len(project_open.dialogs) > 0,
                "recovery_attempted": bool(recovery),
                "recovery_success": bool(recovery.get("success")) if recovery else False,
            },
        )
        return 0
    except Exception as exc:
        record_event(run_ctx, "run_failed", {"error": str(exc)})
        update_status(run_ctx, "failed", f"Hiba történt: {exc}", {"error": str(exc)})
        finalize_run(
            run_ctx,
            success=False,
            exit_code=1,
            summary={
                "short_summary": "runtime_mapping_failed",
                "last_error": str(exc),
            },
        )
        raise
    finally:
        close_result = _close_winwatt_after_mapping()
        record_event(run_ctx, "winwatt_close", close_result)
        logger.remove(sink_id)


if __name__ == "__main__":
    raise SystemExit(main())
