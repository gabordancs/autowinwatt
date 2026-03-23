"""Manual smoke diagnostic for the WinWatt project-open accelerator path.

By default it verifies that the configured accelerator opens the file dialog.
When ``--project-path`` is provided it continues through path entry and dialog
confirmation so the smoke reaches actual project opening as well.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "winwatt_automation" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from winwatt_automation.live_ui.app_connector import (
    FocusGuardError,
    connect_to_winwatt,
    describe_foreground_window,
    ensure_main_window_foreground_before_click,
    get_cached_main_window,
    get_last_focus_guard_diagnostic,
    prepare_main_window_for_menu_interaction,
)
from winwatt_automation.live_ui.project_open_accelerator import (
    PROJECT_OPEN_ACCELERATOR_MODE,
    send_project_open_accelerator,
)
from winwatt_automation.live_ui.file_dialog import interact_with_open_file_dialog
from winwatt_automation.runtime_mapping.program_mapper import capture_state_snapshot, recover_after_project_open

DEFAULT_LOG_PATH = ROOT / "logs" / "winwatt_open_project_accelerator_smoke.json"
POLL_INTERVAL_S = 0.1


def _safe_member(obj: Any, name: str, default: Any = None) -> Any:
    attr = getattr(obj, name, None)
    if attr is None:
        return default
    if callable(attr):
        try:
            return attr()
        except Exception:
            return default
    return attr


def _safe_call(obj: Any, method_name: str, default: Any = None) -> Any:
    value = _safe_member(obj, method_name, default)
    return default if callable(value) else value



def _window_snapshot(window: Any) -> dict[str, Any]:
    rectangle = _safe_call(window, "rectangle", None)
    rect_payload = None
    if rectangle is not None:
        try:
            rect_payload = {
                "left": int(rectangle.left),
                "top": int(rectangle.top),
                "right": int(rectangle.right),
                "bottom": int(rectangle.bottom),
            }
        except Exception:
            rect_payload = None

    handle = _safe_member(window, "handle", None)
    process_id = _safe_member(window, "process_id", None)
    return {
        "title": (_safe_call(window, "window_text", "") or "").strip(),
        "class_name": (_safe_call(window, "class_name", "") or "").strip(),
        "handle": int(handle) if handle is not None else None,
        "process_id": int(process_id) if process_id is not None else None,
        "is_visible": bool(_safe_call(window, "is_visible", False)),
        "is_enabled": bool(_safe_call(window, "is_enabled", False)),
        "rectangle": rect_payload,
    }



def _looks_like_open_dialog(candidate: dict[str, Any]) -> bool:
    title = str(candidate.get("title") or "").lower()
    class_name = str(candidate.get("class_name") or "").lower()
    title_keywords = (
        "open",
        "open file",
        "file name",
        "megnyit",
        "megnyitás",
        "fájlnév",
        "fájl",
    )
    class_keywords = ("#32770", "dialog", "dlg")
    return any(keyword in title for keyword in title_keywords) or any(keyword in class_name for keyword in class_keywords)



def _visible_top_level_windows() -> list[Any]:
    from pywinauto import Desktop

    desktop = Desktop(backend="uia")
    return [window for window in desktop.windows(top_level_only=True) if bool(_safe_call(window, "is_visible", False))]


def _find_visible_window_by_handle(handle: int | None) -> Any | None:
    if handle is None:
        return None
    for window in _visible_top_level_windows():
        if _safe_call(window, "handle", None) == handle:
            return window
    return None



def _detect_dialog(process_id: int | None, baseline_handles: set[int], timeout_s: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    candidates_seen: list[dict[str, Any]] = []

    while time.monotonic() < deadline:
        for window in _visible_top_level_windows():
            snapshot = _window_snapshot(window)
            candidates_seen.append(snapshot)

            handle = snapshot.get("handle")
            pid_match = process_id is not None and snapshot.get("process_id") == process_id
            newly_appeared = handle is not None and handle not in baseline_handles
            if not _looks_like_open_dialog(snapshot):
                continue
            if process_id is not None and not (pid_match or newly_appeared):
                continue

            return {
                "dialog_detected": True,
                "dialog": snapshot,
                "candidate_count": len(candidates_seen),
            }
        time.sleep(POLL_INTERVAL_S)

    return {
        "dialog_detected": False,
        "dialog": None,
        "candidate_count": len(candidates_seen),
    }



def run_smoke(
    *,
    timeout_s: float,
    step_delay_s: float,
    log_path: Path,
    project_path: str | None = None,
    accelerator_mode: str = PROJECT_OPEN_ACCELERATOR_MODE,
    allow_stale_wrapper_refresh: bool = False,
) -> int:
    started_monotonic = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()

    focus_guard_failed = False
    focus_guard_reason = None
    focus_guard_cached_identity = None
    focus_guard_refreshed_identity = None
    focus_guard_relaxed_pass = False
    relaxed_pass_reason = None
    identity_match = None
    refreshed_exists = None
    refreshed_visible = None
    refreshed_enabled = None
    key_send_attempted = False
    accelerator_info = {"project_open_method": accelerator_mode, "sequence": []}
    detection = {"dialog_detected": False, "dialog": None, "candidate_count": 0}
    project_open_result: dict[str, Any] | None = None
    recovery_result: dict[str, Any] | None = None
    foreground_before = {}
    foreground_after = {}

    try:
        connect_to_winwatt()
        prepare_main_window_for_menu_interaction()
        ensure_main_window_foreground_before_click(
            action_label="open_project_accelerator_smoke",
            allow_dialog=True,
            allow_stale_wrapper_refresh=allow_stale_wrapper_refresh,
        )
        focus_guard_diagnostic = get_last_focus_guard_diagnostic()
        focus_guard_cached_identity = focus_guard_diagnostic.get("cached_identity")
        focus_guard_refreshed_identity = focus_guard_diagnostic.get("refreshed_identity")
        focus_guard_relaxed_pass = bool(focus_guard_diagnostic.get("focus_guard_relaxed_pass"))
        relaxed_pass_reason = focus_guard_diagnostic.get("relaxed_pass_reason")
        identity_match = focus_guard_diagnostic.get("identity_match")
        refreshed_exists = focus_guard_diagnostic.get("refreshed_exists")
        refreshed_visible = focus_guard_diagnostic.get("refreshed_visible")
        refreshed_enabled = focus_guard_diagnostic.get("refreshed_enabled")

        main_window = get_cached_main_window()
        process_id = _safe_call(main_window, "process_id", None)
        baseline_handles = {
            snapshot.get("handle")
            for snapshot in (_window_snapshot(window) for window in _visible_top_level_windows())
            if snapshot.get("handle") is not None
        }

        foreground_before = describe_foreground_window()
        accelerator_info = send_project_open_accelerator(mode=accelerator_mode, step_delay_s=step_delay_s)
        key_send_attempted = True
        detection = _detect_dialog(process_id=process_id, baseline_handles=baseline_handles, timeout_s=timeout_s)
        if project_path:
            before_snapshot = asdict(capture_state_snapshot("open_project_accelerator_smoke_before"))
            detected_dialog_snapshot = detection.get("dialog") or None
            helper_dialog_context = {
                "dialog_already_verified": bool(detection.get("dialog_detected")),
                "dialog_handle": (detected_dialog_snapshot or {}).get("handle"),
                "dialog_title": (detected_dialog_snapshot or {}).get("title"),
                "dialog_class": (detected_dialog_snapshot or {}).get("class_name"),
                "dialog_process_id": (detected_dialog_snapshot or {}).get("process_id"),
            }
            dialog_wrapper = None
            if helper_dialog_context.get("dialog_handle") is not None:
                dialog_wrapper = _find_visible_window_by_handle(helper_dialog_context.get("dialog_handle"))
            if bool(detection.get("dialog_detected")):
                project_open_result = asdict(
                    interact_with_open_file_dialog(
                        dialog_wrapper,
                        project_path,
                        before_snapshot=before_snapshot,
                        after_snapshot_provider=lambda: asdict(capture_state_snapshot("open_project_accelerator_smoke_after")),
                        dialog_timeout=timeout_s,
                        project_open_method=accelerator_info.get("project_open_method", accelerator_mode),
                        project_open_sequence=list(accelerator_info.get("sequence") or []),
                        detected_dialog_snapshot=detected_dialog_snapshot,
                        dialog_context=helper_dialog_context,
                    )
                )
            else:
                project_open_result = {
                    "success": False,
                    "path_entry_attempted": False,
                    "path_entered": False,
                    "confirm_attempted": False,
                    "confirm_clicked": False,
                    "dialog_closed": False,
                    "project_state_changed": False,
                    "detected_changes": [],
                    "observed_main_window_title_after_open": "",
                    "observed_project_path": None,
                    "path_match_normalized": False,
                    "detected_dialog_snapshot": detected_dialog_snapshot,
                    "helper_received_dialog_context": helper_dialog_context,
                    "helper_dialog_revalidated": False,
                    "helper_dialog_ready_for_interaction": False,
                    "binding_strategy_used": None,
                    "dialog_handle_available": bool(helper_dialog_context.get("dialog_handle") is not None),
                    "dialog_binding_candidates_count": 0,
                    "binding_failed_reason": "dialog_not_detected" if not bool(detection.get("dialog_detected")) else "helper_not_invoked",
                    "error": "dialog_detected_but_not_bound_for_interaction" if bool(detection.get("dialog_detected")) else "dialog_not_detected",
                }
            recovery_result = recover_after_project_open(timeout_s=timeout_s, poll_interval_s=POLL_INTERVAL_S)
        foreground_after = describe_foreground_window()
    except FocusGuardError as exc:
        elapsed_s = round(time.monotonic() - started_monotonic, 3)
        diagnostic = getattr(exc, "diagnostic", {}) or {}
        refresh_diagnostic = diagnostic.get("refresh_diagnostic") or {}
        focus_guard_failed = True
        focus_guard_reason = str(exc)
        focus_guard_cached_identity = diagnostic.get("cached_identity")
        focus_guard_refreshed_identity = refresh_diagnostic.get("refreshed_identity") or diagnostic.get("refreshed_identity")
        focus_guard_relaxed_pass = bool(refresh_diagnostic.get("focus_guard_relaxed_pass"))
        relaxed_pass_reason = refresh_diagnostic.get("relaxed_pass_reason")
        identity_match = refresh_diagnostic.get("identity_match")
        refreshed_exists = refresh_diagnostic.get("refreshed_exists")
        refreshed_visible = refresh_diagnostic.get("refreshed_visible")
        refreshed_enabled = refresh_diagnostic.get("refreshed_enabled")
        foreground_after = describe_foreground_window()
    else:
        elapsed_s = round(time.monotonic() - started_monotonic, 3)

    dialog = detection.get("dialog") or {}
    path_entry_diagnostics = (project_open_result or {}).get("path_entry_diagnostics") or {}
    payload = {
        "timestamp_utc": started_at,
        "script": str(Path(__file__).relative_to(ROOT)),
        "project_open_method": accelerator_info.get("project_open_method"),
        "sequence": accelerator_info.get("sequence"),
        "allow_stale_wrapper_refresh": allow_stale_wrapper_refresh,
        "focus_guard_failed": focus_guard_failed,
        "focus_guard_reason": focus_guard_reason,
        "cached_identity": focus_guard_cached_identity,
        "refreshed_identity": focus_guard_refreshed_identity,
        "focus_guard_relaxed_pass": focus_guard_relaxed_pass,
        "relaxed_pass_reason": relaxed_pass_reason,
        "identity_match": identity_match,
        "refreshed_exists": refreshed_exists,
        "refreshed_visible": refreshed_visible,
        "refreshed_enabled": refreshed_enabled,
        "key_send_attempted": key_send_attempted,
        "accelerator_sent": key_send_attempted,
        "foreground_before": foreground_before,
        "foreground_after": foreground_after,
        "dialog_detected": bool(detection.get("dialog_detected")),
        "dialog_title": dialog.get("title"),
        "dialog_class": dialog.get("class_name"),
        "dialog_handle": dialog.get("handle"),
        "dialog_process_id": dialog.get("process_id"),
        "detected_dialog_snapshot": (project_open_result or {}).get("detected_dialog_snapshot") or (dialog if dialog else None),
        "helper_received_dialog_context": (project_open_result or {}).get("helper_received_dialog_context"),
        "helper_dialog_revalidated": bool((project_open_result or {}).get("helper_dialog_revalidated")),
        "helper_dialog_ready_for_interaction": bool((project_open_result or {}).get("helper_dialog_ready_for_interaction")),
        "binding_strategy_used": (project_open_result or {}).get("binding_strategy_used"),
        "dialog_handle_available": bool((project_open_result or {}).get("dialog_handle_available")),
        "dialog_binding_candidates_count": int((project_open_result or {}).get("dialog_binding_candidates_count") or 0),
        "binding_failed_reason": (project_open_result or {}).get("binding_failed_reason"),
        "project_path": project_path,
        "project_open_success": bool((project_open_result or {}).get("success")),
        "path_entry_attempted": bool((project_open_result or {}).get("path_entry_attempted")),
        "path_entered": bool((project_open_result or {}).get("path_entered")),
        "confirm_attempted": bool((project_open_result or {}).get("confirm_attempted")),
        "confirm_clicked": bool((project_open_result or {}).get("confirm_clicked")),
        "dialog_closed": bool((project_open_result or {}).get("dialog_closed")),
        "project_state_changed": bool((project_open_result or {}).get("project_state_changed")),
        "project_open_error": (project_open_result or {}).get("error"),
        "project_open_detected_changes": list((project_open_result or {}).get("detected_changes") or []),
        "observed_main_window_title_after_open": (project_open_result or {}).get("observed_main_window_title_after_open"),
        "observed_project_path": (project_open_result or {}).get("observed_project_path"),
        "path_match_normalized": bool((project_open_result or {}).get("path_match_normalized")),
        "path_entry_diagnostics": path_entry_diagnostics,
        "selected_control_control_type": path_entry_diagnostics.get("selected_control_control_type"),
        "selected_control_class_name": path_entry_diagnostics.get("selected_control_class_name"),
        "selected_control_friendly_class_name": path_entry_diagnostics.get("selected_control_friendly_class_name"),
        "selected_control_automation_id": path_entry_diagnostics.get("selected_control_automation_id"),
        "selected_control_name": path_entry_diagnostics.get("selected_control_name"),
        "selected_control_handle": path_entry_diagnostics.get("selected_control_handle"),
        "selected_control_rectangle": path_entry_diagnostics.get("selected_control_rectangle"),
        "selected_control_parent_summary": path_entry_diagnostics.get("selected_control_parent_summary"),
        "selected_control_sibling_summaries": path_entry_diagnostics.get("selected_control_sibling_summaries"),
        "raw_value_before": path_entry_diagnostics.get("raw_value_before"),
        "raw_value_after_immediate": path_entry_diagnostics.get("raw_value_after_immediate"),
        "raw_value_after_300ms": path_entry_diagnostics.get("raw_value_after_300ms"),
        "raw_value_after_1000ms": path_entry_diagnostics.get("raw_value_after_1000ms"),
        "expected_path_raw": path_entry_diagnostics.get("expected_path_raw"),
        "expected_path_normalized": path_entry_diagnostics.get("expected_path_normalized"),
        "actual_path_raw": path_entry_diagnostics.get("actual_path_raw"),
        "actual_path_normalized": path_entry_diagnostics.get("actual_path_normalized"),
        "mismatch_reason": path_entry_diagnostics.get("mismatch_reason"),
        "path_entry_strategy_selected": path_entry_diagnostics.get("path_entry_strategy_selected"),
        "path_entry_strategy_attempted": path_entry_diagnostics.get("path_entry_strategy_attempted"),
        "path_entry_strategy_succeeded": path_entry_diagnostics.get("path_entry_strategy_succeeded"),
        "paste_attempted": bool(path_entry_diagnostics.get("paste_attempted")),
        "paste_sent": bool(path_entry_diagnostics.get("paste_sent")),
        "typed_attempted": bool(path_entry_diagnostics.get("typed_attempted")),
        "typed_sent": bool(path_entry_diagnostics.get("typed_sent")),
        "direct_edit_attempted": bool(path_entry_diagnostics.get("direct_edit_attempted")),
        "direct_edit_sent": bool(path_entry_diagnostics.get("direct_edit_sent")),
        "typed_fallback_skipped_reason": path_entry_diagnostics.get("typed_fallback_skipped_reason"),
        "direct_edit_fallback_skipped_reason": path_entry_diagnostics.get("direct_edit_fallback_skipped_reason"),
        "recovery_success": bool((recovery_result or {}).get("success")),
        "recovery_close_attempts": list((recovery_result or {}).get("close_attempts") or []),
        "recovery_diagnostics": (recovery_result or {}).get("diagnostics"),
        "elapsed_time_s": elapsed_s,
        "timeout_s": timeout_s,
        "step_delay_s": step_delay_s,
        "candidate_count": detection.get("candidate_count"),
    }

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if project_path:
        if payload["project_open_success"] and payload["recovery_success"]:
            return 0
        if payload["focus_guard_failed"]:
            return 2
        return 1
    if payload["dialog_detected"]:
        return 0
    if payload["focus_guard_failed"]:
        return 2
    return 1



def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke diagnostic for the configured WinWatt project-open accelerator path",
        allow_abbrev=False,
    )
    parser.add_argument("--timeout", type=float, default=5.0, help="How long to wait for the dialog after sending the configured accelerator")
    parser.add_argument("--step-delay", type=float, default=0.15, help="Delay between accelerator key steps when the mode uses multiple keypresses")
    parser.add_argument("--accelerator-mode", default=PROJECT_OPEN_ACCELERATOR_MODE, choices=["alt_f_p", "ctrl_o"], help="Project-open accelerator mode to send")
    parser.add_argument("--project-path", default=None, help="Optional project path. When provided the smoke continues through actual project opening.")
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH, help="Path of the JSON result log file")
    parser.add_argument("--allow-stale-wrapper-refresh", action="store_true", help="Allow one diagnostic refresh/retry when the cached UIA wrapper reports exists() == False before the accelerator is sent")
    args = parser.parse_args()

    raise SystemExit(
        run_smoke(
            timeout_s=args.timeout,
            step_delay_s=args.step_delay,
            log_path=args.log_path,
            project_path=args.project_path,
            accelerator_mode=args.accelerator_mode,
            allow_stale_wrapper_refresh=args.allow_stale_wrapper_refresh,
        )
    )


if __name__ == "__main__":
    main()
