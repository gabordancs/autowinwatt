from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
import sys

from loguru import logger

from winwatt_automation.live_ui.app_connector import get_cached_main_window
from winwatt_automation.runtime_logging import append_terminal_line, finalize_run, record_event, start_run, update_status
from winwatt_automation.runtime_logging.progress_display import launch_progress_overlay
from winwatt_automation.runtime_mapping.menu_text import normalize_menu_title
from winwatt_automation.runtime_mapping.program_mapper import DEFAULT_TEST_PROJECT_PATH, build_full_runtime_program_map


def _parse_top_menus(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [normalize_menu_title(item) for item in raw.split(",") if item.strip()]


def _parse_bool(raw: str) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "y"}


def _close_winwatt_after_mapping() -> dict[str, str | bool | None]:
    try:
        main_window = get_cached_main_window()
    except Exception as exc:
        return {"closed": False, "method": None, "error": f"main_window_unavailable:{exc}"}

    close = getattr(main_window, "close", None)
    if callable(close):
        try:
            close()
            return {"closed": True, "method": "window.close", "error": None}
        except Exception as exc:
            logger.warning("WinWatt close() failed: {}", exc)

    try:
        from pywinauto import keyboard

        set_focus = getattr(main_window, "set_focus", None)
        if callable(set_focus):
            set_focus()
        keyboard.send_keys("%{F4}")
        return {"closed": True, "method": "alt+f4", "error": None}
    except Exception as exc:
        return {"closed": False, "method": None, "error": f"keyboard_close_failed:{exc}"}


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
    return parser


def main() -> int:
    args = build_parser().parse_args()
    command = " ".join(["python", *sys.argv])
    run_ctx = start_run(
        command=command,
        context={
            "cwd": str(Path.cwd()),
            "safe_mode": args.safe_mode,
            "project_path": args.project_path or DEFAULT_TEST_PROJECT_PATH,
            "tags": ["map_full_program", "runtime_mapping"],
        },
    )
    sink_id = logger.add(lambda msg: append_terminal_line(run_ctx, str(msg).rstrip("\n")), level="INFO")
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

        no_project = result["state_no_project"]
        project_open = result["state_project_open"]
        diff = asdict(result["diff"])

        print("Runtime mapping completed")
        print(f"- no_project top_menus: {len(no_project.top_menus)}")
        print(f"- project_open top_menus: {len(project_open.top_menus)}")
        print(f"- diff summary: {diff.get('summary', {})}")

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
