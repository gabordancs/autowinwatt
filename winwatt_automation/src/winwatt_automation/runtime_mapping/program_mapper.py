from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Callable

from loguru import logger

from winwatt_automation.live_ui import menu_helpers
from winwatt_automation.dialog_explorer.dialog_explorer import explore_dialog
from winwatt_automation.live_ui.app_connector import (
    ensure_main_window_foreground_before_click,
    get_cached_main_window,
    is_winwatt_foreground_context,
    reset_winwatt_connection_cache,
)
from winwatt_automation.live_ui.file_dialog import open_project_file_via_dialog_dict
from winwatt_automation.runtime_mapping.models import (
    RuntimeActionResult,
    RuntimeDialogRecord,
    RuntimeMenuNode,
    RuntimeMenuRow,
    RuntimeStateDiff,
    RuntimeStateMap,
    RuntimeStateSnapshot,
    RuntimeWindowRecord,
)
from winwatt_automation.runtime_mapping.menu_text import clean_menu_title, normalize_menu_title
from winwatt_automation.runtime_mapping.safety import classify_safety, is_action_allowed
from winwatt_automation.runtime_mapping.serializers import ensure_output_dirs, write_json
from winwatt_automation.runtime_mapping.timing import BASELINE_DELAY, POPUP_WAIT_TIMEOUT
from winwatt_automation.runtime_mapping.config import (
    diagnostic_options,
    is_diagnostic_fast_mode,
    is_fast_mode,
    is_placeholder_traversal_focus_mode,
    is_diagnostic_log_profile,
    placeholder_modal_policy,
    recent_projects_policy,
)
from winwatt_automation.live_ui.ui_cache import PopupState


DEFAULT_TOP_MENUS = ["Fájl", "Jegyzékek", "Adatbázis...", "Beállítások", "Ablak", "Súgó"]
SYSTEM_TOP_MENUS = ["Rendszer"]
DEFAULT_TEST_PROJECT_PATH = r"C:\Users\dancsg\OneDrive - Futureal\Documents\GitHub\autowinwatt\winwatt_automation\tests\testwwp.wwp"
DEFAULT_WINWATT_EXE_PATH = r"C:\Program Files (x86)\Bausoft\WinWatt gólya\WinWatt32.exe"
DEFAULT_WINWATT_PROCESS_NAME = "WinWatt32.exe"
ENABLE_GEOMETRY_PLACEHOLDERS = True

_TOP_MENU_CACHE: dict[str, Any] | None = None
_TOP_MENU_CACHE_MAIN_WINDOW_HANDLE: int | None = None
ACTION_CATALOG_LOG_STATS: dict[str, Counter[str]] = defaultdict(Counter)
SKIP_REASON_LOG_STATS: dict[str, Counter[str]] = defaultdict(Counter)
ACTION_PROBE_REJECTION_REASONS = {
    "legacy_text_only_without_interaction_evidence",
    "placeholder_without_state_change",
    "text_confidence_none_without_interaction_evidence",
    "text_confidence_low_without_interaction_evidence",
}
ACTION_PROBE_ADMISSION_RESULT_TYPES = {
    "child_popup_opened",
    "dialog_opened",
    "child_window_opened",
    "mdi_child_opened",
    "internal_window_opened",
    "internal_child_window_opened",
    "popup_closed_with_foreground_change",
}
ACTION_PROBE_STRONG_RESULT_TYPES = ACTION_PROBE_ADMISSION_RESULT_TYPES | {
    "popup_closed_without_dialog",
}
TRANSIENT_WINDOW_CLASS_NAMES = {
    "thintwindow",
}
TRANSIENT_WINDOW_CLASS_SUBSTRINGS = (
    "hint",
    "tooltip",
)
INTERNAL_CHILD_CONTEXT_MENU_NAMES = {
    normalize_menu_title(name)
    for name in ("Dokumentumablak", "Szerkesztés", "Csoport", "Elem")
}
INTERNAL_CHILD_CONTROL_TYPES = {"window", "pane", "group"}
INTERNAL_CHILD_DESCENDANT_GROWTH_MIN = 25



def _extract_project_path_from_title(title: str | None) -> str | None:
    value = str(title or "").strip()
    if not value:
        return None
    match = re.search(r'([A-Za-z]:\\[^"\r\n\t]*\.[Ww][Ww][Pp])', value)
    if match:
        return match.group(1)
    return None


def _normalize_project_path(project_path: str | None) -> str | None:
    value = str(project_path or "").strip()
    if not value:
        return None
    return value.replace('/', '\\').lower()


def _build_project_path_verification(*, expected_project_path: str | None, observed_main_window_title: str | None) -> dict[str, Any]:
    observed_project_path = _extract_project_path_from_title(observed_main_window_title)
    normalized_expected = _normalize_project_path(expected_project_path)
    normalized_observed = _normalize_project_path(observed_project_path)
    return {
        "expected_project_path": expected_project_path,
        "observed_main_window_title": str(observed_main_window_title or ""),
        "observed_project_path": observed_project_path,
        "path_match_normalized": bool(normalized_expected and normalized_expected == normalized_observed),
    }


def _project_open_verdict(*, already_open_before_mapping: bool, path_match_normalized: bool, open_attempt_success: bool) -> str:
    if already_open_before_mapping:
        return "already_open_before_mapping"
    if open_attempt_success and path_match_normalized:
        return "opened_by_this_attempt"
    if open_attempt_success and not path_match_normalized:
        return "unproven"
    if not open_attempt_success:
        return "open_attempt_failed"
    return "unproven"


def _record_project_open_step_events(
    event_recorder: Callable[[str, dict[str, Any]], None] | None,
    *,
    project_open_result: dict[str, Any] | None,
    project_path_verification: dict[str, Any],
    verification_snapshot: RuntimeStateSnapshot | None,
) -> None:
    if not event_recorder:
        return

    audit = dict((project_open_result or {}).get("project_open_audit") or {})
    observed_title = verification_snapshot.main_window_title if verification_snapshot else ""
    observed_project_path = project_path_verification.get("observed_project_path")
    path_match_normalized = bool(project_path_verification.get("path_match_normalized"))

    event_recorder(
        "open_file_dialog_detected",
        {
            "value": bool(audit.get("open_file_dialog_detected")),
            "project_open_method": audit.get("project_open_method"),
            "project_open_sequence": list(audit.get("project_open_sequence") or []),
        },
    )
    event_recorder("file_dialog_path_entered", {"value": bool(audit.get("file_dialog_path_entered"))})
    event_recorder("file_dialog_confirm_clicked", {"value": bool(audit.get("file_dialog_confirm_clicked"))})
    event_recorder("dialog_closed", {"value": bool((project_open_result or {}).get("dialog_closed"))})
    event_recorder(
        "observed_main_window_title_after_open",
        {
            "value": observed_title,
            "is_empty": not bool(observed_title),
        },
    )
    event_recorder(
        "observed_project_path",
        {
            "value": observed_project_path,
            "is_null": observed_project_path is None,
        },
    )
    event_recorder(
        "path_match_normalized",
        {
            "value": path_match_normalized,
            "expected_project_path": project_path_verification.get("expected_project_path"),
            "observed_project_path": observed_project_path,
        },
    )


def _safe_capture_snapshot(state_id: str) -> RuntimeStateSnapshot | None:
    try:
        return capture_state_snapshot(state_id)
    except Exception as exc:
        logger.warning("snapshot_capture_failed state_id={} error={}", state_id, exc)
        return None


def _taskkill_process_image(image_name: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["taskkill", "/F", "/IM", image_name, "/T"],
        text=True,
        capture_output=True,
        check=False,
    )
    ok = completed.returncode in {0, 128}
    message = completed.stderr.strip() or completed.stdout.strip() or ""
    return {"ok": ok, "message": message, "returncode": completed.returncode}


def _launch_winwatt_target(*, target_path: str | None, exe_path: str) -> dict[str, Any]:
    launch_target = str(target_path or exe_path)
    try:
        if os.name == "nt" and target_path and target_path.lower().endswith(".wwp"):
            os.startfile(target_path)
            return {"method": "os.startfile", "target": launch_target, "ok": True}
        subprocess.Popen([launch_target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"method": "subprocess.Popen", "target": launch_target, "ok": True}
    except Exception as exc:
        logger.warning("winwatt_launch_failed target={} error={}", launch_target, exc)
        return {"method": "launch_failed", "target": launch_target, "ok": False, "error": str(exc)}


def _wait_for_startup_snapshot(
    state_id: str,
    *,
    expected_project_path: str | None = None,
    timeout_s: float = 20.0,
    poll_interval_s: float = 0.5,
) -> RuntimeStateSnapshot | None:
    deadline = time.monotonic() + max(timeout_s, poll_interval_s)
    normalized_expected = _normalize_project_path(expected_project_path)
    last_snapshot: RuntimeStateSnapshot | None = None
    while time.monotonic() < deadline:
        snapshot = _safe_capture_snapshot(state_id)
        if snapshot is not None:
            last_snapshot = snapshot
            title = str(snapshot.main_window_title or "")
            observed = _normalize_project_path(_extract_project_path_from_title(title))
            if normalized_expected is None:
                if title:
                    return snapshot
            elif observed == normalized_expected:
                return snapshot
        time.sleep(poll_interval_s)
    return last_snapshot


def prepare_fresh_winwatt_session(
    *,
    project_path: str | None = None,
    exe_path: str = DEFAULT_WINWATT_EXE_PATH,
    process_image_name: str = DEFAULT_WINWATT_PROCESS_NAME,
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    reset_winwatt_connection_cache()
    close_result = {"ok": True, "message": "not_attempted", "returncode": None}
    if os.name == "nt":
        close_result = _taskkill_process_image(process_image_name)
        time.sleep(1.0)
        reset_winwatt_connection_cache()

    launch_result = _launch_winwatt_target(target_path=project_path, exe_path=exe_path)
    snapshot = _wait_for_startup_snapshot(
        "startup_after_relaunch",
        expected_project_path=project_path if project_path else None,
        timeout_s=timeout_s,
    )
    return {
        "close_result": close_result,
        "launch_result": launch_result,
        "snapshot_ready": snapshot is not None,
        "snapshot_title": snapshot.main_window_title if snapshot is not None else "",
        "snapshot_project_path": _extract_project_path_from_title(snapshot.main_window_title if snapshot is not None else ""),
    }


def _log_phase_timing(phase: str, started_at: float, **payload: Any) -> None:
    details = " ".join(f"{key}={value}" for key, value in payload.items())
    suffix = f" {details}" if details else ""
    elapsed_ms = (time.monotonic() - started_at) * 1000.0
    if phase == "subtree_traversal":
        logger.info("DBG_PHASE_TIMING phase={} elapsed_ms={:.3f}{}", phase, elapsed_ms, suffix)
        return
    logger.debug("DBG_PHASE_TIMING phase={} elapsed_ms={:.3f}{}", phase, elapsed_ms, suffix)


def _placeholder_meta(row: RuntimeMenuRow | dict[str, Any]) -> dict[str, Any]:
    if isinstance(row, RuntimeMenuRow):
        return dict(row.meta)
    return dict(row.get("meta") or {})


def _is_placeholder_row(row: RuntimeMenuRow | dict[str, Any]) -> bool:
    meta = _placeholder_meta(row)
    return meta.get("source") == "geometry_placeholder"


def _row_has_legacy_text_only(row: RuntimeMenuRow | dict[str, Any]) -> bool:
    if isinstance(row, RuntimeMenuRow):
        raw_sources = list(row.raw_text_sources)
    else:
        raw_sources = list(row.get("raw_text_sources") or [])
    normalized = [str(source) for source in raw_sources if str(source)]
    return bool(normalized) and set(normalized) == {"legacy_text"}


def _row_text_confidence(row: RuntimeMenuRow | dict[str, Any]) -> str:
    if isinstance(row, RuntimeMenuRow):
        return str(row.text_confidence or "none")
    return str(row.get("text_confidence") or "none")


def _row_has_strong_interaction_evidence(row: RuntimeMenuRow | dict[str, Any], probe_evidence: dict[str, Any] | None = None) -> bool:
    probe_evidence = dict(probe_evidence or {})
    source = asdict(row) if isinstance(row, RuntimeMenuRow) else dict(row)
    meta = dict(source.get("meta") or {})
    evidence = dict(meta.get("interaction_evidence_probe") or {})
    if probe_evidence:
        evidence.update(probe_evidence)
    result_type = str(evidence.get("result_type") or "")
    return bool(
        result_type in ACTION_PROBE_ADMISSION_RESULT_TYPES
        or evidence.get("evidence_strength") == "strong"
        or evidence.get("dialog_opened")
        or evidence.get("child_popup_opened")
        or evidence.get("mdi_child_opened")
    )


def _placeholder_geometry_signature(row: RuntimeMenuRow | dict[str, Any]) -> tuple[int, int, int, int] | None:
    source = asdict(row) if isinstance(row, RuntimeMenuRow) else dict(row)
    rect = dict(source.get("rectangle") or {})
    if not rect:
        meta = dict(source.get("meta") or {})
        rect = dict(meta.get("rectangle") or {})
    keys = ("left", "top", "right", "bottom")
    try:
        values = tuple(int(rect.get(key)) for key in keys)
    except Exception:
        return None
    return values if all(value >= 0 for value in values) else None


def _placeholder_textual_child_rows(child_rows: list[dict[str, Any]] | None) -> bool:
    for child_row in child_rows or []:
        if normalize_menu_title(str(child_row.get("text") or "")):
            return True
    return False


def _placeholder_has_finalizable_probe_evidence(row: RuntimeMenuRow, probe_evidence: dict[str, Any] | None = None) -> bool:
    if not _is_placeholder_row(row):
        return True
    probe_evidence = dict(probe_evidence or {})
    if str(probe_evidence.get("result_type") or "") != "child_popup_opened":
        return False
    return bool(probe_evidence.get("placeholder_geometry_stable") or probe_evidence.get("textual_child_rows_detected"))


def _should_include_placeholder_in_final_outputs(row: RuntimeMenuRow | dict[str, Any]) -> bool:
    if not _is_placeholder_row(row):
        return True
    source = row if isinstance(row, RuntimeMenuRow) else None
    meta = _placeholder_meta(row)
    if bool(meta.get("placeholder_finalized")):
        return True
    if source is not None:
        return bool(source.admitted_to_action_catalog and _placeholder_has_finalizable_probe_evidence(source, meta.get("interaction_evidence_probe")))
    return False


def _update_row_admission_flags(
    row: RuntimeMenuRow,
    *,
    admitted: bool,
    admission_reason: str | None,
    rejection_reason: str | None,
) -> RuntimeMenuRow:
    row.admitted_to_action_catalog = admitted
    row.retained_as_structure_only = not admitted
    row.admission_reason = admission_reason
    row.rejection_reason = rejection_reason
    meta = dict(row.meta)
    meta["placeholder_finalized"] = bool(admitted and _placeholder_has_finalizable_probe_evidence(row, meta.get("interaction_evidence_probe")))
    row.meta = meta
    return row


def _window_title(snapshot: RuntimeStateSnapshot) -> str:
    return str((snapshot.foreground_window or {}).get("title") or "")


def _window_class(snapshot: RuntimeStateSnapshot) -> str:
    return str((snapshot.foreground_window or {}).get("class_name") or "")


class UnrecoverableMainWindowError(RuntimeError):
    """Raised when the mapper loses WinWatt main window context and cannot recover."""


def _safe_call(obj: Any, method: str, default: Any = None) -> Any:
    attr = getattr(obj, method, None)
    if not callable(attr):
        return default
    try:
        return attr()
    except Exception:
        return default


def _list_visible_top_windows() -> list[dict[str, Any]]:
    try:
        from pywinauto import Desktop
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for window in Desktop(backend="uia").windows(top_level_only=True):
        if not bool(_safe_call(window, "is_visible", False)):
            continue
        rows.append({
            "title": _safe_call(window, "window_text", "") or "",
            "class_name": _safe_call(window, "class_name", "") or "",
            "process_id": _safe_call(window, "process_id", None),
            "handle": _safe_call(window, "handle", None),
        })
    return rows


def _close_secondary_windows(main_title: str) -> None:
    try:
        from pywinauto import Desktop, keyboard
    except Exception:
        return
    for window in Desktop(backend="uia").windows(top_level_only=True):
        if not bool(_safe_call(window, "is_visible", False)):
            continue
        title = _safe_call(window, "window_text", "") or ""
        if title == main_title:
            continue
        try:
            window.set_focus()
            keyboard.send_keys("{ESC}")
        except Exception:
            continue


def _extract_shortcut(text: str) -> tuple[str, str | None]:
    parts = [part.strip() for part in text.split("\t")]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return text, None


def _guess_enabled(row: dict[str, Any]) -> bool | None:
    if row.get("is_separator"):
        return None
    if "enabled_guess" in row:
        value = row.get("enabled_guess")
        return bool(value) if value is not None else None
    if "enabled" in row:
        value = row.get("enabled")
        return bool(value) if value is not None else None
    return True


def _rect_dimensions(rect: dict[str, Any]) -> tuple[int, int]:
    left = int(rect.get("left") or 0)
    right = int(rect.get("right") or 0)
    top = int(rect.get("top") or 0)
    bottom = int(rect.get("bottom") or 0)
    return max(0, right - left), max(0, bottom - top)


def _has_valid_rectangle(rect: dict[str, Any]) -> bool:
    width, height = _rect_dimensions(rect)
    return width > 0 and height > 0


def _rect_center(rect: dict[str, Any]) -> dict[str, int]:
    left = int(rect.get("left") or 0)
    right = int(rect.get("right") or 0)
    top = int(rect.get("top") or 0)
    bottom = int(rect.get("bottom") or 0)
    return {"x": left + ((right - left) // 2), "y": top + ((bottom - top) // 2)}


def _rect_signature(rect: dict[str, Any] | None) -> tuple[int, int, int, int] | None:
    rect = dict(rect or {})
    try:
        return (
            int(rect.get("left") or 0),
            int(rect.get("top") or 0),
            int(rect.get("right") or 0),
            int(rect.get("bottom") or 0),
        )
    except Exception:
        return None


def _rectangles_overlap(rect_a: dict[str, Any] | None, rect_b: dict[str, Any] | None, *, padding: int = 0) -> bool:
    sig_a = _rect_signature(rect_a)
    sig_b = _rect_signature(rect_b)
    if sig_a is None or sig_b is None:
        return False
    left_a, top_a, right_a, bottom_a = sig_a
    left_b, top_b, right_b, bottom_b = sig_b
    return not (
        right_a + padding <= left_b
        or right_b + padding <= left_a
        or bottom_a + padding <= top_b
        or bottom_b + padding <= top_a
    )


def _rectangles_nearly_equal(rect_a: dict[str, Any] | None, rect_b: dict[str, Any] | None, *, tolerance: int = 3) -> bool:
    sig_a = _rect_signature(rect_a)
    sig_b = _rect_signature(rect_b)
    if sig_a is None or sig_b is None:
        return False
    return all(abs(a - b) <= tolerance for a, b in zip(sig_a, sig_b, strict=False))


def _popup_row_geometry_band(rows: list[dict[str, Any]] | None) -> tuple[int, int, int, int] | None:
    popup_rects = [
        _rect_signature(row.get("rectangle"))
        for row in list(rows or [])
        if _row_popup_like(row) or ("topbar_candidate" not in row and not _row_topbar_like(row))
    ]
    popup_rects = [rect for rect in popup_rects if rect is not None]
    if not popup_rects:
        return None
    return (
        min(rect[0] for rect in popup_rects),
        min(rect[1] for rect in popup_rects),
        max(rect[2] for rect in popup_rects),
        max(rect[3] for rect in popup_rects),
    )


def _popup_state_path_is_compatible(
    *,
    current_menu_path: tuple[str, ...] | None,
    normalized_parent: tuple[str, ...],
) -> bool:
    if current_menu_path is None:
        return False
    return tuple(current_menu_path) == tuple(normalized_parent)


def _infer_foreground_top_menu_from_snapshot_rows(
    rows: list[dict[str, Any]],
    *,
    canonical_top_menu_names: set[str] | None,
) -> str | None:
    if not canonical_top_menu_names:
        return None
    popup_band = _popup_row_geometry_band(rows)
    if popup_band is None:
        return None
    popup_left, _popup_top, popup_right, _popup_bottom = popup_band
    for row in rows:
        if not _row_topbar_like(row):
            continue
        normalized = normalize_menu_title(str(row.get("text") or ""))
        if not normalized or normalized not in canonical_top_menu_names:
            continue
        rect = dict(row.get("rectangle") or {})
        if _rectangles_overlap(
            rect,
            {"left": popup_left, "top": -1, "right": popup_right, "bottom": 10_000},
            padding=12,
        ):
            return normalized
    return None


def _popup_snapshot_belongs_to_current_parent(
    *,
    top_menu: str,
    parent_path: list[str],
    normalized_parent: tuple[str, ...],
    snapshot_rows: list[dict[str, Any]] | None,
    popup_state: PopupState | None,
    canonical_top_menu_names: set[str] | None,
) -> tuple[bool, str | None]:
    if not snapshot_rows:
        return False, "empty_snapshot"
    current_menu_path = getattr(popup_state, "current_menu_path", None) if popup_state is not None else None
    if tuple(normalized_parent) != tuple(normalize_menu_title(part) for part in parent_path):
        return False, "parent_mismatch"
    if not _popup_state_path_is_compatible(current_menu_path=current_menu_path, normalized_parent=normalized_parent):
        return False, "state_path_mismatch"
    foreground_top_menu = _infer_foreground_top_menu_from_snapshot_rows(
        snapshot_rows,
        canonical_top_menu_names=canonical_top_menu_names,
    )
    normalized_top_menu = normalize_menu_title(top_menu)
    if foreground_top_menu and foreground_top_menu != normalized_top_menu:
        return False, "foreground_context_mismatch"
    popup_band = _popup_row_geometry_band(snapshot_rows)
    if popup_band is None:
        return False, "geometry_mismatch"
    if canonical_top_menu_names:
        foreign_topbar_overlap = False
        for row in snapshot_rows:
            if not _row_topbar_like(row):
                continue
            normalized = normalize_menu_title(str(row.get("text") or ""))
            if not normalized or normalized == normalized_top_menu or normalized not in canonical_top_menu_names:
                continue
            if _rectangles_overlap(
                row.get("rectangle"),
                {"left": popup_band[0], "top": -1, "right": popup_band[2], "bottom": 10_000},
                padding=12,
            ):
                foreign_topbar_overlap = True
                break
        if foreign_topbar_overlap:
            return False, "geometry_mismatch"
    return True, None


def _is_foreign_popup_row(
    row: dict[str, Any],
    *,
    source_top_menu: str,
) -> tuple[bool, str | None]:
    normalized_text = normalize_menu_title(str(row.get("text") or ""))
    rect = dict(row.get("rectangle") or {})
    width, height = _rect_dimensions(rect)
    if normalized_text == normalize_menu_title("Dokumentumablak") and width <= 40 and height <= 40:
        normalized_top_menu = normalize_menu_title(source_top_menu)
        if normalized_top_menu != normalize_menu_title("Dokumentumablak"):
            return True, "mdi_window_bleedthrough"
    return False, None


def _row_popup_like(row: dict[str, Any]) -> bool:
    return bool(row.get("popup_like", row.get("popup_candidate")))


def _row_topbar_like(row: dict[str, Any]) -> bool:
    return bool(row.get("topbar_like", row.get("topbar_candidate")))


def _row_local_fragments_for_text_recovery(row: dict[str, Any]) -> list[dict[str, Any]]:
    safe_fragments: list[dict[str, Any]] = []
    for fragment in list(row.get("fragments") or []):
        raw_sources = [str(source) for source in list(fragment.get("raw_text_sources") or []) if str(source)]
        source_scope = str(fragment.get("source_scope") or "")
        if raw_sources and raw_sources[0] == "legacy_text":
            continue
        if source_scope == "child_text" or not raw_sources:
            safe_fragments.append(fragment)
            continue
        if any(source in {"child_text", "uia_name", "window_text"} for source in raw_sources):
            safe_fragments.append(fragment)
    return safe_fragments


def _resolve_row_text_with_fallback(row: dict[str, Any], *, row_index: int) -> tuple[str, list[str], str]:
    direct_text = str(row.get("text") or "").strip()
    raw_sources = [str(source) for source in list(row.get("raw_text_sources") or []) if str(source)]
    confidence = str(row.get("text_confidence") or ("high" if direct_text else "none"))
    if direct_text:
        return direct_text, raw_sources or ["existing_text"], confidence

    if str(row.get("rejected_text_recovery_reason") or "") == "repeated_legacy_text":
        logger.info(
            "POPUP_TEXT_RECOVERY_SOURCE_REJECTED row_index={} source=legacy_text reason=repeated_fallback_text_mapper_guard",
            row_index,
        )

    fragments = _row_local_fragments_for_text_recovery(row)
    merged = menu_helpers._merge_text_fragments(fragments, rect=dict(row.get("rectangle") or {}))
    if merged:
        merged_sources = list(dict.fromkeys([*raw_sources, "fragment_merge"]))
        logger.info(
            "TEXT_FRAGMENT_MERGE_APPLIED row_index={} fragment_count={} merged_text={!r}",
            row_index,
            len(fragments),
            merged,
        )
        logger.info(
            "TEXT_EXTRACTION_FALLBACK_USED row_index={} source=fragment_merge confidence=medium",
            row_index,
        )
        return merged, merged_sources, "medium"

    logger.warning(
        "TEXT_EXTRACTION_FAILED row_index={} source_scope={} fragment_count={} rectangle={}",
        row_index,
        row.get("source_scope"),
        len(fragments),
        row.get("rectangle"),
    )
    return "", raw_sources, "none"


def _foreground_matches_main_window(snapshot: RuntimeStateSnapshot | None) -> bool:
    if snapshot is None:
        return False
    foreground = dict(snapshot.foreground_window or {})
    return bool(foreground) and str(foreground.get("title") or "") == snapshot.main_window_title and str(foreground.get("class_name") or "") == snapshot.main_window_class


def _is_stable_vertical_popup_list(rows: list[dict[str, Any]]) -> bool:
    popup_rows = [row for row in rows if _row_popup_like(row)]
    if not popup_rows:
        return False
    base_rect = dict((popup_rows[0].get("rectangle") or {}))
    base_left = int(base_rect.get("left") or 0)
    base_right = int(base_rect.get("right") or 0)
    last_top = int(base_rect.get("top") or 0)
    base_height = max(1, int(base_rect.get("bottom") or 0) - last_top)
    for row in popup_rows[1:]:
        rect = dict(row.get("rectangle") or {})
        left = int(rect.get("left") or 0)
        right = int(rect.get("right") or 0)
        top = int(rect.get("top") or 0)
        height = max(1, int(rect.get("bottom") or 0) - top)
        if abs(left - base_left) > 6 or abs(right - base_right) > 6:
            return False
        if abs(height - base_height) > 8:
            return False
        if top <= last_top or top - last_top > max(40, base_height * 2):
            return False
        last_top = top
    return True


def _classify_popup_block(
    *,
    top_menu: str,
    rows: list[dict[str, Any]],
    snapshot: RuntimeStateSnapshot | None,
    canonical_top_menu_names: set[str] | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    popup_like_count, topbar_like_count, filtered_rows = _summarize_normal_popup_rows(
        rows,
        canonical_top_menu_names=canonical_top_menu_names,
    )
    popup_rows = [row for row in filtered_rows if _row_popup_like(row)]
    empty_popup_rows = [row for row in popup_rows if not str(row.get("text") or "").strip()]
    empty_ratio = (len(empty_popup_rows) / len(popup_rows)) if popup_rows else 0.0
    explicit_recent_entries = [
        row for row in popup_rows if menu_helpers._is_recent_project_entry_text(str(row.get("text") or ""))
    ]
    recent_candidate = (
        normalize_menu_title(top_menu) == normalize_menu_title("Fájl")
        and (
            (
                popup_like_count > 0
                and bool(popup_rows)
                and empty_ratio >= 0.8
                and all(str(row.get("popup_reason") or "") == "empty_text_vertical_cluster_below_topbar" for row in empty_popup_rows)
                and snapshot is not None
                and snapshot.main_window_enabled is not False
                and _foreground_matches_main_window(snapshot)
                and _is_stable_vertical_popup_list(popup_rows)
            )
            or bool(explicit_recent_entries)
        )
    )
    classification = "recent_projects_block" if recent_candidate else "normal_popup"
    accepted_rows = filtered_rows
    if popup_like_count > 0 and empty_ratio >= 0.8 and not recent_candidate and not filtered_rows:
        classification = "ambiguous_empty_block"
        accepted_rows = []
    stateful = classification == "recent_projects_block"
    for row in rows:
        row["popup_block_classification"] = classification
        row["recent_projects_block"] = stateful
        row["stateful_menu_block"] = stateful
        row["recent_project_entry"] = False
    if stateful:
        for row in accepted_rows:
            row["popup_block_classification"] = classification
            row["recent_projects_block"] = True
            row["stateful_menu_block"] = True
            row["recent_project_entry"] = (
                menu_helpers._is_recent_project_entry_text(str(row.get("text") or ""))
                or (_row_popup_like(row) and not str(row.get("text") or "").strip())
            )
    return classification, accepted_rows, {
        "popup_like_count": popup_like_count,
        "topbar_like_count": topbar_like_count,
        "filtered_row_count": len(filtered_rows),
        "accepted_row_count": len(accepted_rows),
        "empty_popup_row_count": len(empty_popup_rows),
        "empty_popup_ratio": empty_ratio,
    }


def _row_to_node(
    state_id: str,
    top_menu: str,
    row: dict[str, Any],
    *,
    level: int,
    index: int,
    path: list[str],
    children: list[dict[str, Any]],
    opens_submenu: bool,
    opens_dialog: bool = False,
    opens_modal: bool = False,
    skipped_by_safety: bool = False,
    reused_from_previous_state: bool = False,
) -> RuntimeMenuNode:
    started_at = time.monotonic()
    title_raw = str(row.get("text") or "")
    title, shortcut = _extract_shortcut(title_raw)
    title_clean = clean_menu_title(title)
    normalized = normalize_menu_title(title)
    logger.debug('RAW_MENU_TITLE="{}" NORMALIZED_MENU_TITLE="{}"', title, normalized)
    normalized_path = [clean_menu_title(part) for part in path]
    safety = classify_safety(normalized_path)
    likely_destructive = safety == "blocked"
    likely_state_changing = safety in {"caution", "blocked"}
    enabled = _guess_enabled(row)
    action_state_classification = "unknown"
    if row.get("is_separator"):
        action_classification = "separator"
        action_state_classification = "separator"
    elif reused_from_previous_state:
        action_classification = "reused_from_previous_state"
    elif skipped_by_safety:
        action_classification = "skipped_by_safety"
    elif bool(row.get("recent_project_entry")):
        action_classification = "recent_project_entry"
        action_state_classification = "recent_project_entry"
    elif opens_submenu:
        action_classification = "opens_submenu"
        action_state_classification = "opens_submenu"
    elif opens_modal:
        action_classification = "opens_modal"
        action_state_classification = "opens_modal"
    elif opens_dialog:
        action_classification = "dialog_window_action"
        action_state_classification = "changes_menu_state"
    elif enabled is False:
        action_classification = "disabled"
        action_state_classification = "disabled"
    elif enabled is True:
        action_classification = "leaf_action"
        action_state_classification = "executes_command"
    else:
        action_classification = "unknown"

    node = RuntimeMenuNode(
        state_id=state_id,
        title_raw=title,
        title=title_clean,
        normalized_title=normalized,
        path=normalized_path,
        level=level,
        index=index,
        enabled=enabled,
        separator=bool(row.get("is_separator")),
        shortcut=shortcut,
        opens_submenu=opens_submenu,
        opens_dialog=opens_dialog,
        opens_modal=opens_modal,
        likely_destructive=likely_destructive,
        likely_state_changing=likely_state_changing,
        action_classification=action_classification,
        action_state_classification=action_state_classification,
        skipped_by_safety=skipped_by_safety,
        children=children,
        debug={
            "geometry": dict(row.get("rectangle") or {}),
            "source_scope": str(row.get("source_scope") or ""),
            "fragments": list(row.get("fragments") or []),
            "top_menu": top_menu,
            "reused_from_previous_state": reused_from_previous_state,
        },
    )
    logger.debug("_row_to_node state={} top_menu={} level={} index={} title={} placeholder={} classification={}", state_id, top_menu, level, index, title_clean, _is_placeholder_row(row), action_classification)
    _log_phase_timing("_row_to_node", started_at, top_menu=top_menu, level=level, index=index, title=title_clean, placeholder=_is_placeholder_row(row))
    return node


def reset_top_menu_cache() -> None:
    global _TOP_MENU_CACHE, _TOP_MENU_CACHE_DISCOVERED_SIGNATURE, _TOP_MENU_CACHE_MAIN_WINDOW_HANDLE
    _TOP_MENU_CACHE = None
    _TOP_MENU_CACHE_DISCOVERED_SIGNATURE = None
    _TOP_MENU_CACHE_MAIN_WINDOW_HANDLE = None


def get_canonical_top_menu_names(discovered_top_menus: list[str]) -> dict[str, Any]:
    global _TOP_MENU_CACHE, _TOP_MENU_CACHE_DISCOVERED_SIGNATURE, _TOP_MENU_CACHE_MAIN_WINDOW_HANDLE

    try:
        main_window = get_cached_main_window()
    except Exception:
        main_window = None
    current_handle = _safe_call(main_window, "handle", None)
    discovered_signature = tuple(normalize_menu_title(item) for item in discovered_top_menus if normalize_menu_title(item))
    if (
        current_handle is not None
        and _TOP_MENU_CACHE is not None
        and _TOP_MENU_CACHE_MAIN_WINDOW_HANDLE == current_handle
        and _TOP_MENU_CACHE_DISCOVERED_SIGNATURE == discovered_signature
    ):
        return _TOP_MENU_CACHE

    items: list[dict[str, str]] = []
    normalized_to_raw: dict[str, str] = {}

    for raw_name in discovered_top_menus:
        normalized = normalize_menu_title(raw_name)
        if not normalized or normalized in normalized_to_raw:
            continue
        clean_name = clean_menu_title(raw_name)
        normalized_to_raw[normalized] = raw_name
        items.append({"raw": raw_name, "clean": clean_name, "normalized": normalized})

    canonical = {
        "items": items,
        "normalized_to_raw": normalized_to_raw,
        "normalized_names": set(normalized_to_raw),
    }
    if current_handle is not None:
        _TOP_MENU_CACHE = canonical
        _TOP_MENU_CACHE_DISCOVERED_SIGNATURE = discovered_signature
        _TOP_MENU_CACHE_MAIN_WINDOW_HANDLE = current_handle
    logger.info("Canonical top-level menus [{}]: {}", len(items), [item["raw"] for item in items])
    return canonical


def is_top_menu_like_popup_row(row: dict[str, Any], canonical_top_menu_names: set[str]) -> bool:
    text = str(row.get("text") or "")
    normalized = normalize_menu_title(text)
    return bool(normalized and normalized in canonical_top_menu_names)


def should_restore_clean_menu_baseline(*, state_id: str, stage: str, popup_rows: list[dict[str, Any]] | None = None) -> bool:
    try:
        main_window = get_cached_main_window()
    except Exception:
        return False
    if not bool(_safe_call(main_window, "is_visible", False)):
        logger.warning("baseline_restore_needed state={} stage={} reason=main_window_hidden", state_id, stage)
        return True
    if not bool(_safe_call(main_window, "is_enabled", True)):
        logger.warning("baseline_restore_needed state={} stage={} reason=main_window_disabled", state_id, stage)
        return True
    if not is_winwatt_foreground_context(main_window, allow_dialog=True):
        logger.warning("baseline_restore_needed state={} stage={} reason=focus_lost", state_id, stage)
        return True
    if popup_rows is not None:
        try:
            current_rows = menu_helpers.capture_menu_popup_snapshot()
        except Exception:
            current_rows = []
        if bool(current_rows) != bool(popup_rows):
            logger.warning("baseline_restore_needed state={} stage={} reason=popup_snapshot_mismatch", state_id, stage)
            return True
    return False


def restore_clean_menu_baseline(*, state_id: str, stage: str) -> bool:
    logger.debug("baseline_restore start state={} stage={}", state_id, stage)
    try:
        ensure_main_window_foreground_before_click(action_label=f"baseline_restore:{state_id}:{stage}")
    except Exception as exc:
        main_window = get_cached_main_window()
        if bool(_safe_call(main_window, "is_visible", False)) and not bool(_safe_call(main_window, "is_enabled", True)):
            logger.warning("baseline_restore modal_pending state={} stage={} error={}", state_id, stage, exc)
            recovery = recover_after_project_open()
            if recovery.get("success"):
                logger.info("baseline_restore modal_pending_recovered state={} stage={}", state_id, stage)
            else:
                logger.error("baseline_restore failed state={} stage={} error={}", state_id, stage, exc)
                return False
        else:
            logger.error("baseline_restore failed state={} stage={} error={}", state_id, stage, exc)
            return False

    for _ in range(2):
        try:
            from pywinauto import keyboard

            keyboard.send_keys("{ESC}")
            if menu_helpers.wait_for_popup_to_close(timeout=BASELINE_DELAY):
                break
        except Exception:
            pass

    try:
        menu_helpers.capture_menu_popup_snapshot()
    except Exception:
        pass

    logger.debug("baseline_restore success state={} stage={}", state_id, stage)
    return True


def capture_state_snapshot(state_id: str) -> RuntimeStateSnapshot:
    main_window = get_cached_main_window()
    return RuntimeStateSnapshot(
        state_id=state_id,
        process_id=_safe_call(main_window, "process_id", None),
        main_window_title=_safe_call(main_window, "window_text", "") or "",
        main_window_class=_safe_call(main_window, "class_name", "") or "",
        visible_top_windows=_list_visible_top_windows(),
        discovered_top_menus=menu_helpers.list_top_menu_items(),
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
        main_window_enabled=bool(_safe_call(main_window, "is_enabled", False)),
        main_window_visible=bool(_safe_call(main_window, "is_visible", False)),
        foreground_window=_foreground_window_info(),
    )


def _build_menu_rows_from_popup_rows(
    state_id: str,
    top_menu: str,
    rows: list[dict[str, Any]],
    *,
    canonical_top_menu_names: set[str] | None = None,
) -> list[RuntimeMenuRow]:
    started_at = time.monotonic()
    mapped: list[RuntimeMenuRow] = []
    filtered_counts = {"top_level_overlap": 0, "empty_popup_text_non_actionable": 0}
    placeholder_count = 0
    rejected_foreign_rows = 0
    for index, row in enumerate(rows):
        if bool(row.get("popup_noise_suppressed")):
            logger.info(
                "DBG_MENU_BUILD_FILTER_REASON state={} top_menu={} row_index={} reason=popup_noise_suppressed row_text={!r} rectangle={} suppression_reason={} duplicate_of={}",
                state_id,
                top_menu,
                index,
                row.get("text"),
                row.get("rectangle"),
                row.get("rejected_text_recovery_reason"),
                row.get("suppressed_as_duplicate_of"),
            )
            continue
        popup_like = _row_popup_like(row)
        topbar_like = _row_topbar_like(row)
        rect = dict(row.get("rectangle") or {})
        logger.info(
            "DBG_MENU_BUILD_INPUT_ROW state={} top_menu={} row_index={} text={!r} rectangle={} topbar_like={} popup_like={} source_scope={} fragments={} ",
            state_id,
            top_menu,
            index,
            row.get("text"),
            rect,
            topbar_like,
            popup_like,
            row.get("source_scope"),
            len(list(row.get("fragments") or [])),
        )
        reject_foreign, foreign_reason = _is_foreign_popup_row(row, source_top_menu=top_menu)
        if reject_foreign:
            log_name = "MDI_BLEEDTHROUGH_REJECTED" if foreign_reason == "mdi_window_bleedthrough" else "FOREIGN_POPUP_ROW_REJECTED"
            logger.info(
                "{} state={} top_menu={} row_index={} reason={} row_text={!r} rectangle={} source_scope={}",
                log_name,
                state_id,
                top_menu,
                index,
                foreign_reason or "foreign_popup_row",
                row.get("text"),
                rect,
                row.get("source_scope"),
            )
            rejected_foreign_rows += 1
            continue
        if canonical_top_menu_names and is_top_menu_like_popup_row(row, canonical_top_menu_names):
            logger.info(
                "DBG_MENU_BUILD_FILTER_REASON state={} top_menu={} row_index={} reason=top-level overlap row_text={!r} rectangle={} topbar_like={} popup_like={} normalized_text={} canonical_match=True",
                state_id,
                top_menu,
                index,
                row.get("text"),
                row.get("rectangle"),
                bool(row.get("topbar_candidate")),
                bool(row.get("popup_candidate")),
                normalize_menu_title(str(row.get("text") or "")),
            )
            logger.debug("popup row filtered as top-level overlap top_menu={} row_text={}", top_menu, row.get("text"))
            filtered_counts["top_level_overlap"] += 1
            continue
        text, raw_text_sources, text_confidence = _resolve_row_text_with_fallback(row, row_index=index)
        title, _ = _extract_shortcut(text)
        title_clean = clean_menu_title(title)
        normalized_title = normalize_menu_title(title)
        logger.debug('RAW_MENU_TITLE="{}" NORMALIZED_MENU_TITLE="{}"', title, normalized_title)
        meta: dict[str, Any] = {}
        actionable = not bool(row.get("is_separator"))
        dispatch_type = "click"
        recent_project_entry = bool(row.get("recent_project_entry"))
        stateful_menu_block = bool(row.get("stateful_menu_block"))
        enabled_guess = _guess_enabled(row)
        if menu_helpers._is_recent_project_entry_text(text):
            recent_project_entry = True
            stateful_menu_block = True
        if bool(row.get("is_separator")):
            actionable = False
        if not normalized_title:
            logger.info(
                "DBG_WINWATT_EMPTY_NORMALIZED_MENU_TITLE row_index={} raw_text={} normalized_text={} is_separator={} source_scope={} control_type={} class_name={} rectangle={} fragment_count={} fragment_texts={} ",
                index,
                text,
                normalized_title,
                bool(row.get("is_separator")),
                row.get("source_scope"),
                row.get("control_type"),
                row.get("class_name"),
                rect,
                len(list(row.get("fragments") or [])),
                [fragment.get("text") for fragment in list(row.get("fragments") or [])],
            )
            placeholder_eligible = (
                ENABLE_GEOMETRY_PLACEHOLDERS
                and not bool(row.get("is_separator"))
                and not (recent_project_entry and text.strip())
                and popup_like
                and not topbar_like
                and not text.strip()
                and _has_valid_rectangle(rect)
            )
            if placeholder_eligible:
                title_clean = f"[unlabeled row {index}]"
                normalized_title = normalize_menu_title(title_clean)
                click_point = _rect_center(rect)
                meta = {
                    "source_scope": str(row.get("source_scope") or ""),
                    "id": f"__geom_row_{index:03d}",
                    "source": "geometry_placeholder",
                    "row_index": index,
                    "rectangle": rect,
                    "popup_reason": row.get("popup_reason"),
                    "text_was_empty": True,
                    "click_point": click_point,
                    "click_strategy": "center_point_fallback",
                    "popup_block_classification": row.get("popup_block_classification"),
                    "recent_projects_block": bool(row.get("recent_projects_block")),
                    "recent_project_entry": recent_project_entry,
                    "stateful_menu_block": stateful_menu_block,
                    "raw_text_sources": raw_text_sources,
                    "text_confidence": text_confidence,
                }
                actionable = True
                dispatch_type = "click"
                logger.info(
                    "REPLACED_EMPTY_POPUP_ROW_WITH_PLACEHOLDER row_index={:02d}",
                    index,
                )
                logger.info(
                    "GEOM_PLACEHOLDER_CREATED row_index={:02d} rect={} popup_reason={}",
                    index,
                    rect,
                    row.get("popup_reason"),
                )
                placeholder_count += 1
            elif not bool(row.get("is_separator")):
                logger.info(
                    "DBG_MENU_BUILD_FILTER_REASON state={} top_menu={} row_index={} reason=empty_popup_text_non_actionable row_text={!r} rectangle={} popup_reason={} topbar_like={} popup_like={}",
                    state_id,
                    top_menu,
                    index,
                    row.get("text"),
                    rect,
                    row.get("popup_reason"),
                    topbar_like,
                    popup_like,
                )
                filtered_counts["empty_popup_text_non_actionable"] += 1
                continue
        meta.setdefault("popup_block_classification", row.get("popup_block_classification", "normal_popup"))
        meta.setdefault("recent_projects_block", bool(row.get("recent_projects_block")))
        meta.setdefault("recent_project_entry", recent_project_entry)
        meta.setdefault("stateful_menu_block", stateful_menu_block)
        mapped.append(
            RuntimeMenuRow(
                state_id=state_id,
                top_menu=top_menu,
                row_index=index,
                menu_path=[clean_menu_title(top_menu), title_clean],
                text=title_clean,
                normalized_text=normalized_title,
                rectangle=rect,
                center_x=int(row.get("center_x") or meta.get("click_point", {}).get("x") or 0),
                center_y=int(row.get("center_y") or meta.get("click_point", {}).get("y") or 0),
                is_separator=bool(row.get("is_separator")),
                source_scope=str(row.get("source_scope") or ""),
                fragments=list(row.get("fragments") or []),
                enabled_guess=enabled_guess,
                discovered_in_state=state_id,
                raw_text_sources=raw_text_sources,
                text_confidence=text_confidence,
                actionable=actionable,
                dispatch_type=dispatch_type,
                action_type="unknown",
                recent_project_entry=recent_project_entry,
                stateful_menu_block=stateful_menu_block,
                meta=meta,
            )
        )
        logger.info(
            "DBG_WINWATT_NORMAL_MENU_ROW state={} top_menu={} row_index={} text={!r} normalized_text={} source_scope={} separator={} enabled_guess={} rectangle={} depth=1",
            state_id,
            top_menu,
            index,
            title_clean,
            normalized_title,
            row.get("source_scope"),
            bool(row.get("is_separator")),
            _guess_enabled(row),
            row.get("rectangle"),
        )
    deduped: list[RuntimeMenuRow] = []
    dedupe_groups: dict[tuple[str, tuple[int, int, int, int] | None, str, str], RuntimeMenuRow] = {}
    deduped_rows = 0
    for mapped_row in mapped:
        raw_sources = tuple(str(source) for source in mapped_row.raw_text_sources if str(source))
        source_scope_pattern = f"{mapped_row.source_scope}|{','.join(raw_sources) or 'none'}"
        dedupe_key = (
            mapped_row.normalized_text,
            _rect_signature(mapped_row.rectangle),
            ",".join(raw_sources) or "none",
            mapped_row.meta.get("source", ""),
        )
        existing = dedupe_groups.get(dedupe_key)
        if existing is None:
            dedupe_groups[dedupe_key] = mapped_row
            deduped.append(mapped_row)
            continue
        deduped_rows += 1
        existing_sources = list(dict.fromkeys([*existing.raw_text_sources, *mapped_row.raw_text_sources]))
        existing.raw_text_sources = existing_sources
        existing.meta["deduped_row_indices"] = list(dict.fromkeys([*list(existing.meta.get("deduped_row_indices") or [existing.row_index]), mapped_row.row_index]))
        logger.info(
            "MENU_ROW_DEDUP_APPLIED state={} top_menu={} normalized_text={} kept_row_index={} dropped_row_index={} rectangle={} source_scope_pattern={}",
            state_id,
            top_menu,
            mapped_row.normalized_text,
            existing.row_index,
            mapped_row.row_index,
            mapped_row.rectangle,
            source_scope_pattern,
        )
    mapped = deduped
    logger.info(
        "MENU_ROW_BUILD_SUMMARY state={} top_menu={} input_rows={} mapped_rows={} placeholders={} filtered_overlap={} filtered_empty_non_actionable={} rejected_foreign_rows={} deduped_rows={}",
        state_id,
        top_menu,
        len(rows),
        len(mapped),
        placeholder_count,
        filtered_counts["top_level_overlap"],
        filtered_counts["empty_popup_text_non_actionable"],
        rejected_foreign_rows,
        deduped_rows,
    )
    _log_phase_timing("_build_menu_rows_from_popup_rows", started_at, state_id=state_id, top_menu=top_menu, input_rows=len(rows), mapped_rows=len(mapped))
    return mapped


def _hover_row(row: dict[str, Any]) -> None:
    try:
        from pywinauto import mouse

        mouse.move(coords=(int(row.get("center_x") or 0), int(row.get("center_y") or 0)))
    except Exception:
        return


def _activate_row_for_exploration(row: RuntimeMenuRow, popup_rows: list[dict[str, Any]]) -> None:
    options = diagnostic_options()
    popup_count = len(popup_rows) if popup_rows is not None else 0
    popup_visible_now, topbar_visible_now = menu_helpers._popup_visibility_counts(popup_rows or [])
    meta = dict(row.meta)
    placeholder = _is_placeholder_row(row)
    logger.info(
        "DBG_PLACEHOLDER_TRAVERSAL_CANDIDATE path={} row_index={} placeholder={} action_type={} source_scope={} meta={} popup_visible_count={} topbar_visible_count={} diagnostic_fast_mode={}",
        row.menu_path,
        row.row_index,
        placeholder,
        row.dispatch_type,
        row.source_scope,
        meta,
        popup_visible_now,
        topbar_visible_now,
        options.diagnostic_fast_mode,
    )
    decision = "click_structured_row"
    if placeholder and meta.get("click_point"):
        decision = "click_placeholder_point"
    elif placeholder and row.dispatch_type == "hover":
        decision = "hover_placeholder"
    logger.info(
        "DBG_PLACEHOLDER_TRAVERSAL_DECISION path={} decision={} action_type={} source_scope={} popup_visible_count={} popup_rows_count={} meta_source={} click_strategy={}",
        row.menu_path,
        decision,
        row.dispatch_type,
        row.source_scope,
        popup_visible_now,
        popup_count,
        meta.get("source_scope", row.source_scope),
        meta.get("click_strategy"),
    )
    try:
        if decision == "click_placeholder_point":
            from pywinauto import mouse

            point = meta.get("click_point") or {}
            mouse.click(button="left", coords=(int(point.get("x") or row.center_x), int(point.get("y") or row.center_y)))
            return
        if decision == "hover_placeholder":
            _hover_row(asdict(row))
            return
        menu_helpers.click_structured_popup_row(popup_rows, row.row_index)
        return
    except Exception as exc:
        logger.info(
            "DBG_WINWATT_STRUCTURED_ROW_CLICK_EXCEPTION exception_class={} exception_message={} current_path={} fallback_to_hover=True popup_rows_count={}",
            exc.__class__.__name__,
            str(exc),
            row.menu_path,
            popup_count,
        )
        logger.debug("structured row click failed; fallback to hover path={} error={}", row.menu_path, exc)
    _hover_row(asdict(row))


def _single_row_probe_target_payload(*, top_menu: str, row: RuntimeMenuRow) -> dict[str, Any]:
    meta = dict(row.meta)
    click_point = dict(meta.get("click_point") or {"x": row.center_x, "y": row.center_y})
    return {
        "top_menu": top_menu,
        "row_index": row.row_index,
        "text": row.text,
        "target_rect": dict(row.rectangle),
        "target_click_point": click_point,
        "source_scope": meta.get("source_scope", row.source_scope),
    }


def _hover_single_row_probe_target(*, target: RuntimeMenuRow, top_menu: str, hover_pause_s: float = 0.05) -> dict[str, Any]:
    payload = _single_row_probe_target_payload(top_menu=top_menu, row=target)
    _hover_row({"center_x": payload["target_click_point"]["x"], "center_y": payload["target_click_point"]["y"]})
    if hover_pause_s > 0:
        time.sleep(hover_pause_s)
    logger.info(
        "SINGLE_ROW_PROBE_HOVER top_menu={} row_index={} source_scope={} target_rect={} target_click_point={} hover_pause_s={}",
        payload["top_menu"],
        payload["row_index"],
        payload["source_scope"],
        payload["target_rect"],
        payload["target_click_point"],
        hover_pause_s,
    )
    return payload


def _dispatch_single_row_probe_click(
    *,
    target: RuntimeMenuRow,
    popup_rows: list[dict[str, Any]],
    top_menu: str,
    pre_click_pause_s: float = 0.05,
    post_click_pause_s: float = 0.1,
) -> dict[str, Any]:
    payload = _single_row_probe_target_payload(top_menu=top_menu, row=target)
    click_point = payload["target_click_point"]
    logger.info(
        "SINGLE_ROW_PROBE_CLICK_START top_menu={} row_index={} source_scope={} target_rect={} target_click_point={} click_method={} popup_rows_count={}",
        payload["top_menu"],
        payload["row_index"],
        payload["source_scope"],
        payload["target_rect"],
        click_point,
        "explicit_mouse_down_up_after_move",
        len(popup_rows or []),
    )
    ensure_main_window_foreground_before_click(action_label=f"single_row_probe_click[{target.row_index}]", allow_dialog=True)
    from pywinauto import mouse

    coords = (int(click_point.get("x") or target.center_x), int(click_point.get("y") or target.center_y))
    mouse.move(coords=coords)
    if pre_click_pause_s > 0:
        time.sleep(pre_click_pause_s)
    mouse.press(button="left", coords=coords)
    mouse.release(button="left", coords=coords)
    logger.info(
        "SINGLE_ROW_PROBE_CLICK_DISPATCHED top_menu={} row_index={} source_scope={} target_rect={} target_click_point={} click_method={} pre_click_pause_s={} post_click_pause_s={}",
        payload["top_menu"],
        payload["row_index"],
        payload["source_scope"],
        payload["target_rect"],
        click_point,
        "explicit_mouse_down_up_after_move",
        pre_click_pause_s,
        post_click_pause_s,
    )
    if post_click_pause_s > 0:
        time.sleep(post_click_pause_s)
    payload["click_method"] = "explicit_mouse_down_up_after_move"
    payload["dispatched"] = True
    logger.info(
        "SINGLE_ROW_PROBE_CLICK_DONE top_menu={} row_index={} source_scope={} target_rect={} target_click_point={} click_method={} dispatched={}",
        payload["top_menu"],
        payload["row_index"],
        payload["source_scope"],
        payload["target_rect"],
        click_point,
        payload["click_method"],
        payload["dispatched"],
    )
    return payload


def _detect_child_rows(parent_row: dict[str, Any], all_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rect = parent_row.get("rectangle") or {}
    p_left, p_top, p_right, p_bottom = int(rect.get("left", 0)), int(rect.get("top", 0)), int(rect.get("right", 0)), int(rect.get("bottom", 0))
    children: list[dict[str, Any]] = []
    for row in all_rows:
        r = row.get("rectangle") or {}
        left, top = int(r.get("left", 0)), int(r.get("top", 0))
        if left <= p_right + 8:
            continue
        if top < p_top - 120 or top > p_bottom + 220:
            continue
        children.append(row)
    children.sort(key=lambda item: int((item.get("rectangle") or {}).get("top", 0)))
    return children


def _is_system_menu(top_menu: str) -> bool:
    return normalize_menu_title(top_menu) == normalize_menu_title(menu_helpers.SYSTEM_MENU_TITLE)


def _is_primary_normal_top_menu(top_menu: str) -> bool:
    return not _is_system_menu(top_menu)


def _filter_normal_popup_rows(
    rows: list[dict[str, Any]],
    *,
    canonical_top_menu_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for row in rows:
        normalized_text = normalize_menu_title(str(row.get("text") or ""))
        if bool(row.get("topbar_candidate")):
            continue
        if canonical_top_menu_names and normalized_text and normalized_text in canonical_top_menu_names:
            continue
        filtered.append(row)
    return filtered


def _summarize_normal_popup_rows(
    rows: list[dict[str, Any]],
    *,
    canonical_top_menu_names: set[str] | None = None,
) -> tuple[int, int, list[dict[str, Any]]]:
    popup_like_count = sum(
        1
        for row in rows
        if bool(row.get("popup_candidate")) or (
            "popup_candidate" not in row and not bool(row.get("topbar_candidate"))
        )
    )
    topbar_like_count = sum(1 for row in rows if bool(row.get("topbar_candidate")))
    filtered_rows = _filter_normal_popup_rows(rows, canonical_top_menu_names=canonical_top_menu_names)
    return popup_like_count, topbar_like_count, filtered_rows


def _has_valid_normal_popup_rows(
    rows: list[dict[str, Any]],
    *,
    canonical_top_menu_names: set[str] | None = None,
) -> tuple[bool, int, int, list[dict[str, Any]], str]:
    popup_like_count, topbar_like_count, filtered_rows = _summarize_normal_popup_rows(
        rows,
        canonical_top_menu_names=canonical_top_menu_names,
    )
    return popup_like_count > 0 and bool(filtered_rows), popup_like_count, topbar_like_count, filtered_rows, "normal_popup"


def _open_and_capture_root_menu(
    *,
    state_id: str,
    top_menu: str,
    canonical_top_menu_names: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    logger.info(
        "DBG_WINWATT_NORMAL_MENU_OPEN_START state={} top_menu={} menu_kind={}",
        state_id,
        top_menu,
        "normal" if _is_primary_normal_top_menu(top_menu) else "system",
    )
    before_click = capture_state_snapshot(state_id)
    if _is_system_menu(top_menu):
        main_window = get_cached_main_window()
        menu_helpers.open_system_menu(main_window)
        popup_rows = menu_helpers.capture_system_menu_popup()
        logger.info(
            "DBG_WINWATT_SYSTEM_MENU_MAPPING_ROOT state={} top_menu={} row_count={} note=system_menu_is_separate_from_menubar",
            state_id,
            top_menu,
            len(popup_rows),
        )
    else:
        popup_rows = []
        for attempt in range(2):
            if attempt:
                logger.info(
                    "DBG_WINWATT_NORMAL_MENU_RETRY_OPEN state={} top_menu={} attempt={}",
                    state_id,
                    top_menu,
                    attempt + 1,
                )
                restore_clean_menu_baseline(state_id=state_id, stage=f"retry_open:{top_menu}:{attempt + 1}")
            menu_helpers.click_top_menu_item(top_menu)
            candidate_rows = menu_helpers.capture_menu_popup_snapshot()
            snapshot = capture_state_snapshot(state_id)
            classification, filtered_rows, popup_meta = _classify_popup_block(
                top_menu=top_menu,
                rows=candidate_rows,
                snapshot=snapshot,
                canonical_top_menu_names=canonical_top_menu_names,
            )
            valid_popup = popup_meta["popup_like_count"] > 0 and bool(filtered_rows)
            popup_like_count = popup_meta["popup_like_count"]
            topbar_like_count = popup_meta["topbar_like_count"]
            if valid_popup:
                if classification == "recent_projects_block":
                    logger.info("RECENT_PROJECT_BLOCK_ACCEPTED state={} top_menu={} attempt={} accepted_rows={} empty_popup_rows={} popup_like_count={}", state_id, top_menu, attempt + 1, popup_meta["accepted_row_count"], popup_meta["empty_popup_row_count"], popup_like_count)
                logger.info("RECENT_PROJECT_BLOCK_SUMMARY state={} top_menu={} attempt={} popup_block_classification={} recent_projects_block={} stateful_menu_block={} accepted_rows={} filtered_rows={}", state_id, top_menu, attempt + 1, classification, classification == "recent_projects_block", classification == "recent_projects_block", popup_meta["accepted_row_count"], popup_meta["filtered_row_count"])
                logger.info(
                    "DBG_WINWATT_NORMAL_MENU_OPEN_VALIDATED state={} top_menu={} attempt={} raw_row_count={} popup_like_count={} topbar_like_count={}",
                    state_id,
                    top_menu,
                    attempt + 1,
                    len(candidate_rows),
                    popup_like_count,
                    topbar_like_count,
                )
                logger.info(
                    "DBG_WINWATT_NORMAL_MENU_POPUP_ROWS_ACCEPTED state={} top_menu={} attempt={} accepted_row_count={}",
                    state_id,
                    top_menu,
                    attempt + 1,
                    len(filtered_rows),
                )
                popup_rows = filtered_rows
                break
            if classification in {"recent_projects_block", "ambiguous_empty_block"}:
                logger.info("RECENT_PROJECT_BLOCK_REJECTED state={} top_menu={} attempt={} popup_block_classification={} popup_like_count={} filtered_rows={} empty_popup_rows={}", state_id, top_menu, attempt + 1, classification, popup_like_count, popup_meta["filtered_row_count"], popup_meta["empty_popup_row_count"])
            logger.info(
                "DBG_WINWATT_NORMAL_MENU_OPEN_NO_POPUP state={} top_menu={} attempt={} raw_row_count={} popup_like_count={} topbar_like_count={} filtered_row_count={}",
                state_id,
                top_menu,
                attempt + 1,
                len(candidate_rows),
                popup_like_count,
                topbar_like_count,
                len(filtered_rows),
            )
    after_click = capture_state_snapshot(state_id)
    top_transition = detect_dialog_or_window_transition(before_click, after_click, child_rows=popup_rows)
    if _is_primary_normal_top_menu(top_menu):
        popup_like_count, topbar_like_count, filtered_rows = _summarize_normal_popup_rows(
            popup_rows,
            canonical_top_menu_names=canonical_top_menu_names,
        )
        if not filtered_rows and popup_like_count == 0:
            top_transition = dict(top_transition)
            top_transition["result_type"] = "open_failed_no_popup"
        logger.info(
            "DBG_WINWATT_NORMAL_MENU_OPEN_RESULT state={} top_menu={} result_type={} raw_row_count={} filtered_row_count={} popup_like_count={} topbar_like_count={}",
            state_id,
            top_menu,
            top_transition.get("result_type"),
            len(popup_rows),
            len(filtered_rows),
            popup_like_count,
            topbar_like_count,
        )
        logger.info(
            "DBG_WINWATT_NORMAL_MENU_POPUP_SUMMARY state={} top_menu={} depth=1 rows={} popup_like_count={} topbar_like_count={}",
            state_id,
            top_menu,
            len(filtered_rows),
            popup_like_count,
            topbar_like_count,
        )
        popup_rows = filtered_rows
    return popup_rows, top_transition


def _find_popup_row_by_title(rows: list[dict[str, Any]], title: str) -> dict[str, Any] | None:
    wanted = normalize_menu_title(title)
    for row in rows:
        if bool(row.get("is_separator")):
            continue
        if normalize_menu_title(str(row.get("text") or "")) == wanted:
            return row
    return None


def _popup_row_identity(row: RuntimeMenuRow | dict[str, Any]) -> dict[str, Any]:
    source = asdict(row) if isinstance(row, RuntimeMenuRow) else dict(row)
    rect = dict(source.get("rectangle") or {})
    meta = dict(source.get("meta") or {})
    click_point = dict(meta.get("click_point") or {})
    return {
        "normalized_text": normalize_menu_title(str(source.get("text") or "")),
        "rectangle": rect,
        "center_x": int(source.get("center_x") or 0),
        "center_y": int(source.get("center_y") or 0),
        "enabled": source.get("enabled_guess", source.get("enabled")),
        "source_scope": str(source.get("source_scope") or ""),
        "click_point": click_point,
        "placeholder_source": str(meta.get("source") or ""),
        "popup_reason": str(source.get("popup_reason") or meta.get("popup_reason") or ""),
    }


def _find_matching_popup_row(rows: list[dict[str, Any]], target_row: RuntimeMenuRow) -> tuple[int, dict[str, Any]] | None:
    target = _popup_row_identity(target_row)
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for index, row in enumerate(rows):
        current = _popup_row_identity(row)
        score = 0
        if target["normalized_text"] and current["normalized_text"] == target["normalized_text"]:
            score += 100
        if target["source_scope"] and current["source_scope"] == target["source_scope"]:
            score += 10
        if target["enabled"] is not None and current["enabled"] == target["enabled"]:
            score += 5
        if target["placeholder_source"] and current["placeholder_source"] == target["placeholder_source"]:
            score += 5
        if target["popup_reason"] and current["popup_reason"] == target["popup_reason"]:
            score += 5
        if target["click_point"] and current["click_point"]:
            score -= abs(int(target["click_point"].get("x", 0)) - int(current["click_point"].get("x", 0)))
            score -= abs(int(target["click_point"].get("y", 0)) - int(current["click_point"].get("y", 0)))
        score -= abs(target["center_x"] - current["center_x"])
        score -= abs(target["center_y"] - current["center_y"])
        candidates.append((score, index, row))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, index, row = candidates[0]
    return index, row


def _action_state_classification(
    *,
    transition: dict[str, Any],
    opens_submenu: bool,
    opens_modal: bool,
) -> str:
    if transition.get("project_open_state_transition"):
        return "opens_project_and_changes_runtime_state"
    if transition.get("recent_project_candidate"):
        return "recent_project_entry"
    if opens_submenu:
        return "opens_submenu"
    if opens_modal:
        return "opens_modal"
    if transition.get("menu_state_changed"):
        return "changes_menu_state"
    if transition.get("result_type") in {
        "dialog_opened",
        "window_opened",
        "child_window_opened",
        "mdi_child_opened",
        "internal_window_opened",
        "internal_child_window_opened",
        "main_window_disabled_modal_likely",
    }:
        return "changes_menu_state"
    if transition.get("attempted"):
        return "executes_command"
    return "unknown"


def _safe_depth_decision(
    *,
    state_id: str,
    path: list[str],
    current_depth: int,
    max_depth: int | None,
    action_state_classification: str,
) -> bool:
    if max_depth is not None and max_depth >= 0 and current_depth >= max_depth:
        logger.info(
            "SAFE_DEPTH_BLOCKED state={} path={} current_depth={} max_depth={} action_state_classification={} reason=max_depth_reached",
            state_id,
            path,
            current_depth,
            max_depth,
            action_state_classification,
        )
        return False
    if action_state_classification == "opens_submenu":
        logger.info(
            "SAFE_DEPTH_ALLOWED state={} path={} current_depth={} next_depth={} action_state_classification={}",
            state_id,
            path,
            current_depth,
            current_depth + 1,
            action_state_classification,
        )
        return True
    if action_state_classification == "recent_project_entry":
        logger.info(
            "SAFE_DEPTH_BLOCKED state={} path={} current_depth={} max_depth={} action_state_classification={} reason=recent_project_entries_are_stateful_leafs",
            state_id,
            path,
            current_depth,
            max_depth,
            action_state_classification,
        )
        return False
    logger.info(
        "SAFE_DEPTH_BLOCKED state={} path={} current_depth={} max_depth={} action_state_classification={} reason=non_submenu_branch",
        state_id,
        path,
        current_depth,
        max_depth,
        action_state_classification,
    )
    return False


def _derive_action_type(*, classification: str | None, provable_change: bool, action_like: bool) -> str:
    normalized = str(classification or "unknown")
    if normalized in {
        "dialog_opened",
        "window_opened",
        "child_window_opened",
        "mdi_child_opened",
        "internal_window_opened",
        "internal_child_window_opened",
        "main_window_disabled_modal_likely",
        "modal_opened",
    }:
        return "functional_action"
    if normalized == "transient_hint_opened":
        return "transient_ui_only"
    if normalized in {"no_observable_effect", "target_unresolved"} and not provable_change:
        return "no_effect"
    if action_like and provable_change:
        return "functional_action"
    if provable_change:
        return "unknown"
    return "no_effect"


def _classify_transition_action_type(*, transition: dict[str, Any], action_state_classification: str, opens_submenu: bool, opens_modal: bool) -> str:
    result_type = str(transition.get("result_type") or "unknown")
    functional_classifications = {
        "dialog_opened",
        "window_opened",
        "child_window_opened",
        "mdi_child_opened",
        "internal_window_opened",
        "internal_child_window_opened",
        "main_window_disabled_modal_likely",
        "modal_opened",
        "child_popup_opened",
    }
    functional_states = {
        "opens_submenu",
        "opens_modal",
        "changes_menu_state",
        "opens_project_and_changes_runtime_state",
        "recent_project_entry",
    }
    if opens_submenu or opens_modal or result_type in functional_classifications or action_state_classification in functional_states:
        return "functional_action"
    if result_type == "transient_hint_opened":
        return "transient_ui_only"
    if result_type == "no_observable_effect":
        return "no_effect"
    if result_type == "unknown" and action_state_classification == "unknown":
        return "unknown"
    return "unknown"


def _action_discovery_policy(action_type: str) -> dict[str, bool]:
    return {
        "treat_as_navigation": action_type == "functional_action",
        "expand_children": action_type == "functional_action",
        "retry_on_next_pass": action_type not in {"transient_ui_only", "no_effect"},
    }


def build_action_discovery_report(probe_results: list[dict[str, Any]]) -> dict[str, Any]:
    report: dict[str, list[dict[str, Any]]] = {}
    for item in probe_results:
        top_menu = str(item.get("top_menu") or "<unknown>")
        summary = dict(item.get("summary") or {})
        row_action_type = str(summary.get("action_type") or _derive_action_type(
            classification=summary.get("final_classification") or item.get("final_classification"),
            provable_change=bool(summary.get("provable_change")),
            action_like=bool(summary.get("action_like")),
        ))
        row_entry = {
            "row": {
                "text": item.get("probe_row_text"),
                "row_index": item.get("probe_row_index"),
            },
            "classification": summary.get("final_classification") or item.get("final_classification"),
            "action_type": row_action_type,
            "policy": _action_discovery_policy(row_action_type),
        }
        report.setdefault(top_menu, []).append(row_entry)
    return {"top_menus": report}


def _build_action_catalog_entry(
    *,
    path: list[str],
    action_type: str,
    action_state_classification: str,
    opens_modal: bool,
    opens_submenu: bool,
    changes_menu_state: bool,
    opens_project_and_changes_runtime_state: bool,
    traversal_depth: int,
    skip_reason: str | None = None,
) -> dict[str, Any]:
    policy = _action_discovery_policy(action_type)
    entry = {
        "path": list(path),
        "action_type": action_type,
        "action_state_classification": action_state_classification,
        "opens_modal": opens_modal,
        "opens_submenu": opens_submenu,
        "changes_menu_state": changes_menu_state,
        "opens_project_and_changes_runtime_state": opens_project_and_changes_runtime_state,
        "traversal_depth": traversal_depth,
        "treat_as_navigation": policy["treat_as_navigation"],
        "expand_children": policy["expand_children"],
        "retry_on_next_pass": policy["retry_on_next_pass"],
    }
    if skip_reason:
        entry["skip_reason"] = skip_reason
    top_menu_key = path[0] if path else "<unknown>"
    ACTION_CATALOG_LOG_STATS[top_menu_key][action_state_classification or action_type or "unknown"] += 1
    if skip_reason:
        SKIP_REASON_LOG_STATS[top_menu_key][skip_reason] += 1
    if is_diagnostic_log_profile():
        logger.info("ACTION_CATALOG_ENTRY state_path={} entry={}", path, entry)
    else:
        logger.debug("ACTION_CATALOG_ENTRY state_path={} entry={}", path, entry)
    return entry


def _evaluate_action_admission(
    *,
    row: RuntimeMenuRow,
    path: list[str],
    action_state_classification: str,
    transition: dict[str, Any],
    opens_submenu: bool,
    opens_modal: bool,
    skip_reason: str | None,
    traversal_depth: int,
    probe_evidence: dict[str, Any] | None = None,
) -> tuple[bool, str | None, str | None]:
    result_type = str(transition.get("result_type") or "no_observable_effect")
    text_confidence = _row_text_confidence(row)
    legacy_text_only = _row_has_legacy_text_only(row)
    placeholder = _is_placeholder_row(row)
    structural_interaction_evidence = bool(
        not placeholder
        and row.is_separator is False
        and row.enabled_guess is True
        and text_confidence in {"high", "medium"}
        and not legacy_text_only
    )
    probe_evidence = dict(probe_evidence or {})
    probe_result_type = str(probe_evidence.get("result_type") or "")
    probe_evidence_supports_admission = bool(
        (
            probe_result_type in ACTION_PROBE_ADMISSION_RESULT_TYPES
            or probe_evidence.get("evidence_strength") == "strong"
        )
        and _placeholder_has_finalizable_probe_evidence(row, probe_evidence)
    )
    strong_interaction_evidence = _row_has_strong_interaction_evidence(row, probe_evidence)
    noisy_unknown_legacy_row = bool(
        row.action_type == "unknown"
        and action_state_classification == "unknown"
        and text_confidence == "medium"
        and legacy_text_only
        and not strong_interaction_evidence
    )
    separate_interaction_evidence = bool(
        opens_submenu
        or opens_modal
        or transition.get("menu_state_changed")
        or transition.get("project_open_state_transition")
        or transition.get("dialog_detected")
        or result_type in {
            "dialog_opened",
            "window_opened",
            "child_window_opened",
            "mdi_child_opened",
            "internal_window_opened",
            "internal_child_window_opened",
            "main_window_disabled_modal_likely",
            "modal_opened",
            "main_window_disabled",
            "project_open_state_transition",
            "child_popup_opened",
            "popup_closed_with_foreground_change",
        }
        or action_state_classification in {
            "opens_submenu",
            "opens_modal",
            "changes_menu_state",
            "opens_project_and_changes_runtime_state",
            "recent_project_entry",
        }
        or structural_interaction_evidence
        or probe_evidence_supports_admission
    )

    rejection_reason: str | None = None
    admission_reason: str | None = None

    if row.is_separator:
        rejection_reason = "separator_row"
    elif row.enabled_guess is False:
        rejection_reason = "disabled_menu_item"
    elif row.recent_project_entry and not skip_reason:
        rejection_reason = "recent_project_entry"
    elif placeholder and not separate_interaction_evidence:
        rejection_reason = "placeholder_without_state_change"
    elif text_confidence in {"none", "low"} and not separate_interaction_evidence:
        rejection_reason = f"text_confidence_{text_confidence}_without_interaction_evidence"
    elif noisy_unknown_legacy_row:
        rejection_reason = "unknown_legacy_popup_noise_suppressed"
    elif legacy_text_only and not separate_interaction_evidence:
        rejection_reason = "legacy_text_only_without_interaction_evidence"
    elif result_type in {"no_visible_change", "no_observable_effect"} and not separate_interaction_evidence:
        rejection_reason = "no_visible_change_without_interaction_evidence"
    elif skip_reason:
        admission_reason = f"policy_cataloged:{skip_reason}"
    elif structural_interaction_evidence:
        admission_reason = "interaction_evidence:validated_enabled_menu_row"
    elif separate_interaction_evidence:
        admission_reason = f"interaction_evidence:{probe_result_type or action_state_classification or result_type}"
    elif action_state_classification == "unknown":
        logger.info(
            "ACTION_UNKNOWN_SUPPRESSED top_menu={} path={} traversal_depth={} result_type={} placeholder={} text_confidence={} legacy_text_only={}",
            path[0] if path else "<unknown>",
            path,
            traversal_depth,
            result_type,
            placeholder,
            text_confidence,
            legacy_text_only,
        )
        rejection_reason = "unknown_classification_suppressed"
    else:
        admission_reason = f"validated_action:{action_state_classification or row.action_type or row.dispatch_type}"

    if rejection_reason:
        logger.info(
            "ACTION_ADMISSION_REJECTED top_menu={} path={} traversal_depth={} reason={} classification={} result_type={} placeholder={} text_confidence={} raw_text_sources={} skip_reason={}",
            path[0] if path else "<unknown>",
            path,
            traversal_depth,
            rejection_reason,
            action_state_classification,
            result_type,
            placeholder,
            text_confidence,
            list(row.raw_text_sources),
            skip_reason,
        )
        logger.info(
            "ACTION_STRUCTURE_ONLY_ROW top_menu={} path={} traversal_depth={} reason={}",
            path[0] if path else "<unknown>",
            path,
            traversal_depth,
            rejection_reason,
        )
        return False, None, rejection_reason

    logger.info(
        "ACTION_ADMISSION_ACCEPTED top_menu={} path={} traversal_depth={} reason={} classification={} result_type={} placeholder={} text_confidence={} raw_text_sources={} skip_reason={}",
        path[0] if path else "<unknown>",
        path,
        traversal_depth,
        admission_reason,
        action_state_classification,
        result_type,
        placeholder,
        text_confidence,
        list(row.raw_text_sources),
        skip_reason,
    )
    return True, admission_reason, None


def log_action_catalog_summary() -> None:
    for top_menu, counts in sorted(ACTION_CATALOG_LOG_STATS.items()):
        logger.info("ACTION_CATALOG_SUMMARY top_menu={} counts={}", top_menu, dict(sorted(counts.items())))
    for top_menu, counts in sorted(SKIP_REASON_LOG_STATS.items()):
        logger.info("SKIP_REASON_SUMMARY top_menu={} counts={}", top_menu, dict(sorted(counts.items())))


def _build_state_transitions_from_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    transitions: list[dict[str, Any]] = []
    for action in actions:
        details = dict(action.get("event_details") or {})
        if not details.get("project_open_state_transition"):
            continue
        transition = {
            "path": list(action.get("menu_path") or []),
            "trigger": "opens_project_and_changes_runtime_state",
            "result_type": details.get("result_type"),
            "new_runtime_state": dict(details.get("new_runtime_state") or {}),
            "project_open_transition_reasons": dict(details.get("project_open_transition_reasons") or {}),
        }
        logger.info("STATE_TRANSITION_RECORDED transition={}", transition)
        transitions.append(transition)
    return transitions


def _build_state_atlas_entry(state_map: RuntimeStateMap) -> dict[str, Any]:
    entry = {
        "state_id": state_map.state_id,
        "canonical_top_menus": list(state_map.top_menus),
        "top_menu_rows": list(state_map.menu_rows),
        "action_catalog": list(state_map.action_catalog),
        "state_transitions": list(state_map.state_transitions),
        "action_discovery_report": {
            "top_menus": {
                top_menu: [
                    {
                        "menu_path": row.get("menu_path", []),
                        "action_type": row.get("action_type", "unknown"),
                    }
                    for row in state_map.menu_rows
                    if row.get("top_menu") == top_menu
                ]
                for top_menu in sorted({str(row.get("top_menu") or "<unknown>") for row in state_map.menu_rows})
            }
        },
    }
    logger.info(
        "STATE_ATLAS_ENTRY_CREATED state_id={} top_menus={} rows={} actions={} transitions={} top_menu_texts={} action_sample={} ",
        state_map.state_id,
        len(state_map.top_menus),
        len(state_map.menu_rows),
        len(state_map.action_catalog),
        len(state_map.state_transitions),
        [item.get("text") for item in state_map.top_menus],
        [item.get("path") for item in state_map.action_catalog[:3]],
    )
    return entry


def _build_runtime_state_atlas(*, states: list[RuntimeStateMap]) -> dict[str, Any]:
    atlas_states = {state.state_id: _build_state_atlas_entry(state) for state in states}
    return {
        "states": atlas_states,
        "state_order": [state.state_id for state in states],
    }


def _is_recent_projects_candidate(*, top_menu: str, path: list[str], row: RuntimeMenuRow) -> bool:
    if normalize_menu_title(top_menu) != normalize_menu_title("Fájl"):
        return False
    if row.recent_project_entry or bool(row.meta.get("recent_project_entry")):
        return True
    normalized_path = [normalize_menu_title(part) for part in path]
    if any(token in {"korábbiprojektek", "recentprojects"} for token in normalized_path):
        return True
    return len(path) == 2 and _is_placeholder_row(row) and row.row_index >= 4


def _invalidate_stale_menu_references(*, popup_state: PopupState | None, reason: str) -> None:
    if popup_state is not None:
        popup_state.current_menu_path = None
        popup_state.popup_handle = None
        popup_state.popup_rows = None
        popup_state.runtime_state_reset_required = True
    reset_top_menu_cache()
    logger.info("STALE_MENU_REFERENCES_INVALIDATED reason={}", reason)


def _refresh_runtime_state_after_project_open(*, state_id: str, transition: dict[str, Any], popup_state: PopupState | None) -> dict[str, Any]:
    _invalidate_stale_menu_references(
        popup_state=popup_state,
        reason="project_open_state_transition",
    )
    main_window = get_cached_main_window()
    main_title = _safe_call(main_window, "window_text", "") or ""
    logger.info("PROJECT_OPEN_STATE_TRANSITION state={} title={}", state_id, main_title)
    refreshed_snapshot = capture_state_snapshot(f"{state_id}_project_open_transition")
    refreshed_canonical_top_menus = get_canonical_top_menu_names(refreshed_snapshot.discovered_top_menus)
    logger.info("CANONICAL_TOP_MENUS_REFRESHED state={} menus={}", state_id, [item["raw"] for item in refreshed_canonical_top_menus["items"]])
    logger.info(
        "NEW_RUNTIME_STATE_AFTER_PROJECT_OPEN state={} title={} top_menus={}",
        state_id,
        refreshed_snapshot.main_window_title,
        [item["raw"] for item in refreshed_canonical_top_menus["items"]],
    )
    transition["project_open_state_transition"] = True
    transition["result_type"] = "project_open_state_transition"
    transition["new_runtime_state"] = {
        "main_window_title": refreshed_snapshot.main_window_title,
        "discovered_top_menus": list(refreshed_snapshot.discovered_top_menus),
    }
    return refreshed_canonical_top_menus


def _detect_project_open_transition(
    *,
    state_id: str,
    top_menu: str,
    path: list[str],
    row: RuntimeMenuRow,
    before_action: RuntimeStateSnapshot,
    after_action: RuntimeStateSnapshot,
    transition: dict[str, Any],
    popup_state: PopupState | None,
) -> bool:
    recent_candidate = bool(transition.get("recent_project_candidate")) or _is_recent_projects_candidate(top_menu=top_menu, path=path, row=row)
    if recent_candidate:
        logger.info("RECENT_PROJECT_ACTION_DETECTED state={} path={} policy={}", state_id, path, recent_projects_policy())
    if not recent_candidate:
        return False
    title_changed = before_action.main_window_title != after_action.main_window_title
    before_menus = {normalize_menu_title(item) for item in before_action.discovered_top_menus}
    after_menus = {normalize_menu_title(item) for item in after_action.discovered_top_menus}
    top_menus_changed = before_menus != after_menus
    recovery_success = bool((transition.get("project_open_recovery") or {}).get("success"))
    if not (title_changed or top_menus_changed or recovery_success):
        return False
    transition["project_open_transition_reasons"] = {
        "title_changed": title_changed,
        "top_menus_changed": top_menus_changed,
        "recovery_success": recovery_success,
    }
    _refresh_runtime_state_after_project_open(
        state_id=state_id,
        transition=transition,
        popup_state=popup_state,
    )
    return True


def _reopen_parent_popup_rows(
    *,
    state_id: str,
    top_menu: str,
    parent_path: list[str],
    canonical_top_menu_names: set[str] | None,
    popup_state: PopupState | None,
    force_ui_reopen: bool = False,
) -> list[dict[str, Any]]:
    started_at = time.monotonic()
    logger.info(
        "DBG_WINWATT_NORMAL_MENU_REOPEN_PARENT state={} top_menu={} parent_path={} cached_popup_path={} suppress_placeholder_top_menu_relist={}",
        state_id,
        top_menu,
        parent_path,
        getattr(popup_state, "current_menu_path", None) if popup_state is not None else None,
        diagnostic_options().suppress_placeholder_top_menu_relist,
    )
    normalized_parent = tuple(normalize_menu_title(part) for part in parent_path)
    if not force_ui_reopen and popup_state is not None and popup_state.popup_rows:
        reuse_allowed, reuse_rejection_reason = _popup_snapshot_belongs_to_current_parent(
            top_menu=top_menu,
            parent_path=parent_path,
            normalized_parent=normalized_parent,
            snapshot_rows=list(popup_state.popup_rows),
            popup_state=popup_state,
            canonical_top_menu_names=canonical_top_menu_names,
        )
        if reuse_allowed:
            cached = list(popup_state.popup_rows)
            logger.info(
                "POPUP_OWNERSHIP_CONFIRMED state={} top_menu={} normalized_parent={} popup_state_path={} row_count={}",
                state_id,
                top_menu,
                normalized_parent,
                getattr(popup_state, "current_menu_path", None),
                len(cached),
            )
            _log_phase_timing("reopen_parent_popup_rows", started_at, strategy="popup_state_reuse", row_count=len(cached), parent_path=" > ".join(parent_path))
            return cached
        logger.info(
            "POPUP_REUSE_REJECTED state={} top_menu={} normalized_parent={} popup_state_path={} reason={}",
            state_id,
            top_menu,
            normalized_parent,
            getattr(popup_state, "current_menu_path", None),
            reuse_rejection_reason,
        )

    if not restore_clean_menu_baseline(state_id=state_id, stage=f"reopen_parent:{' > '.join(parent_path)}"):
        return []

    if _is_system_menu(top_menu):
        main_window = get_cached_main_window()
        menu_helpers.open_system_menu(main_window)
        current_rows = menu_helpers.capture_system_menu_popup()
    else:
        menu_helpers.click_top_menu_item(top_menu)
        current_rows = menu_helpers.capture_menu_popup_snapshot()
        current_rows = _filter_normal_popup_rows(current_rows, canonical_top_menu_names=canonical_top_menu_names)

    for part in parent_path[1:]:
        row = _find_popup_row_by_title(current_rows, part)
        if row is None:
            logger.debug("reopen_parent_missing_part state={} top_menu={} part={}", state_id, top_menu, part)
            break

        _hover_row(row)
        menu_helpers.wait_for_new_menu_popup(
            menu_helpers._snapshot_keys(current_rows),
            timeout=POPUP_WAIT_TIMEOUT,
        )
        snapshot_rows = menu_helpers.capture_menu_popup_snapshot()
        snapshot_rows = _filter_normal_popup_rows(snapshot_rows, canonical_top_menu_names=canonical_top_menu_names)
        child_rows = _detect_child_rows(row, snapshot_rows)
        if canonical_top_menu_names:
            child_rows = [
                child_row
                for child_row in child_rows
                if not is_top_menu_like_popup_row(child_row, canonical_top_menu_names)
            ]
        if not child_rows:
            logger.debug("reopen_parent_missing_children state={} path={}", state_id, parent_path)
            break
        current_rows = child_rows

    if popup_state is not None:
        popup_state.current_menu_path = normalized_parent
        popup_state.popup_rows = list(current_rows)
    _log_phase_timing("reopen_parent_popup_rows", started_at, strategy="reopened", row_count=len(current_rows), parent_path=" > ".join(parent_path))
    return current_rows






def _capture_fresh_root_popup_for_sibling(
    *,
    state_id: str,
    top_menu: str,
    parent_path: list[str],
    target_row: RuntimeMenuRow,
    canonical_top_menu_names: set[str] | None,
    popup_state: PopupState | None,
    stage: str,
) -> tuple[list[dict[str, Any]], RuntimeMenuRow]:
    logger.info("ROOT_MENU_REOPEN_FOR_NEXT_SIBLING state={} top_menu={} parent_path={} next_after={}", state_id, top_menu, parent_path, stage)
    refreshed_rows = _reopen_parent_popup_rows(
        state_id=state_id,
        top_menu=top_menu,
        parent_path=parent_path,
        canonical_top_menu_names=canonical_top_menu_names,
        popup_state=popup_state,
        force_ui_reopen=True,
    )
    valid_popup = False
    popup_like_count = 0
    target_match = None
    if refreshed_rows:
        valid_popup, popup_like_count, _topbar_like_count, filtered_rows, _popup_block_classification = _has_valid_normal_popup_rows(
            refreshed_rows,
            canonical_top_menu_names=canonical_top_menu_names,
        )
        refreshed_rows = filtered_rows
        if valid_popup:
            target_match = _find_matching_popup_row(refreshed_rows, target_row)
    if not valid_popup or popup_like_count <= 0 or target_match is None:
        logger.error(
            "ROOT_MENU_REOPEN_FAILED state={} top_menu={} parent_path={} stage={} popup_visible={} popup_row_count={} target_reidentified={} target_path={}",
            state_id,
            top_menu,
            parent_path,
            stage,
            valid_popup,
            len(refreshed_rows),
            target_match is not None,
            target_row.menu_path,
        )
        logger.error(
            "NEXT_SIBLING_BLOCKED_NO_FRESH_POPUP state={} top_menu={} parent_path={} stage={} target_path={}",
            state_id,
            top_menu,
            parent_path,
            stage,
            target_row.menu_path,
        )
        raise RuntimeError(f"fresh root popup reopen failed for {' > '.join(target_row.menu_path)}")
    row_idx, matching_row = target_match
    refreshed_row = RuntimeMenuRow(
        state_id=target_row.state_id,
        top_menu=target_row.top_menu,
        row_index=row_idx,
        menu_path=target_row.menu_path,
        text=target_row.text,
        normalized_text=target_row.normalized_text,
        rectangle=dict(matching_row.get("rectangle") or target_row.rectangle),
        center_x=int(matching_row.get("center_x") or target_row.center_x),
        center_y=int(matching_row.get("center_y") or target_row.center_y),
        is_separator=target_row.is_separator,
        source_scope=str(matching_row.get("source_scope") or target_row.source_scope),
        fragments=list(matching_row.get("fragments") or target_row.fragments),
        enabled_guess=_guess_enabled(matching_row),
        discovered_in_state=target_row.discovered_in_state,
        raw_text_sources=list(matching_row.get("raw_text_sources") or target_row.raw_text_sources),
        text_confidence=str(matching_row.get("text_confidence") or target_row.text_confidence),
        actionable=target_row.actionable,
        dispatch_type=target_row.dispatch_type,
        action_type=target_row.action_type,
        recent_project_entry=target_row.recent_project_entry,
        stateful_menu_block=target_row.stateful_menu_block,
        meta=dict(target_row.meta),
    )
    logger.info("ROOT_MENU_REOPEN_EXECUTED state={} top_menu={} parent_path={} row_count={} target_path={}", state_id, top_menu, parent_path, len(refreshed_rows), target_row.menu_path)
    logger.info("FRESH_ROOT_SNAPSHOT_CAPTURED state={} top_menu={} parent_path={} row_count={}", state_id, top_menu, parent_path, len(refreshed_rows))
    return refreshed_rows, refreshed_row


def _foreground_window_info() -> dict[str, Any]:
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {}
        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        title_buf = ctypes.create_unicode_buffer(512)
        class_buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title_buf, 511)
        user32.GetClassNameW(hwnd, class_buf, 255)
        return {"handle": int(hwnd), "title": title_buf.value or "", "class_name": class_buf.value or "", "process_id": int(pid.value)}
    except Exception:
        return {}


def _control_type_name(control: Any) -> str:
    for attr in ("friendly_class_name",):
        try:
            value = getattr(control, attr)()
            if value:
                return str(value).strip().lower()
        except Exception:
            pass
    element_info = getattr(control, "element_info", None)
    control_type = getattr(element_info, "control_type", None)
    if control_type:
        return str(control_type).strip().lower()
    return ""


def _control_text_value(control: Any) -> str:
    for attr in ("window_text",):
        try:
            value = getattr(control, attr)()
            if value:
                return str(value).strip()
        except Exception:
            pass
    element_info = getattr(control, "element_info", None)
    name = getattr(element_info, "name", None)
    if name:
        return str(name).strip()
    return ""


def _uia_subtree_metrics(window: Any) -> dict[str, int]:
    if window is None:
        return {"child_count": 0, "descendant_count": 0}
    try:
        children = _safe_call(window, "children", []) or []
    except Exception:
        children = []
    try:
        descendants = _safe_call(window, "descendants", []) or []
    except Exception:
        descendants = []
    return {
        "child_count": len(children),
        "descendant_count": len(descendants),
    }


def _main_window_child_summary(window: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "child_control_types": {},
        "descendant_control_types": {},
        "child_window_like_count": 0,
        "descendant_window_like_count": 0,
        "title_bar_like_count": 0,
        "close_button_like_count": 0,
        "window_like_titles": [],
        "window_signatures": [],
    }
    if window is None:
        return summary
    try:
        children = list(_safe_call(window, "children", []) or [])
    except Exception:
        children = []
    try:
        descendants = list(_safe_call(window, "descendants", []) or [])
    except Exception:
        descendants = []

    child_types = Counter()
    descendant_types = Counter()
    window_like_titles: list[str] = []
    window_like_title_keys: set[str] = set()
    window_signatures: list[tuple[str, str, int, int, int, int]] = []
    window_signature_keys: set[tuple[str, str, int, int, int, int]] = set()
    title_bar_like_count = 0
    close_button_like_count = 0

    for control in children:
        control_type = _control_type_name(control)
        if control_type:
            child_types[control_type] += 1
        title = _control_text_value(control)
        if control_type in INTERNAL_CHILD_CONTROL_TYPES:
            title_key = title.lower()
            if title and title_key not in window_like_title_keys:
                window_like_titles.append(title)
                window_like_title_keys.add(title_key)
            rect_obj = _safe_call(control, "rectangle", None)
            rect = dict(rect_obj.__dict__) if rect_obj is not None and hasattr(rect_obj, "__dict__") else {}
            signature = (
                control_type,
                title_key,
                int(getattr(getattr(control, "element_info", control), "handle", 0) or 0),
                int(rect.get("left", 0)),
                int(rect.get("top", 0)),
                int(rect.get("right", 0) - rect.get("left", 0)),
            )
            if signature not in window_signature_keys:
                window_signature_keys.add(signature)
                window_signatures.append(signature)
    for control in descendants:
        control_type = _control_type_name(control)
        if control_type:
            descendant_types[control_type] += 1
        raw_title = _control_text_value(control)
        title = raw_title.lower()
        if control_type in INTERNAL_CHILD_CONTROL_TYPES and title and title not in window_like_title_keys:
            window_like_titles.append(raw_title)
            window_like_title_keys.add(title)
        if "title bar" in title or "titlebar" in title:
            title_bar_like_count += 1
        if control_type == "button" and title in {"close", "bezárás", "bezaras", "x"}:
            close_button_like_count += 1

    summary.update(
        {
            "child_control_types": dict(sorted(child_types.items())),
            "descendant_control_types": dict(sorted(descendant_types.items())),
            "child_window_like_count": sum(child_types.get(item, 0) for item in INTERNAL_CHILD_CONTROL_TYPES),
            "descendant_window_like_count": sum(descendant_types.get(item, 0) for item in INTERNAL_CHILD_CONTROL_TYPES),
            "title_bar_like_count": title_bar_like_count,
            "close_button_like_count": close_button_like_count,
            "window_like_titles": window_like_titles[:10],
            "window_signatures": window_signatures[:20],
        }
    )
    return summary


def _top_menu_expansion_summary(*, before_menus: list[str], after_menus: list[str]) -> dict[str, Any]:
    before_normalized = {normalize_menu_title(item) for item in before_menus if normalize_menu_title(item)}
    after_normalized = {normalize_menu_title(item) for item in after_menus if normalize_menu_title(item)}
    new_context_menus = sorted(after_normalized - before_normalized)
    context_matches = sorted(menu for menu in new_context_menus if menu in INTERNAL_CHILD_CONTEXT_MENU_NAMES)
    return {
        "before_count": len(before_menus),
        "after_count": len(after_menus),
        "count_diff": len(after_menus) - len(before_menus),
        "new_menus": new_context_menus,
        "context_menu_expanded": bool(context_matches),
        "context_menu_matches": context_matches,
    }


def _detect_internal_child_window_opened(*, subtree_diff: dict[str, Any], child_summary_before: dict[str, Any], child_summary_after: dict[str, Any], top_menu_expansion: dict[str, Any]) -> dict[str, Any]:
    descendant_growth = int(subtree_diff.get("descendant_count_diff") or 0)
    child_growth = int(subtree_diff.get("child_count_diff") or 0)
    window_like_growth = int(child_summary_after.get("descendant_window_like_count") or 0) - int(child_summary_before.get("descendant_window_like_count") or 0)
    title_bar_growth = int(child_summary_after.get("title_bar_like_count") or 0) - int(child_summary_before.get("title_bar_like_count") or 0)
    close_button_growth = int(child_summary_after.get("close_button_like_count") or 0) - int(child_summary_before.get("close_button_like_count") or 0)
    signals = {
        "descendant_growth": descendant_growth >= INTERNAL_CHILD_DESCENDANT_GROWTH_MIN,
        "child_growth": child_growth > 0,
        "window_like_growth": window_like_growth > 0,
        "context_menu_expanded": bool(top_menu_expansion.get("context_menu_expanded")),
        "chrome_detected": title_bar_growth > 0 or close_button_growth > 0,
    }
    before_signatures = {
        tuple(item) if isinstance(item, list) else item
        for item in list(child_summary_before.get("window_signatures") or [])
    }
    after_signatures = {
        tuple(item) if isinstance(item, list) else item
        for item in list(child_summary_after.get("window_signatures") or [])
    }
    new_child_signatures = sorted(after_signatures - before_signatures)
    detected = signals["descendant_growth"] and (
        signals["window_like_growth"]
        or signals["context_menu_expanded"]
        or signals["chrome_detected"]
        or signals["child_growth"]
    )
    result_type = "mdi_child_opened" if new_child_signatures else "internal_child_window_opened"
    return {
        "detected": detected,
        "result_type": result_type,
        "signals": signals,
        "descendant_growth": descendant_growth,
        "child_growth": child_growth,
        "window_like_growth": window_like_growth,
        "title_bar_growth": title_bar_growth,
        "close_button_growth": close_button_growth,
        "new_child_signatures": [list(item) for item in new_child_signatures[:10]],
    }


def _probe_snapshot(*, state_id: str, main_window: Any, popup_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    snapshot = capture_state_snapshot(state_id)
    windows = list(snapshot.visible_top_windows)
    popup_rows = list(popup_rows or [])
    return {
        "foreground_window": dict(snapshot.foreground_window or {}),
        "top_level_window_count": len(windows),
        "top_level_windows": windows,
        "main_window_enabled": snapshot.main_window_enabled,
        "main_window_visible": snapshot.main_window_visible,
        "popup_visible": bool(popup_rows),
        "popup_row_count": len(popup_rows),
        "discovered_top_menus": list(snapshot.discovered_top_menus),
        "top_menu_count": len(snapshot.discovered_top_menus),
        "uia_subtree": _uia_subtree_metrics(main_window),
        "main_window_child_summary": _main_window_child_summary(main_window),
        "runtime_snapshot": snapshot,
    }


def _classify_single_row_probe_diff(diff: dict[str, Any]) -> str:
    if diff.get("new_dialog_window"):
        return "dialog_opened"
    if diff.get("new_window"):
        return "window_opened"
    if (diff.get("internal_child_window_detection") or {}).get("detected"):
        return str((diff.get("internal_child_window_detection") or {}).get("result_type") or "internal_child_window_opened")
    if diff.get("transient_hint_window"):
        return "transient_hint_opened"
    if diff.get("popup_closed"):
        return "popup_closed"
    if diff.get("focus_changed"):
        return "focus_changed"
    return "no_observable_effect"


def _summarize_single_row_probe_diff(*, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_foreground = dict(before.get("foreground_window") or {})
    after_foreground = dict(after.get("foreground_window") or {})
    before_windows = list(before.get("top_level_windows") or [])
    after_windows = list(after.get("top_level_windows") or [])
    before_ids = {_window_identity(window) for window in before_windows}
    after_ids = {_window_identity(window) for window in after_windows}
    new_windows = [window for window in after_windows if _window_identity(window) not in before_ids]
    closed_windows = [window for window in before_windows if _window_identity(window) not in after_ids]
    transient_new_windows = [window for window in new_windows if _is_transient_window_snapshot(window)]
    functional_new_windows = [window for window in new_windows if not _is_transient_window_snapshot(window)]
    new_dialog_window = any(_is_modal_window_snapshot(window) for window in functional_new_windows)
    focus_changed = before_foreground != after_foreground
    popup_closed = bool(before.get("popup_visible")) and not bool(after.get("popup_visible"))
    before_subtree = dict(before.get("uia_subtree") or {})
    after_subtree = dict(after.get("uia_subtree") or {})
    subtree_diff = {
        "child_count_before": int(before_subtree.get("child_count") or 0),
        "child_count_after": int(after_subtree.get("child_count") or 0),
        "child_count_diff": int(after_subtree.get("child_count") or 0) - int(before_subtree.get("child_count") or 0),
        "descendant_count_before": int(before_subtree.get("descendant_count") or 0),
        "descendant_count_after": int(after_subtree.get("descendant_count") or 0),
        "descendant_count_diff": int(after_subtree.get("descendant_count") or 0) - int(before_subtree.get("descendant_count") or 0),
    }
    child_summary_before = dict(before.get("main_window_child_summary") or {})
    child_summary_after = dict(after.get("main_window_child_summary") or {})
    top_menu_expansion = _top_menu_expansion_summary(
        before_menus=list(before.get("discovered_top_menus") or []),
        after_menus=list(after.get("discovered_top_menus") or []),
    )
    internal_child_window_detection = _detect_internal_child_window_opened(
        subtree_diff=subtree_diff,
        child_summary_before=child_summary_before,
        child_summary_after=child_summary_after,
        top_menu_expansion=top_menu_expansion,
    )
    logger.info("SINGLE_ROW_PROBE_SUBTREE_SUMMARY before={} after={} before_child_summary={} after_child_summary={}", before_subtree, after_subtree, child_summary_before, child_summary_after)
    logger.info("SINGLE_ROW_PROBE_CONTEXT_MENU_EXPANSION result={}", top_menu_expansion)
    logger.info("SINGLE_ROW_PROBE_INTERNAL_CHILD_WINDOW_DETECTION result={}", internal_child_window_detection)
    diff = {
        "new_window_count": len(new_windows),
        "closed_window_count": len(closed_windows),
        "new_windows": new_windows,
        "functional_new_window_count": len(functional_new_windows),
        "functional_new_windows": functional_new_windows,
        "transient_hint_window_count": len(transient_new_windows),
        "transient_hint_windows": transient_new_windows,
        "closed_windows": closed_windows,
        "new_dialog_window": new_dialog_window,
        "new_window": bool(functional_new_windows) and not new_dialog_window,
        "transient_hint_window": bool(transient_new_windows),
        "popup_closed": popup_closed,
        "focus_changed": focus_changed,
        "main_window_enabled_changed": before.get("main_window_enabled") != after.get("main_window_enabled"),
        "top_level_window_count_diff": int(after.get("top_level_window_count") or 0) - int(before.get("top_level_window_count") or 0),
        "uia_subtree_diff": subtree_diff,
        "top_menu_expansion": top_menu_expansion,
        "main_window_child_summary_before": child_summary_before,
        "main_window_child_summary_after": child_summary_after,
        "internal_child_window_detection": internal_child_window_detection,
    }
    diff["classification"] = _classify_single_row_probe_diff(diff)
    return diff


def _select_probe_target_row(
    *,
    menu_rows: list[RuntimeMenuRow],
    probe_row_text: str | None,
    probe_row_index: int | None,
) -> tuple[RuntimeMenuRow | None, dict[str, Any]]:
    requested_text = str(probe_row_text or "")
    normalized_text = normalize_menu_title(requested_text)
    available_row_texts = [row.text for row in menu_rows]
    available_row_indices = [row.row_index for row in menu_rows]
    placeholder_count = sum(1 for row in menu_rows if _is_placeholder_row(row))
    requested_placeholder_text = ""
    placeholder_match = re.fullmatch(r"\[unlabeled row (\d+)\]", requested_text.strip(), flags=re.IGNORECASE)
    if placeholder_match:
        requested_placeholder_text = placeholder_match.group(1)

    resolution: dict[str, Any] = {
        "requested_text": probe_row_text,
        "requested_index": probe_row_index,
        "matched_by": None,
        "resolved_row_text": None,
        "resolved_row_index": None,
        "resolved_rectangle": None,
        "available_row_texts": available_row_texts,
        "available_row_indices": available_row_indices,
        "placeholder_count": placeholder_count,
    }

    if requested_text:
        for row in menu_rows:
            if row.text == requested_text:
                resolution.update(
                    matched_by="text",
                    resolved_row_text=row.text,
                    resolved_row_index=row.row_index,
                    resolved_rectangle=dict(row.rectangle),
                )
                return row, resolution

        for row in menu_rows:
            if normalized_text and row.normalized_text == normalized_text:
                resolution.update(
                    matched_by="normalized_text",
                    resolved_row_text=row.text,
                    resolved_row_index=row.row_index,
                    resolved_rectangle=dict(row.rectangle),
                )
                return row, resolution

    if requested_text:
        logger.info(
            "PROBE_ROW_TEXT_NOT_FOUND requested_text={!r} available_row_texts={} available_row_indices={} placeholder_count={}",
            probe_row_text,
            available_row_texts,
            available_row_indices,
            placeholder_count,
        )

    if probe_row_index is not None:
        for row in menu_rows:
            if row.row_index != probe_row_index:
                continue
            resolution.update(
                matched_by="row_index",
                resolved_row_text=row.text,
                resolved_row_index=row.row_index,
                resolved_rectangle=dict(row.rectangle),
            )
            return row, resolution

    if requested_placeholder_text:
        placeholder_index = int(requested_placeholder_text)
        for row in menu_rows:
            if not _is_placeholder_row(row):
                continue
            if row.row_index != placeholder_index:
                continue
            resolution.update(
                matched_by="placeholder_index",
                resolved_row_text=row.text,
                resolved_row_index=row.row_index,
                resolved_rectangle=dict(row.rectangle),
            )
            return row, resolution

    return None, resolution


def _window_identity(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("handle"),
        row.get("title") or "",
        row.get("class_name") or "",
        row.get("process_id"),
    )


def _list_process_visible_windows(process_id: int | None) -> list[dict[str, Any]]:
    if process_id is None:
        return []
    return [w for w in _list_visible_top_windows() if w.get("process_id") == process_id]


def _describe_controls(window: Any, limit: int = 20) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    try:
        descendants = _safe_call(window, "descendants", []) or []
    except Exception:
        return controls
    for child in descendants[:limit]:
        controls.append({
            "control_type": getattr(getattr(child, "element_info", None), "control_type", None),
            "name": _safe_call(child, "window_text", "") or "",
            "automation_id": getattr(getattr(child, "element_info", None), "automation_id", None),
        })
    return controls


def _window_snapshot(window: Any) -> dict[str, Any]:
    rect = _safe_call(window, "rectangle", None)
    rectangle = {}
    if rect is not None:
        rectangle = {
            "left": int(getattr(rect, "left", 0)),
            "top": int(getattr(rect, "top", 0)),
            "right": int(getattr(rect, "right", 0)),
            "bottom": int(getattr(rect, "bottom", 0)),
        }
    return {
        "title": _safe_call(window, "window_text", "") or "",
        "class_name": _safe_call(window, "class_name", "") or "",
        "process_id": _safe_call(window, "process_id", None),
        "handle": _safe_call(window, "handle", None),
        "rectangle": rectangle,
        "enabled": bool(_safe_call(window, "is_enabled", False)),
        "visible": bool(_safe_call(window, "is_visible", False)),
        "controls": _describe_controls(window),
    }


def _resolve_window_wrapper(candidate: dict[str, Any]) -> Any | None:
    handle = candidate.get("handle")
    if handle is None:
        return None
    try:
        from pywinauto import Desktop

        return Desktop(backend="uia").window(handle=handle)
    except Exception:
        return None


def _explore_dialog_candidate(candidate: dict[str, Any], *, safe_mode: str) -> dict[str, Any]:
    dialog = _resolve_window_wrapper(candidate)
    if dialog is None:
        return {"controls": [], "interactions": [], "states": [], "exploration_depth": 0}
    try:
        return explore_dialog(dialog, safe_mode=safe_mode == "safe")
    except Exception as exc:
        logger.warning("dialog_explorer_failed title={} error={}", candidate.get("title"), exc)
        return {"controls": [], "interactions": [], "states": [], "exploration_depth": 0}


def detect_dialog_or_window_transition(
    before_snapshot: RuntimeStateSnapshot,
    after_snapshot: RuntimeStateSnapshot,
    *,
    child_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    child_rows = child_rows or []
    before_ids = {_window_identity(w) for w in before_snapshot.visible_top_windows}
    new_windows = [w for w in after_snapshot.visible_top_windows if _window_identity(w) not in before_ids]
    main_disabled = before_snapshot.main_window_enabled is not False and after_snapshot.main_window_enabled is False

    if child_rows:
        return {"result_type": "child_popup_opened", "new_windows": new_windows}

    if new_windows:
        transient_new_windows = [window for window in new_windows if _is_transient_window_snapshot(window)]
        functional_new_windows = [window for window in new_windows if not _is_transient_window_snapshot(window)]
        if functional_new_windows:
            candidate = functional_new_windows[0]
            title = str(candidate.get("title") or "")
            class_name = str(candidate.get("class_name") or "")
            result_type = "dialog_opened" if class_name == "#32770" or "dialog" in class_name.lower() else "window_opened"
            logger.info("dialog_detected result_type={} title={} class_name={} transient_new_window_count={}", result_type, title, class_name, len(transient_new_windows))
            return {"result_type": result_type, "dialog_detected": result_type == "dialog_opened", "window_snapshot": candidate, "transient_windows": transient_new_windows}
        candidate = transient_new_windows[0]
        logger.info("transient_window_detected result_type=transient_hint_opened title={} class_name={}", candidate.get("title") or "", candidate.get("class_name") or "")
        return {"result_type": "transient_hint_opened", "dialog_detected": False, "transient_window_detected": True, "window_snapshot": candidate, "transient_windows": transient_new_windows}

    if main_disabled:
        logger.warning("modal_likely_main_disabled title={}", after_snapshot.main_window_title)
        return {"result_type": "main_window_disabled_modal_likely", "dialog_detected": True}

    if after_snapshot.foreground_window != before_snapshot.foreground_window:
        return {"result_type": "focus_changed_without_dialog", "dialog_detected": False}

    return {"result_type": "no_observable_effect", "dialog_detected": False}


def _is_modal_window_snapshot(window_snapshot: dict[str, Any] | None) -> bool:
    window_snapshot = window_snapshot or {}
    class_name = str(window_snapshot.get("class_name") or "")
    return class_name == "#32770" or "dialog" in class_name.lower()


def _is_transient_window_snapshot(window_snapshot: dict[str, Any] | None) -> bool:
    window_snapshot = window_snapshot or {}
    class_name = str(window_snapshot.get("class_name") or "").strip().lower()
    title = str(window_snapshot.get("title") or "").strip().lower()
    if class_name in TRANSIENT_WINDOW_CLASS_NAMES:
        return True
    if any(marker in class_name for marker in TRANSIENT_WINDOW_CLASS_SUBSTRINGS):
        return True
    if class_name.endswith("tooltips_class32"):
        return True
    return not title and "hint" in class_name


def _classify_placeholder_action_outcome(
    *,
    state_id: str,
    path: list[str],
    row: RuntimeMenuRow,
    before_action: RuntimeStateSnapshot,
    after_action: RuntimeStateSnapshot,
    current_rows: list[dict[str, Any]],
    child_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    popup_visible_count, topbar_visible_count = menu_helpers._popup_visibility_counts(current_rows)
    foreground = after_action.foreground_window or {}
    modal_detected = _is_modal_window_snapshot(foreground)
    if child_rows:
        outcome = "child_popup_opened"
    elif modal_detected:
        outcome = "modal_opened"
    elif after_action.main_window_enabled is False:
        outcome = "modal_opened"
    elif popup_visible_count == 0:
        outcome = "popup_closed_without_dialog"
        if _window_title(before_action) != _window_title(after_action) or _window_class(before_action) != _window_class(after_action):
            outcome = "popup_closed_with_foreground_change"
    else:
        outcome = "no_observable_effect"
    details = {
        "outcome": outcome,
        "state_id": state_id,
        "path": path,
        "row_index": row.row_index,
        "placeholder": _is_placeholder_row(row),
        "popup_visible_count": popup_visible_count,
        "topbar_visible_count": topbar_visible_count,
        "child_row_count": len(child_rows),
        "main_window_enabled_before": before_action.main_window_enabled,
        "main_window_enabled_after": after_action.main_window_enabled,
        "foreground_window": foreground,
        "foreground_class_name": str(foreground.get("class_name") or ""),
        "foreground_title": str(foreground.get("title") or ""),
        "policy": placeholder_modal_policy(),
    }
    logger.info(
        "PLACEHOLDER_ACTION_OUTCOME state={} path={} outcome={} row_index={} popup_visible_count={} topbar_visible_count={} child_row_count={} main_window_enabled_before={} main_window_enabled_after={} foreground_class_name={} foreground_title={!r} policy={}",
        state_id,
        path,
        outcome,
        row.row_index,
        popup_visible_count,
        topbar_visible_count,
        len(child_rows),
        before_action.main_window_enabled,
        after_action.main_window_enabled,
        details["foreground_class_name"],
        details["foreground_title"],
        details["policy"],
    )
    return details


def _classify_probe_result_type(*, before_action: RuntimeStateSnapshot, after_action: RuntimeStateSnapshot, before_rows: list[dict[str, Any]], after_rows: list[dict[str, Any]], child_rows: list[dict[str, Any]], click_exception: str | None) -> str:
    if click_exception:
        return "click_failed_focus_guard" if "focus" in click_exception.lower() else "no_observable_effect"
    foreground_changed = _window_title(before_action) != _window_title(after_action) or _window_class(before_action) != _window_class(after_action)
    popup_closed = bool(before_rows) and not after_rows
    if child_rows:
        return "child_popup_opened"
    if _is_modal_window_snapshot(after_action.foreground_window) or after_action.main_window_enabled is False:
        return "dialog_opened"
    if popup_closed and foreground_changed:
        return "popup_closed_with_foreground_change"
    if popup_closed:
        return "popup_closed_without_dialog"
    if foreground_changed:
        return "focus_changed_without_dialog"
    return "no_observable_effect"


def _evidence_strength_for_probe(evidence: dict[str, Any], result_type: str) -> str:
    if result_type in ACTION_PROBE_STRONG_RESULT_TYPES or evidence.get("new_dialog_detected"):
        return "strong"
    if evidence.get("popup_closed") or evidence.get("menu_selection_highlight_changed") or evidence.get("foreground_title_before") != evidence.get("foreground_title_after"):
        return "medium"
    if evidence.get("click_exception"):
        return "weak"
    return "none"


def _should_run_action_evidence_probe(*, row: RuntimeMenuRow, rejection_reason: str | None) -> bool:
    geometry_placeholder = _is_placeholder_row(row)
    return bool(
        rejection_reason in ACTION_PROBE_REJECTION_REASONS
        and (not geometry_placeholder or geometry_placeholder)
        and (row.is_separator is False)
    )


def _run_action_evidence_probe(*, state_id: str, top_menu: str, path: list[str], row: RuntimeMenuRow, popup_rows: list[dict[str, Any]], current_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    before_rows = list(current_rows if current_rows is not None else menu_helpers.capture_menu_popup_snapshot())
    before_action = capture_state_snapshot(state_id)
    placeholder_geometry_signature = _placeholder_geometry_signature(row) if _is_placeholder_row(row) else None
    evidence: dict[str, Any] = {
        "popup_row_count_before": len(before_rows),
        "visible_item_count_before": sum(1 for item in before_rows if not item.get("is_separator")),
        "foreground_title_before": _window_title(before_action),
        "foreground_class_before": _window_class(before_action),
        "main_window_enabled_before": before_action.main_window_enabled,
        "popup_row_count_after": len(before_rows),
        "visible_item_count_after": sum(1 for item in before_rows if not item.get("is_separator")),
        "foreground_title_after": _window_title(before_action),
        "foreground_class_after": _window_class(before_action),
        "main_window_enabled_after": before_action.main_window_enabled,
        "new_dialog_detected": False,
        "popup_closed": False,
        "child_popup_opened": False,
        "menu_selection_highlight_changed": False,
        "click_exception": None,
        "evidence_strength": "none",
        "placeholder_geometry_signature": placeholder_geometry_signature,
        "placeholder_geometry_stable": False,
        "textual_child_rows_detected": False,
    }
    logger.info("ACTION_EVIDENCE_PROBE_START state={} top_menu={} path={} row_index={} rejection_reason={}", state_id, top_menu, path, row.row_index, row.rejection_reason)
    try:
        _activate_row_for_exploration(row, popup_rows)
    except Exception as exc:
        evidence["click_exception"] = f"{exc.__class__.__name__}: {exc}"
    after_rows = list(menu_helpers.capture_menu_popup_snapshot())
    after_action = capture_state_snapshot(state_id)
    child_rows = _detect_child_rows(asdict(row), after_rows)
    popup_closed = bool(before_rows) and not after_rows
    foreground_changed = _window_title(before_action) != _window_title(after_action) or _window_class(before_action) != _window_class(after_action)
    result_type = _classify_probe_result_type(
        before_action=before_action,
        after_action=after_action,
        before_rows=before_rows,
        after_rows=after_rows,
        child_rows=child_rows,
        click_exception=evidence["click_exception"],
    )
    after_placeholder_signatures = {
        _placeholder_geometry_signature(candidate)
        for candidate in after_rows
        if _placeholder_geometry_signature(candidate) is not None
    }
    evidence.update(
        {
            "popup_row_count_after": len(after_rows),
            "visible_item_count_after": sum(1 for item in after_rows if not item.get("is_separator")),
            "foreground_title_after": _window_title(after_action),
            "foreground_class_after": _window_class(after_action),
            "main_window_enabled_after": after_action.main_window_enabled,
            "new_dialog_detected": result_type == "dialog_opened",
            "popup_closed": popup_closed,
            "child_popup_opened": bool(child_rows),
            "menu_selection_highlight_changed": bool(not child_rows and not popup_closed and menu_helpers._snapshot_keys(before_rows) != menu_helpers._snapshot_keys(after_rows)),
            "placeholder_geometry_stable": bool(
                placeholder_geometry_signature is not None
                and placeholder_geometry_signature in after_placeholder_signatures
            ),
            "textual_child_rows_detected": _placeholder_textual_child_rows(child_rows),
        }
    )
    evidence["popup_closed_without_dialog"] = result_type == "popup_closed_without_dialog"
    evidence["popup_closed_with_foreground_change"] = result_type == "popup_closed_with_foreground_change"
    evidence["focus_changed_without_dialog"] = result_type == "focus_changed_without_dialog"
    evidence["evidence_strength"] = _evidence_strength_for_probe(evidence, result_type)
    evidence["result_type"] = result_type
    if result_type != "no_observable_effect":
        logger.info("ACTION_OUTCOME_RECLASSIFIED state={} top_menu={} path={} from=no_visible_change to={}", state_id, top_menu, path, result_type)
    logger.info("ACTION_EVIDENCE_PROBE_RESULT state={} top_menu={} path={} row_index={} result_type={} evidence={}", state_id, top_menu, path, row.row_index, result_type, evidence)
    return evidence


def _handle_placeholder_modal_outcome(
    *,
    state_id: str,
    top_menu: str,
    safe_mode: str,
    path: list[str],
    row: RuntimeMenuRow,
    transition: dict[str, Any],
) -> tuple[dict[str, Any], RuntimeDialogRecord]:
    candidate = dict(transition.get("window_snapshot") or transition.get("foreground_window") or {})
    logger.warning(
        "MODAL_DETECTED_AFTER_PLACEHOLDER state={} top_menu={} path={} row_index={} title={!r} class_name={} policy={}",
        state_id,
        top_menu,
        path,
        row.row_index,
        str(candidate.get("title") or ""),
        str(candidate.get("class_name") or ""),
        placeholder_modal_policy(),
    )
    exploration = {"controls": [], "interactions": [], "states": [], "exploration_depth": 0}
    if placeholder_modal_policy() == "allow_modal_probe":
        exploration = _explore_dialog_candidate(candidate, safe_mode=safe_mode)
    logger.info(
        "PLACEHOLDER_MARKED_AS_MODAL_ACTION state={} top_menu={} path={} row_index={} opens_modal=True policy={}",
        state_id,
        top_menu,
        path,
        row.row_index,
        placeholder_modal_policy(),
    )
    logger.info(
        "MODAL_CLOSE_ATTEMPT state={} top_menu={} path={} row_index={} title={!r} class_name={} policy={}",
        state_id,
        top_menu,
        path,
        row.row_index,
        str(candidate.get("title") or ""),
        str(candidate.get("class_name") or ""),
        placeholder_modal_policy(),
    )
    close_result = close_transient_dialog_or_window(_resolve_window_wrapper(candidate), action_label=" > ".join(path))
    verification = _verify_modal_close_outcome(
        state_id=state_id,
        top_menu=top_menu,
        path=path,
        row_index=row.row_index,
    )
    close_result["verification"] = verification
    logger.info(
        "MODAL_CLOSE_RESULT state={} top_menu={} path={} row_index={} closed={} method={} error={} verification={} policy={}",
        state_id,
        top_menu,
        path,
        row.row_index,
        close_result.get("closed"),
        close_result.get("method"),
        close_result.get("error"),
        verification,
        placeholder_modal_policy(),
    )
    if not verification.get("ok"):
        logger.error(
            "MODAL_CLOSE_HARD_FAIL state={} top_menu={} path={} row_index={} foreground_class={} main_window_enabled={} root_menu_reopenable={}",
            state_id,
            top_menu,
            path,
            row.row_index,
            verification.get("foreground_class_name"),
            verification.get("main_window_enabled"),
            verification.get("root_menu_reopenable"),
        )
    restore_clean_menu_baseline(state_id=state_id, stage=f"placeholder_modal:{' > '.join(path)}")
    return close_result, RuntimeDialogRecord(
        state_id=state_id,
        top_menu=top_menu,
        row_index=row.row_index,
        menu_path=path,
        title=str(candidate.get("title") or ""),
        class_name=str(candidate.get("class_name") or ""),
        process_id=candidate.get("process_id"),
        rectangle=dict(candidate.get("rectangle") or {}),
        enabled=candidate.get("enabled"),
        visible=candidate.get("visible"),
        controls=list(candidate.get("controls") or []),
        explored_controls=list(exploration.get("controls") or []),
        interactions_attempted=list(exploration.get("interactions") or []),
        resulting_states=list(exploration.get("states") or []),
        exploration_depth=int(exploration.get("exploration_depth") or 0),
    )


def close_transient_dialog_or_window(window: Any | None, *, action_label: str = "") -> dict[str, Any]:
    logger.info("dialog_close_attempt action_label={}", action_label)
    if window is None:
        try:
            from pywinauto import keyboard
            keyboard.send_keys('{ESC}')
            logger.info('dialog_close_success method=esc_global')
            return {'closed': True, 'method': 'esc_global'}
        except Exception:
            return {"closed": False, "method": None, "error": "missing_window"}
    try:
        from pywinauto import keyboard
    except Exception:
        keyboard = None

    if keyboard is not None:
        for key, method in [('{ESC}', 'esc'), ('%{F4}', 'alt_f4')]:
            try:
                window.set_focus()
                keyboard.send_keys(key)
                if not bool(_safe_call(window, 'is_visible', False)):
                    logger.info('dialog_close_success method={}', method)
                    return {'closed': True, 'method': method}
            except Exception:
                continue

    labels = ["Mégse", "Cancel", "Bezár", "Bezárás", "Close", "OK"]
    for label in labels:
        for meth in ("child_window", "window"):
            try:
                btn = getattr(window, meth)(title_re=f".*{label}.*", control_type="Button")
                btn.click_input()
                if not bool(_safe_call(window, 'is_visible', False)):
                    logger.info('dialog_close_success method=button:{}', label)
                    return {'closed': True, 'method': f'button:{label}'}
            except Exception:
                continue

    try:
        window.close()
        if not bool(_safe_call(window, 'is_visible', False)):
            logger.info('dialog_close_success method=close')
            return {'closed': True, 'method': 'close'}
    except Exception:
        pass

    logger.error("dialog_close_failed action_label={}", action_label)
    return {"closed": False, "method": None, "error": "close_failed"}


def verify_main_window_recovery(main_window: Any) -> bool:
    visible = bool(_safe_call(main_window, "is_visible", False))
    enabled = bool(_safe_call(main_window, "is_enabled", False))
    ok = visible and enabled
    if ok:
        logger.info("recovery_success")
    else:
        logger.error("recovery_failed visible={} enabled={}", visible, enabled)
    return ok


def _main_window_recovery_state(main_window: Any) -> dict[str, Any]:
    rect = _safe_call(main_window, "rectangle", None)
    rectangle = {}
    if rect is not None:
        rectangle = {
            "left": int(getattr(rect, "left", 0)),
            "top": int(getattr(rect, "top", 0)),
            "right": int(getattr(rect, "right", 0)),
            "bottom": int(getattr(rect, "bottom", 0)),
        }
    return {
        "exists": main_window is not None,
        "title": _safe_call(main_window, "window_text", "") or "",
        "class_name": _safe_call(main_window, "class_name", "") or "",
        "process_id": _safe_call(main_window, "process_id", None),
        "handle": _safe_call(main_window, "handle", None),
        "visible": bool(_safe_call(main_window, "is_visible", False)),
        "enabled": bool(_safe_call(main_window, "is_enabled", False)),
        "rect": rectangle,
    }


def _list_recovery_target_windows(*, main_window_handle: Any | None = None, main_process_id: int | None = None) -> list[Any]:
    try:
        from pywinauto import Desktop
    except Exception:
        return []

    targets: list[tuple[int, Any]] = []
    for window in Desktop(backend="uia").windows(top_level_only=True):
        if not bool(_safe_call(window, "is_visible", False)):
            continue
        handle = _safe_call(window, "handle", None)
        if main_window_handle is not None and handle == main_window_handle:
            continue
        score = 0
        if main_process_id is not None and _safe_call(window, "process_id", None) == main_process_id:
            score += 10
        title = (_safe_call(window, "window_text", "") or "").strip()
        if title:
            score += 1
        targets.append((score, window))

    targets.sort(key=lambda item: item[0], reverse=True)
    return [window for _, window in targets]


def _send_recovery_key(
    key_sequence: str,
    *,
    main_window_handle: Any | None = None,
    main_process_id: int | None = None,
) -> bool:
    try:
        from pywinauto import keyboard
    except Exception:
        return False

    targets = _list_recovery_target_windows(main_window_handle=main_window_handle, main_process_id=main_process_id)
    if not targets:
        try:
            keyboard.send_keys(key_sequence)
            return True
        except Exception:
            return False

    for target in targets:
        try:
            target.set_focus()
            keyboard.send_keys(key_sequence)
            return True
        except Exception:
            continue
    return False


def _click_recovery_button(label: str, *, main_window_handle: Any | None = None) -> bool:
    try:
        from pywinauto import Desktop
    except Exception:
        return False

    for window in Desktop(backend="uia").windows(top_level_only=True):
        if not bool(_safe_call(window, "is_visible", False)):
            continue
        if main_window_handle is not None and _safe_call(window, "handle", None) == main_window_handle:
            continue
        for method_name in ("child_window", "window"):
            try:
                button = getattr(window, method_name)(title_re=fr".*{label}.*", control_type="Button")
                button.click_input()
                return True
            except Exception:
                continue
    return False


def _collect_project_open_recovery_diagnostics(main_window: Any) -> dict[str, Any]:
    main_state = _main_window_recovery_state(main_window)
    dialog_candidates = [
        window
        for window in _list_visible_top_windows()
        if window.get("handle") != main_state.get("handle")
    ]
    return {
        "foreground_window": _foreground_window_info(),
        "dialog_candidates": dialog_candidates,
        "main_window": {
            "enabled": main_state.get("enabled"),
            "visible": main_state.get("visible"),
            "rect": main_state.get("rect"),
            "title": main_state.get("title"),
            "class_name": main_state.get("class_name"),
            "process_id": main_state.get("process_id"),
            "handle": main_state.get("handle"),
            "exists": main_state.get("exists"),
        },
    }


def _is_main_window_interactive(main_window: Any) -> bool:
    state = _main_window_recovery_state(main_window)
    return bool(state["exists"] and state["visible"] and state["enabled"])


def _attempt_project_open_modal_close(
    *,
    main_window_handle: Any | None = None,
    main_process_id: int | None = None,
) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for key_sequence, name in (("{ESC}", "Esc"), ("{ENTER}", "Enter"), ("%{F4}", "Alt+F4")):
        attempt = {"method": "key", "name": name, "key_sequence": key_sequence}
        logger.info("project_open_recovery_close_attempt method={} name={}", attempt["method"], attempt["name"])
        attempt["sent"] = _send_recovery_key(
            key_sequence,
            main_window_handle=main_window_handle,
            main_process_id=main_process_id,
        )
        attempts.append(attempt)
        if _is_main_window_interactive(get_cached_main_window()):
            logger.info("project_open_recovery_close_success method={} name={}", attempt["method"], attempt["name"])
            return attempts

    for label in ["OK", "Rendben", "Bezár", "Mégse", "Cancel", "Close", "No", "Nem"]:
        attempt = {"method": "button", "name": label}
        logger.info("project_open_recovery_close_attempt method={} name={}", attempt["method"], attempt["name"])
        attempt["clicked"] = _click_recovery_button(label, main_window_handle=main_window_handle)
        attempts.append(attempt)
        if _is_main_window_interactive(get_cached_main_window()):
            logger.info("project_open_recovery_close_success method={} name={}", attempt["method"], attempt["name"])
            return attempts
    return attempts


def _verify_modal_close_outcome(
    *,
    state_id: str,
    top_menu: str,
    path: list[str],
    row_index: int,
) -> dict[str, Any]:
    snapshot = capture_state_snapshot(state_id)
    foreground = snapshot.foreground_window or {}
    foreground_is_modal = _is_modal_window_snapshot(foreground)
    main_enabled = bool(snapshot.main_window_enabled)
    root_menu_rows: list[dict[str, Any]] = []
    root_menu_reopenable = False
    if main_enabled and not foreground_is_modal:
        try:
            root_menu_rows, _ = _open_and_capture_root_menu(state_id=state_id, top_menu=top_menu)
            root_menu_reopenable = bool(root_menu_rows)
        except Exception as exc:
            logger.warning(
                "MODAL_CLOSE_VERIFY_REOPEN_FAILED state={} top_menu={} path={} row_index={} error={}",
                state_id,
                top_menu,
                path,
                row_index,
                exc,
            )
    verification = {
        "ok": bool((not foreground_is_modal) and main_enabled and root_menu_reopenable),
        "foreground_class_name": str(foreground.get("class_name") or ""),
        "foreground_title": str(foreground.get("title") or ""),
        "main_window_enabled": main_enabled,
        "root_menu_reopenable": root_menu_reopenable,
        "root_menu_row_count": len(root_menu_rows),
    }
    logger.info(
        "MODAL_CLOSE_VERIFICATION state={} top_menu={} path={} row_index={} foreground_is_modal={} main_window_enabled={} root_menu_reopenable={} root_menu_row_count={}",
        state_id,
        top_menu,
        path,
        row_index,
        foreground_is_modal,
        main_enabled,
        root_menu_reopenable,
        len(root_menu_rows),
    )
    return verification


def recover_after_project_open(*, timeout_s: float = 15.0, poll_interval_s: float = 0.25) -> dict[str, Any]:
    logger.info("project_open_recovery_start timeout_s={} poll_interval_s={}", timeout_s, poll_interval_s)
    deadline = time.monotonic() + timeout_s
    diagnostics: dict[str, Any] = {}
    close_attempts: list[dict[str, Any]] = []
    modal_logged = False
    modal_pending = False

    while time.monotonic() <= deadline:
        main_window = get_cached_main_window()
        main_state = _main_window_recovery_state(main_window)
        if main_state["exists"] and main_state["visible"] and main_state["enabled"]:
            logger.info("project_open_recovery_success")
            diagnostics = _collect_project_open_recovery_diagnostics(main_window)
            return {
                "success": True,
                "diagnostics": diagnostics,
                "close_attempts": close_attempts,
                "modal_pending": modal_pending,
                "close_attempted": bool(close_attempts),
                "main_window_reenabled": True,
                "reason": "main_window_ready",
            }

        if main_state["visible"] and not main_state["enabled"]:
            modal_pending = True
            diagnostics = _collect_project_open_recovery_diagnostics(main_window)
            if not modal_logged:
                logger.warning("project_open_recovery_modal_detected diagnostics={}", diagnostics)
                modal_logged = True
            close_attempts.extend(
                _attempt_project_open_modal_close(
                    main_window_handle=main_state.get("handle"),
                    main_process_id=main_state.get("process_id"),
                )
            )

        time.sleep(poll_interval_s)

    diagnostics = _collect_project_open_recovery_diagnostics(get_cached_main_window())
    logger.error("project_open_recovery_failed diagnostics={}", diagnostics)
    return {
        "success": False,
        "diagnostics": diagnostics,
        "close_attempts": close_attempts,
        "modal_pending": modal_pending,
        "close_attempted": bool(close_attempts),
        "main_window_reenabled": False,
        "reason": "timeout",
    }


def classify_post_click_result(
    process_id: int | None,
    before_snapshot: RuntimeStateSnapshot,
    after_snapshot: RuntimeStateSnapshot,
    dialog_detection: dict[str, Any] | None,
    *,
    state_id: str,
    top_menu: str,
    row_index: int,
    menu_path: list[str],
    action_key: str,
    safety_level: str,
    attempted: bool,
    error_text: str | None = None,
    notes: str | None = None,
    top_menu_click_count: int | None = None,
    forced_result_type: str | None = None,
    action_state_classification: str | None = None,
) -> RuntimeActionResult:
    details = dict(dialog_detection or {})
    if action_state_classification:
        details["action_state_classification"] = action_state_classification
    if forced_result_type:
        result_type = forced_result_type
    elif not attempted:
        result_type = "failed"
    elif error_text:
        result_type = "failed"
    else:
        result_type = str(details.get("result_type") or ("dialog_opened" if details.get("dialog_detected") else "no_observable_effect"))

    return RuntimeActionResult(
        state_id=state_id,
        top_menu=top_menu,
        row_index=row_index,
        menu_path=menu_path,
        action_key=action_key,
        safety_level=safety_level,
        attempted=attempted,
        result_type=result_type,
        dialog_title=details.get("dialog_title") or ((details.get("window_snapshot") or {}).get("title")),
        dialog_class=details.get("dialog_class") or ((details.get("window_snapshot") or {}).get("class_name")),
        window_title=(details.get("window_snapshot") or {}).get("title"),
        window_class=(details.get("window_snapshot") or {}).get("class_name"),
        error_text=error_text,
        notes=notes,
        process_id=process_id,
        top_menu_click_count=top_menu_click_count,
        event_details=details,
    )


def explore_menu_tree(
    *,
    state_id: str,
    top_menu: str,
    safe_mode: str,
    max_depth: int | None,
    include_disabled: bool,
    depth: int = 1,
    parent_path: list[str] | None = None,
    popup_rows: list[dict[str, Any]] | None = None,
    canonical_top_menu_names: set[str] | None = None,
    visited_paths: set[tuple[str, ...]] | None = None,
    visited_path_hashes: set[int] | None = None,
    known_paths_to_skip: set[tuple[str, ...]] | None = None,
    popup_state: PopupState | None = None,
) -> tuple[list[dict[str, Any]], list[RuntimeMenuRow], list[RuntimeActionResult], list[RuntimeDialogRecord], list[RuntimeWindowRecord], list[dict[str, Any]]]:
    parent_path = list(parent_path or [clean_menu_title(top_menu)])
    dialogs: list[RuntimeDialogRecord] = []
    windows: list[RuntimeWindowRecord] = []
    top_transition: dict[str, Any] = {"result_type": "no_observable_effect"}

    if popup_rows is None:
        normalized_parent = tuple(normalize_menu_title(part) for part in parent_path)
        reusable_popup_rows: list[dict[str, Any]] = []
        if popup_state is not None and popup_state.popup_rows:
            reuse_allowed, reuse_rejection_reason = _popup_snapshot_belongs_to_current_parent(
                top_menu=top_menu,
                parent_path=parent_path,
                normalized_parent=normalized_parent,
                snapshot_rows=list(popup_state.popup_rows),
                popup_state=popup_state,
                canonical_top_menu_names=canonical_top_menu_names,
            )
            if reuse_allowed:
                reusable_popup_rows = list(popup_state.popup_rows)
                logger.info(
                    "POPUP_OWNERSHIP_CONFIRMED state={} top_menu={} normalized_parent={} popup_state_path={} row_count={}",
                    state_id,
                    top_menu,
                    normalized_parent,
                    getattr(popup_state, "current_menu_path", None),
                    len(reusable_popup_rows),
                )
            elif reuse_rejection_reason != "empty_snapshot":
                logger.info(
                    "POPUP_REUSE_REJECTED state={} top_menu={} normalized_parent={} popup_state_path={} reason={}",
                    state_id,
                    top_menu,
                    normalized_parent,
                    getattr(popup_state, "current_menu_path", None),
                    reuse_rejection_reason,
                )
        if not reusable_popup_rows:
            reusable_popup_rows = menu_helpers.capture_system_menu_popup() if _is_system_menu(top_menu) else menu_helpers.capture_menu_popup_snapshot()
        if reusable_popup_rows:
            if _is_primary_normal_top_menu(top_menu):
                classification, filtered_rows, popup_meta = _classify_popup_block(
                    top_menu=top_menu,
                    rows=reusable_popup_rows,
                    snapshot=capture_state_snapshot(state_id),
                    canonical_top_menu_names=canonical_top_menu_names,
                )
                valid_popup = popup_meta["popup_like_count"] > 0 and bool(filtered_rows)
                popup_like_count = popup_meta["popup_like_count"]
                topbar_like_count = popup_meta["topbar_like_count"]
                if valid_popup:
                    popup_rows = filtered_rows
                    logger.info("RECENT_PROJECT_BLOCK_SUMMARY state={} top_menu={} attempt=0 popup_block_classification={} recent_projects_block={} stateful_menu_block={} accepted_rows={} filtered_rows={}", state_id, top_menu, classification, classification == "recent_projects_block", classification == "recent_projects_block", popup_meta["accepted_row_count"], popup_meta["filtered_row_count"])
                    logger.info(
                        "DBG_REUSING_OPEN_POPUP_SNAPSHOT state={} top_menu={} row_count={} popup_like_count={} topbar_like_count={} normalized_parent={} popup_state_path={}",
                        state_id,
                        top_menu,
                        len(reusable_popup_rows),
                        popup_like_count,
                        topbar_like_count,
                        normalized_parent,
                        getattr(popup_state, "current_menu_path", None) if popup_state is not None else None,
                    )
                    logger.info(
                        "DBG_WINWATT_NORMAL_MENU_POPUP_ROWS_ACCEPTED state={} top_menu={} attempt=0 accepted_row_count={}",
                        state_id,
                        top_menu,
                        len(filtered_rows),
                    )
                    logger.debug("reusing_open_popup_snapshot state={} top_menu={} row_count={}", state_id, top_menu, len(reusable_popup_rows))
                else:
                    if classification in {"recent_projects_block", "ambiguous_empty_block"}:
                        logger.info("RECENT_PROJECT_BLOCK_REJECTED state={} top_menu={} attempt=0 popup_block_classification={} popup_like_count={} filtered_rows={} empty_popup_rows={}", state_id, top_menu, classification, popup_like_count, popup_meta["filtered_row_count"], popup_meta["empty_popup_row_count"])
                    logger.info(
                        "DBG_WINWATT_NORMAL_MENU_OPEN_NO_POPUP state={} top_menu={} attempt=0 raw_row_count={} popup_like_count={} topbar_like_count={} filtered_row_count={}",
                        state_id,
                        top_menu,
                        len(reusable_popup_rows),
                        popup_like_count,
                        topbar_like_count,
                        len(filtered_rows),
                    )
                    popup_rows, top_transition = _open_and_capture_root_menu(
                        state_id=state_id,
                        top_menu=top_menu,
                        canonical_top_menu_names=canonical_top_menu_names,
                    )
            else:
                popup_rows = reusable_popup_rows
                popup_like_count = sum(1 for row in popup_rows if bool(row.get("popup_candidate")))
                topbar_like_count = sum(1 for row in popup_rows if bool(row.get("topbar_candidate")))
                logger.info(
                    "DBG_REUSING_OPEN_POPUP_SNAPSHOT state={} top_menu={} row_count={} popup_like_count={} topbar_like_count={} normalized_parent={} popup_state_path={}",
                    state_id,
                    top_menu,
                    len(popup_rows),
                    popup_like_count,
                    topbar_like_count,
                    normalized_parent,
                    getattr(popup_state, "current_menu_path", None) if popup_state is not None else None,
                )
                logger.debug("reusing_open_popup_snapshot state={} top_menu={} row_count={}", state_id, top_menu, len(popup_rows))
        else:
            popup_rows, top_transition = _open_and_capture_root_menu(
                state_id=state_id,
                top_menu=top_menu,
                canonical_top_menu_names=canonical_top_menu_names,
            )
        if top_transition.get("result_type") in {"dialog_opened", "window_opened", "main_window_disabled_modal_likely"}:
            candidate = top_transition.get("window_snapshot") or {}
            if top_transition.get("result_type") == "dialog_opened" or top_transition.get("result_type") == "main_window_disabled_modal_likely":
                exploration = _explore_dialog_candidate(candidate, safe_mode=safe_mode)
                dialogs.append(RuntimeDialogRecord(
                    state_id=state_id,
                    top_menu=top_menu,
                    row_index=-1,
                    menu_path=[clean_menu_title(top_menu)],
                    title=str(candidate.get("title") or ""),
                    class_name=str(candidate.get("class_name") or ""),
                    process_id=candidate.get("process_id"),
                    rectangle=dict(candidate.get("rectangle") or {}),
                    enabled=candidate.get("enabled"),
                    visible=candidate.get("visible"),
                    controls=list(candidate.get("controls") or []),
                    explored_controls=list(exploration.get("controls") or []),
                    interactions_attempted=list(exploration.get("interactions") or []),
                    resulting_states=list(exploration.get("states") or []),
                    exploration_depth=int(exploration.get("exploration_depth") or 0),
                ))
            else:
                windows.append(RuntimeWindowRecord(
                    state_id=state_id,
                    top_menu=top_menu,
                    row_index=-1,
                    menu_path=[clean_menu_title(top_menu)],
                    title=str(candidate.get("title") or ""),
                    class_name=str(candidate.get("class_name") or ""),
                    process_id=candidate.get("process_id"),
                    rectangle=dict(candidate.get("rectangle") or {}),
                    enabled=candidate.get("enabled"),
                    visible=candidate.get("visible"),
                    controls=list(candidate.get("controls") or []),
                ))
            close_result = close_transient_dialog_or_window(None, action_label=f"top_menu:{top_menu}")
            if not close_result.get("closed"):
                logger.error("dialog_close_failed top_menu={}", top_menu)
        if popup_state is not None:
            popup_state.current_menu_path = normalized_parent
            popup_state.popup_rows = list(popup_rows)

    if visited_paths is None:
        visited_paths = set()
    if visited_path_hashes is None:
        visited_path_hashes = set()
    known_paths_to_skip = set(known_paths_to_skip or set())

    current_level_rows = _build_menu_rows_from_popup_rows(
        state_id,
        top_menu,
        _filter_normal_popup_rows(popup_rows, canonical_top_menu_names=canonical_top_menu_names) if _is_primary_normal_top_menu(top_menu) else popup_rows,
        canonical_top_menu_names=canonical_top_menu_names,
    )
    logger.info(
        "ACTION_CATALOG_INPUT_SUMMARY state={} top_menu={} depth={} candidate_rows={} placeholders={} low_or_none_confidence={} legacy_text_only={} unknown_pending=0",
        state_id,
        top_menu,
        depth,
        len(current_level_rows),
        sum(1 for row in current_level_rows if _is_placeholder_row(row)),
        sum(1 for row in current_level_rows if _row_text_confidence(row) in {"none", "low"}),
        sum(1 for row in current_level_rows if _row_has_legacy_text_only(row)),
    )
    collected_rows: list[RuntimeMenuRow] = list(current_level_rows)
    nodes: list[dict[str, Any]] = []
    actions: list[RuntimeActionResult] = []
    action_catalog: list[dict[str, Any]] = []
    probed_rows = 0
    admitted_after_probe = 0

    traversal_started_at = time.monotonic()
    for row in current_level_rows:
        if not include_disabled and row.enabled_guess is False:
            continue
        path = parent_path + [row.text]
        normalized_path = tuple(normalize_menu_title(part) for part in path)
        visit_key = normalized_path
        if not row.normalized_text:
            visit_key = (*normalized_path, f"#idx:{row.row_index}")

        path_key = hash(visit_key)
        if path_key in visited_path_hashes:
            logger.debug("visited path skip state={} path={}", state_id, normalized_path)
            continue
        visited_path_hashes.add(path_key)
        visited_paths.add(visit_key)

        skipped = row.is_separator or (not is_action_allowed(path, mode=safe_mode))
        reused_from_previous_state = normalized_path in known_paths_to_skip
        opens_submenu = False
        opens_modal = False
        children_nodes: list[dict[str, Any]] = []
        before_action = capture_state_snapshot(state_id) if not is_fast_mode() else RuntimeStateSnapshot(
            state_id=state_id,
            process_id=None,
            main_window_title="",
            main_window_class="",
            visible_top_windows=[],
            discovered_top_menus=[],
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
        )
        transition: dict[str, Any] = {"result_type": "no_observable_effect"}
        action_state_classification = "unknown"
        project_open_transition_detected = False
        skip_reason: str | None = None

        if (max_depth is None or max_depth < 0 or depth < max_depth) and not row.is_separator and row.enabled_guess is not False and not reused_from_previous_state:
            placeholder = _is_placeholder_row(row)
            recent_candidate = _is_recent_projects_candidate(top_menu=top_menu, path=path, row=row)
            transition["recent_project_candidate"] = recent_candidate
            recent_policy = recent_projects_policy()
            if recent_candidate and recent_policy == "skip_recent_projects":
                transition = {"result_type": "skipped_recent_project", "attempted": False, "recent_project_candidate": True}
                action_state_classification = "recent_project_entry"
                skip_reason = "recent_project_blocked_by_policy"
            elif recent_candidate and recent_policy == "probe_recent_projects":
                transition = {"result_type": "probed_recent_project", "attempted": False, "recent_project_candidate": True}
                action_state_classification = "recent_project_entry"
                skip_reason = "recent_project_catalog_only"
            else:
                transition = transition
            if recent_candidate and recent_policy in {"skip_recent_projects", "probe_recent_projects"}:
                logger.info("RECENT_PROJECT_ACTION_DETECTED state={} path={} policy={}", state_id, path, recent_policy)
                logger.info("RECENT_PROJECT_ENTRY_CLASSIFIED state={} path={} classification={} skip_reason={}", state_id, path, action_state_classification, skip_reason)
            if recent_candidate and recent_policy in {"skip_recent_projects", "probe_recent_projects"}:
                node = _row_to_node(
                    state_id,
                    top_menu,
                    asdict(row),
                    level=depth,
                    index=row.row_index,
                    path=path,
                    children=[],
                    opens_submenu=False,
                    opens_dialog=False,
                    opens_modal=False,
                    skipped_by_safety=skipped,
                    reused_from_previous_state=reused_from_previous_state,
                )
                node.action_state_classification = action_state_classification
                nodes.append(asdict(node))
                actions.append(
                    classify_post_click_result(
                        process_id=None,
                        before_snapshot=before_action,
                        after_snapshot=before_action,
                        dialog_detection=transition,
                        state_id=state_id,
                        top_menu=top_menu,
                        row_index=row.row_index,
                        menu_path=path,
                        action_key=" > ".join(path),
                        safety_level=classify_safety([clean_menu_title(part) for part in path]),
                        attempted=False,
                        notes=recent_policy,
                        action_state_classification=action_state_classification,
                    )
                )
                admitted, admission_reason, rejection_reason = _evaluate_action_admission(
                    row=row,
                    path=path,
                    action_state_classification=action_state_classification,
                    transition=transition,
                    opens_submenu=False,
                    opens_modal=False,
                    skip_reason=skip_reason,
                    traversal_depth=depth,
                )
                _update_row_admission_flags(
                    row,
                    admitted=admitted,
                    admission_reason=admission_reason,
                    rejection_reason=rejection_reason,
                )
                row.action_type = _classify_transition_action_type(
                    transition={"result_type": "unknown"},
                    action_state_classification=action_state_classification,
                    opens_submenu=False,
                    opens_modal=False,
                )
                row.meta["action_discovery"] = {"classification": action_state_classification, "policy": _action_discovery_policy(row.action_type)}
                if admitted:
                    action_catalog.append(
                        _build_action_catalog_entry(
                            path=path,
                            action_type=row.action_type,
                            action_state_classification=action_state_classification,
                            opens_modal=False,
                            opens_submenu=False,
                            changes_menu_state=False,
                            opens_project_and_changes_runtime_state=False,
                            traversal_depth=depth,
                            skip_reason=skip_reason,
                        )
                    )
                continue
            focus_refresh_mode = bool(
                is_placeholder_traversal_focus_mode()
                and _is_primary_normal_top_menu(top_menu)
                and depth == 1
            )
            skip_parent_reopen = bool(
                placeholder
                and diagnostic_options().suppress_placeholder_top_menu_relist
                and popup_rows
                and not focus_refresh_mode
            )
            logger.info(
                "DBG_SUBTREE_TRAVERSAL_DECISION state={} path={} placeholder={} skipped_by_safety={} reused_from_previous_state={} action_type={} source_scope={} skip_parent_reopen={} diagnostic_fast_mode={} placeholder_focus_mode={}",
                state_id,
                path,
                placeholder,
                skipped,
                reused_from_previous_state,
                row.action_type,
                row.source_scope,
                skip_parent_reopen,
                is_diagnostic_fast_mode(),
                is_placeholder_traversal_focus_mode(),
            )
            if focus_refresh_mode:
                logger.info("SIBLING_REFRESH_REQUIRED state={} top_menu={} parent_path={} path={}", state_id, top_menu, parent_path, path)
                should_restore_clean_menu_baseline(
                    state_id=state_id,
                    stage=f"pre_sibling:{' > '.join(path)}",
                    popup_rows=popup_rows,
                )
            active_popup_rows = popup_rows
            if not skip_parent_reopen and not focus_refresh_mode:
                active_popup_rows = _reopen_parent_popup_rows(
                    state_id=state_id,
                    top_menu=top_menu,
                    parent_path=parent_path,
                    canonical_top_menu_names=canonical_top_menu_names,
                    popup_state=popup_state,
                )
            if focus_refresh_mode:
                popup_rows, row = _capture_fresh_root_popup_for_sibling(
                    state_id=state_id,
                    top_menu=top_menu,
                    parent_path=parent_path,
                    target_row=row,
                    canonical_top_menu_names=canonical_top_menu_names,
                    popup_state=popup_state,
                    stage=f"pre_sibling:{' > '.join(path)}",
                )
            elif active_popup_rows:
                popup_rows = active_popup_rows
                match = _find_matching_popup_row(active_popup_rows, row)
                if match is not None:
                    row_idx, matching_row = match
                    row = RuntimeMenuRow(
                        state_id=row.state_id,
                        top_menu=row.top_menu,
                        row_index=row_idx,
                        menu_path=row.menu_path,
                        text=row.text,
                        normalized_text=row.normalized_text,
                        rectangle=dict(matching_row.get("rectangle") or row.rectangle),
                        center_x=int(matching_row.get("center_x") or row.center_x),
                        center_y=int(matching_row.get("center_y") or row.center_y),
                        is_separator=row.is_separator,
                        source_scope=str(matching_row.get("source_scope") or row.source_scope),
                        fragments=list(matching_row.get("fragments") or row.fragments),
                        enabled_guess=_guess_enabled(matching_row),
                        discovered_in_state=row.discovered_in_state,
                        raw_text_sources=list(matching_row.get("raw_text_sources") or row.raw_text_sources),
                        text_confidence=str(matching_row.get("text_confidence") or row.text_confidence),
                        actionable=row.actionable,
                        dispatch_type=row.dispatch_type,
                        action_type=row.action_type,
                        recent_project_entry=row.recent_project_entry,
                        stateful_menu_block=row.stateful_menu_block,
                        meta=dict(row.meta),
                    )
            _activate_row_for_exploration(row, popup_rows)
            current_rows = menu_helpers.capture_menu_popup_snapshot()
            popup_visible_count, topbar_visible_count = menu_helpers._popup_visibility_counts(current_rows)
            logger.info(
                "DBG_POST_ACTION_POPUP_VISIBILITY state={} path={} popup_visible_count={} topbar_visible_count={} snapshot_rows={} placeholder={} ",
                state_id,
                path,
                popup_visible_count,
                topbar_visible_count,
                len(current_rows),
                placeholder,
            )
            if _is_primary_normal_top_menu(top_menu):
                current_rows = _filter_normal_popup_rows(current_rows, canonical_top_menu_names=canonical_top_menu_names)
            child_rows = _detect_child_rows(asdict(row), current_rows)
            if canonical_top_menu_names:
                child_rows = [
                    child_row
                    for child_row in child_rows
                    if not is_top_menu_like_popup_row(child_row, canonical_top_menu_names)
                ]
            after_action = capture_state_snapshot(state_id) if (recent_candidate or not is_fast_mode()) else before_action
            placeholder_outcome = None
            if placeholder:
                placeholder_outcome = _classify_placeholder_action_outcome(
                    state_id=state_id,
                    path=path,
                    row=row,
                    before_action=before_action,
                    after_action=after_action,
                    current_rows=current_rows,
                    child_rows=child_rows,
                )
            if child_rows or not is_fast_mode():
                transition = detect_dialog_or_window_transition(before_action, after_action, child_rows=child_rows)
            if placeholder_outcome and placeholder_outcome.get("outcome") in {"dialog_opened", "modal_opened"}:
                transition = {
                    "result_type": str(placeholder_outcome.get("outcome") or "dialog_opened"),
                    "dialog_detected": True,
                    "window_snapshot": dict(placeholder_outcome.get("foreground_window") or {}),
                    "foreground_window": dict(placeholder_outcome.get("foreground_window") or {}),
                    "placeholder_outcome": str(placeholder_outcome.get("outcome") or "dialog_opened"),
                }
            elif placeholder_outcome:
                transition = dict(transition)
                transition["placeholder_outcome"] = placeholder_outcome.get("outcome")
            if recent_candidate and (
                transition.get("result_type") in {"dialog_opened", "modal_opened"}
                or after_action.main_window_enabled is False
            ):
                transition["project_open_recovery"] = recover_after_project_open()
                if transition["project_open_recovery"].get("success"):
                    after_action = capture_state_snapshot(state_id)
            transition["attempted"] = True
            if child_rows:
                opens_submenu = True
                action_state_classification = "opens_submenu"
                logger.info("DBG_SUBTREE_TRAVERSAL_SUBMENU_OPENED state={} path={} child_row_count={} placeholder={}", state_id, path, len(child_rows), placeholder)
                if popup_state is not None:
                    popup_state.current_menu_path = tuple(normalize_menu_title(part) for part in path)
                    popup_state.popup_rows = list(child_rows)
                if _safe_depth_decision(
                    state_id=state_id,
                    path=path,
                    current_depth=depth,
                    max_depth=max_depth,
                    action_state_classification=action_state_classification,
                ):
                    child_nodes, child_menu_rows, child_actions, child_dialogs, child_windows, child_action_catalog = explore_menu_tree(
                        state_id=state_id,
                        top_menu=top_menu,
                        safe_mode=safe_mode,
                        max_depth=max_depth,
                        include_disabled=include_disabled,
                        depth=depth + 1,
                        parent_path=path,
                        popup_rows=child_rows,
                        canonical_top_menu_names=canonical_top_menu_names,
                        visited_paths=visited_paths,
                        visited_path_hashes=visited_path_hashes,
                        known_paths_to_skip=known_paths_to_skip,
                        popup_state=popup_state,
                    )
                    children_nodes = child_nodes
                    collected_rows.extend(child_menu_rows)
                    actions.extend(child_actions)
                    dialogs.extend(child_dialogs)
                    windows.extend(child_windows)
                    action_catalog.extend(child_action_catalog)
            elif transition.get("result_type") in {"dialog_opened", "modal_opened", "window_opened", "main_window_disabled_modal_likely"}:
                candidate = transition.get("window_snapshot") or {}
                if transition.get("result_type") in {"dialog_opened", "modal_opened", "main_window_disabled_modal_likely"}:
                    opens_modal = True
                    exploration = _explore_dialog_candidate(candidate, safe_mode=safe_mode)
                    dialogs.append(RuntimeDialogRecord(
                        state_id=state_id,
                        top_menu=top_menu,
                        row_index=row.row_index,
                        menu_path=path,
                        title=str(candidate.get("title") or ""),
                        class_name=str(candidate.get("class_name") or ""),
                        process_id=candidate.get("process_id"),
                        rectangle=dict(candidate.get("rectangle") or {}),
                        enabled=candidate.get("enabled"),
                        visible=candidate.get("visible"),
                        controls=list(candidate.get("controls") or []),
                        explored_controls=list(exploration.get("controls") or []),
                        interactions_attempted=list(exploration.get("interactions") or []),
                        resulting_states=list(exploration.get("states") or []),
                        exploration_depth=int(exploration.get("exploration_depth") or 0),
                    ))
                else:
                    windows.append(RuntimeWindowRecord(
                        state_id=state_id,
                        top_menu=top_menu,
                        row_index=row.row_index,
                        menu_path=path,
                        title=str(candidate.get("title") or ""),
                        class_name=str(candidate.get("class_name") or ""),
                        process_id=candidate.get("process_id"),
                        rectangle=dict(candidate.get("rectangle") or {}),
                        enabled=candidate.get("enabled"),
                        visible=candidate.get("visible"),
                        controls=list(candidate.get("controls") or []),
                    ))
                _safe_depth_decision(
                    state_id=state_id,
                    path=path,
                    current_depth=depth,
                    max_depth=max_depth,
                    action_state_classification="opens_modal" if opens_modal else "changes_menu_state",
                )
            project_open_transition_detected = _detect_project_open_transition(
                state_id=state_id,
                top_menu=top_menu,
                path=path,
                row=row,
                before_action=before_action,
                after_action=after_action,
                transition=transition,
                popup_state=popup_state,
            )
            action_state_classification = _action_state_classification(
                transition=transition,
                opens_submenu=opens_submenu,
                opens_modal=opens_modal,
            )
            row.action_type = _classify_transition_action_type(
                transition=transition,
                action_state_classification=action_state_classification,
                opens_submenu=opens_submenu,
                opens_modal=opens_modal,
            )
            row.meta["action_discovery"] = {
                "classification": str(transition.get("result_type") or action_state_classification or "unknown"),
                "policy": _action_discovery_policy(row.action_type),
            }
            if recent_candidate:
                logger.info("RECENT_PROJECT_ENTRY_CLASSIFIED state={} path={} classification={} skip_reason={}", state_id, path, action_state_classification, skip_reason)
            if focus_refresh_mode and not project_open_transition_detected:
                restore_clean_menu_baseline(state_id=state_id, stage=f"post_action:{' > '.join(path)}")
                logger.info("ACTION_BASELINE_RESTORED state={} top_menu={} path={}", state_id, top_menu, path)
                if opens_modal or transition.get("result_type") in {"dialog_opened", "modal_opened", "window_opened", "main_window_disabled_modal_likely"}:
                    action_snapshot = capture_state_snapshot(state_id)
                    if action_snapshot.main_window_enabled is False:
                        logger.error("ACTION_LEFT_MAIN_WINDOW_DISABLED state={} top_menu={} path={}", state_id, top_menu, path)
                previous_rows = popup_rows
                popup_rows, _ = _capture_fresh_root_popup_for_sibling(
                    state_id=state_id,
                    top_menu=top_menu,
                    parent_path=parent_path,
                    target_row=row,
                    canonical_top_menu_names=canonical_top_menu_names,
                    popup_state=popup_state,
                    stage=f"post_action:{' > '.join(path)}",
                )
                if menu_helpers._snapshot_keys(previous_rows) != menu_helpers._snapshot_keys(popup_rows):
                    transition["menu_state_changed"] = True
                    logger.info("ACTION_CHANGED_MENU_STATE state={} top_menu={} path={} action_state_classification=changes_menu_state", state_id, top_menu, path)
                    action_state_classification = "changes_menu_state"
            if transition.get("result_type") in {"no_visible_change", "no_observable_effect"} and transition.get("attempted"):
                _safe_depth_decision(
                    state_id=state_id,
                    path=path,
                    current_depth=depth,
                    max_depth=max_depth,
                    action_state_classification=action_state_classification or "executes_command",
                )

        node = _row_to_node(
            state_id,
            top_menu,
            asdict(row),
            level=depth,
            index=row.row_index,
            path=path,
            children=children_nodes,
            opens_submenu=opens_submenu,
            opens_dialog=transition.get("result_type") in {"dialog_opened", "modal_opened", "main_window_disabled_modal_likely", "window_opened", "project_open_state_transition"},
            opens_modal=opens_modal,
            skipped_by_safety=skipped,
            reused_from_previous_state=reused_from_previous_state,
        )
        node.action_state_classification = action_state_classification
        nodes.append(asdict(node))
        actions.append(
            classify_post_click_result(
                process_id=None,
                before_snapshot=before_action,
                after_snapshot=capture_state_snapshot(state_id),
                dialog_detection=transition,
                state_id=state_id,
                top_menu=top_menu,
                row_index=row.row_index,
                menu_path=path,
                action_key=" > ".join(path),
                safety_level=classify_safety([clean_menu_title(part) for part in path]),
                attempted=bool(transition.get("project_open_state_transition")) or (not skipped and not reused_from_previous_state),
                notes="reused_from_previous_state" if reused_from_previous_state else "mapped_only",
                action_state_classification=action_state_classification,
            )
        )
        admitted, admission_reason, rejection_reason = _evaluate_action_admission(
            row=row,
            path=path,
            action_state_classification=action_state_classification,
            transition=transition,
            opens_submenu=opens_submenu,
            opens_modal=opens_modal,
            skip_reason=skip_reason,
            traversal_depth=depth,
        )
        probe_evidence: dict[str, Any] | None = None
        if not admitted and _should_run_action_evidence_probe(row=row, rejection_reason=rejection_reason):
            probed_rows += 1
            probe_evidence = _run_action_evidence_probe(
                state_id=state_id,
                top_menu=top_menu,
                path=path,
                row=row,
                popup_rows=popup_rows,
                current_rows=current_rows if 'current_rows' in locals() else None,
            )
            transition = dict(transition)
            transition["interaction_evidence_probe"] = probe_evidence
            transition["result_type"] = probe_evidence.get("result_type") or transition.get("result_type")
            row.meta = dict(row.meta)
            row.meta["interaction_evidence_probe"] = dict(probe_evidence)
            admitted, admission_reason, rejection_reason = _evaluate_action_admission(
                row=row,
                path=path,
                action_state_classification=action_state_classification,
                transition=transition,
                opens_submenu=opens_submenu or bool(probe_evidence.get("child_popup_opened")),
                opens_modal=opens_modal or bool(probe_evidence.get("new_dialog_detected")),
                skip_reason=skip_reason,
                traversal_depth=depth,
                probe_evidence=probe_evidence,
            )
            if admitted:
                admitted_after_probe += 1
                logger.info("ACTION_ADMISSION_ACCEPTED_WITH_PROBE top_menu={} path={} traversal_depth={} reason={} probe_result_type={} evidence_strength={}", top_menu, path, depth, admission_reason, probe_evidence.get("result_type"), probe_evidence.get("evidence_strength"))
            else:
                logger.info("ACTION_ADMISSION_STILL_REJECTED_AFTER_PROBE top_menu={} path={} traversal_depth={} reason={} probe_result_type={} evidence_strength={}", top_menu, path, depth, rejection_reason, probe_evidence.get("result_type"), probe_evidence.get("evidence_strength"))
        _update_row_admission_flags(
            row,
            admitted=admitted,
            admission_reason=admission_reason,
            rejection_reason=rejection_reason,
        )
        if admitted:
            action_catalog.append(
                _build_action_catalog_entry(
                    path=path,
                    action_type=row.action_type,
                    action_state_classification=action_state_classification,
                    opens_modal=opens_modal,
                    opens_submenu=opens_submenu,
                    changes_menu_state=action_state_classification == "changes_menu_state",
                    opens_project_and_changes_runtime_state=action_state_classification == "opens_project_and_changes_runtime_state",
                    traversal_depth=depth,
                    skip_reason=skip_reason,
                )
            )
        if project_open_transition_detected:
            break

    _log_phase_timing("subtree_traversal", traversal_started_at, state_id=state_id, top_menu=top_menu, depth=depth, rows=len(current_level_rows), nodes=len(nodes), actions=len(actions))
    logger.info(
        "ACTION_CATALOG_OUTPUT_SUMMARY state={} top_menu={} depth={} candidate_rows={} probed_rows={} admitted_after_probe={} admitted_actions={} still_structure_only={} suppressed_unknown={} placeholders_retained={} ",
        state_id,
        top_menu,
        depth,
        len(current_level_rows),
        probed_rows,
        admitted_after_probe,
        len(action_catalog),
        sum(1 for row in current_level_rows if row.retained_as_structure_only),
        sum(1 for row in current_level_rows if row.rejection_reason == "unknown_classification_suppressed"),
        sum(1 for row in current_level_rows if _is_placeholder_row(row)),
    )
    for action in action_catalog:
        actions_by_path = {tuple(item.menu_path if isinstance(item, RuntimeActionResult) else item.get("menu_path", [])): item for item in actions}
        action_result = actions_by_path.get(tuple(action["path"]))
        if action_result is not None:
            details = action_result.event_details if isinstance(action_result, RuntimeActionResult) else action_result.get("event_details", {})
            action["changes_menu_state"] = bool(action["changes_menu_state"] or details.get("menu_state_changed"))
    return nodes, collected_rows, actions, dialogs, windows, action_catalog


def _state_summary_markdown(state_map: RuntimeStateMap) -> str:
    enabled = sum(1 for item in state_map.menu_rows if item.get("enabled_guess") is True)
    disabled = sum(1 for item in state_map.menu_rows if item.get("enabled_guess") is False)
    submenu_count = sum(1 for item in state_map.actions if item.get("result_type") == "success_popup_opened")
    dialog_candidates = len(state_map.dialogs)
    return "\n".join(
        [
            f"# Runtime summary ({state_map.state_id})",
            "",
            f"- top menük száma: {len(state_map.top_menus)}",
            f"- összes menüpont: {len(state_map.menu_rows)}",
            f"- enabled: {enabled}",
            f"- disabled: {disabled}",
            f"- submenu count: {submenu_count}",
            f"- dialog candidates: {dialog_candidates}",
            "",
        ]
    )


def _diff_summary_markdown(diff: RuntimeStateDiff) -> str:
    return "\n".join(
        [
            "# Runtime állapot diff",
            "",
            f"- shared top-level menük: {len(diff.top_menu_diff.get('shared', []))}",
            f"- csak projekt után látható elemek: {len(diff.project_only_paths)}",
            f"- enabled változások: {len(diff.enabled_state_changes)}",
            "",
        ]
    )


def _retain_selected_top_menus(
    *,
    retained: dict[str, dict[str, Any]],
    canonical_top_menus: dict[str, Any],
    target_menu_map: dict[str, str],
    state_id: str,
) -> None:
    for item in canonical_top_menus["items"]:
        if item["normalized"] not in target_menu_map:
            continue
        retained[item["normalized"]] = {
            "state_id": state_id,
            "text": item["clean"],
            "text_raw": item["raw"],
            "text_normalized": item["normalized"],
        }


def map_runtime_state(
    *,
    state_id: str,
    safe_mode: str = "off",
    top_menus: list[str] | None = None,
    max_submenu_depth: int | None = None,
    include_disabled: bool = True,
    known_paths_to_skip: set[tuple[str, ...]] | None = None,
) -> RuntimeStateMap:
    snapshot = capture_state_snapshot(state_id)
    discovered = snapshot.discovered_top_menus
    canonical_top_menus = get_canonical_top_menu_names(discovered)
    target_menus = top_menus or DEFAULT_TOP_MENUS
    target_menu_map = {normalize_menu_title(item): item for item in target_menus}
    retained_top_menus: dict[str, dict[str, Any]] = {}
    _retain_selected_top_menus(
        retained=retained_top_menus,
        canonical_top_menus=canonical_top_menus,
        target_menu_map=target_menu_map,
        state_id=state_id,
    )
    logger.info(
        "MAP_RUNTIME_STATE_SELECTION state_id={} discovered={} canonical={} requested={} normalized_targets={}",
        state_id,
        discovered,
        [item["raw"] for item in canonical_top_menus["items"]],
        top_menus or DEFAULT_TOP_MENUS,
        list(target_menu_map),
    )

    all_rows: list[RuntimeMenuRow] = []
    all_tree: list[dict[str, Any]] = []
    all_actions: list[RuntimeActionResult] = []
    all_dialogs: list[RuntimeDialogRecord] = []
    all_windows: list[RuntimeWindowRecord] = []
    all_action_catalog: list[dict[str, Any]] = []

    partial_mapping = False
    stop_reason: str | None = None
    popup_state = PopupState()

    target_menu_keys = list(target_menu_map.keys())
    index = 0
    while index < len(target_menu_keys):
        top_menu_normalized = target_menu_keys[index]
        discovered_top_menu = canonical_top_menus["normalized_to_raw"].get(top_menu_normalized)
        if not discovered_top_menu:
            logger.warning(
                "MAP_RUNTIME_STATE_MENU_SKIPPED state_id={} requested_menu={} reason=not_found_in_canonical available={}",
                state_id,
                top_menu_normalized,
                [item["raw"] for item in canonical_top_menus["items"]],
            )
            index += 1
            continue

        rows: list[RuntimeMenuRow] = []
        try:
            tree, rows, actions, dialogs, windows, action_catalog = explore_menu_tree(
                state_id=state_id,
                top_menu=discovered_top_menu,
                safe_mode=safe_mode,
                max_depth=max_submenu_depth,
                include_disabled=include_disabled,
                canonical_top_menu_names=canonical_top_menus["normalized_names"],
                visited_paths={(normalize_menu_title(discovered_top_menu),)},
                visited_path_hashes={hash((normalize_menu_title(discovered_top_menu),))},
                known_paths_to_skip=known_paths_to_skip,
                popup_state=popup_state,
            )
            clean_top_menu = clean_menu_title(discovered_top_menu)
            normalized_top_menu = normalize_menu_title(discovered_top_menu)
            logger.debug('RAW_MENU_TITLE="{}" NORMALIZED_MENU_TITLE="{}"', discovered_top_menu, normalized_top_menu)
            all_tree.append({"state_id": state_id, "title_raw": discovered_top_menu, "title_normalized": normalized_top_menu, "title": clean_top_menu, "path": [clean_top_menu], "children": tree})
            retained_top_menus[normalized_top_menu] = {
                "state_id": state_id,
                "text": clean_top_menu,
                "text_raw": discovered_top_menu,
                "text_normalized": normalized_top_menu,
            }
            all_rows.extend(rows)
            all_actions.extend(actions)
            all_dialogs.extend(dialogs)
            all_windows.extend(windows)
            all_action_catalog.extend(action_catalog)
            logger.info(
                "MAP_RUNTIME_STATE_MENU_RESULT state_id={} top_menu={} rows={} nodes={} actions={} dialogs={} windows={} catalog={}",
                state_id,
                discovered_top_menu,
                len(rows),
                len(tree),
                len(actions),
                len(dialogs),
                len(windows),
                len(action_catalog),
            )
            if popup_state.runtime_state_reset_required:
                snapshot = capture_state_snapshot(state_id)
                canonical_top_menus = get_canonical_top_menu_names(snapshot.discovered_top_menus)
                _retain_selected_top_menus(
                    retained=retained_top_menus,
                    canonical_top_menus=canonical_top_menus,
                    target_menu_map=target_menu_map,
                    state_id=state_id,
                )
                logger.info(
                    "MAP_RUNTIME_STATE_POST_RESET state_id={} discovered={} canonical={} retained={}",
                    state_id,
                    snapshot.discovered_top_menus,
                    [item["raw"] for item in canonical_top_menus["items"]],
                    list(retained_top_menus),
                )
                popup_state.runtime_state_reset_required = False
        except Exception as exc:
            logger.exception("Top menu mapping failed: {}", discovered_top_menu)
            all_actions.append(
                asdict(
                    classify_post_click_result(
                        process_id=None,
                        before_snapshot=snapshot,
                        after_snapshot=snapshot,
                        dialog_detection=None,
                        state_id=state_id,
                        top_menu=clean_menu_title(discovered_top_menu),
                        row_index=-1,
                        menu_path=[clean_menu_title(discovered_top_menu)],
                        action_key=clean_menu_title(discovered_top_menu),
                        safety_level="caution",
                        attempted=False,
                        error_text=str(exc),
                        forced_result_type="failed_focus",
                    )
                )
            )
            if "WinWatt" in type(exc).__name__ or "focus_not_restored" in str(exc):
                recovered = restore_clean_menu_baseline(state_id=state_id, stage=f"recover_after_exception:{discovered_top_menu}")
                if recovered:
                    logger.warning(
                        "recovered from focus loss, continuing mapping state={} top_menu={}",
                        state_id,
                        discovered_top_menu,
                    )
                else:
                    partial_mapping = True
                    stop_reason = f"unrecoverable:{discovered_top_menu}"
                    logger.error("unrecoverable main window loss during top menu state={} top_menu={}", state_id, discovered_top_menu)
                    break

        if should_restore_clean_menu_baseline(state_id=state_id, stage=f"after:{discovered_top_menu}"):
            if not restore_clean_menu_baseline(state_id=state_id, stage=f"after:{discovered_top_menu}"):
                partial_mapping = True
                stop_reason = f"lost_main_window_after:{discovered_top_menu}"
                logger.error("unrecoverable main window loss after top menu state={} top_menu={}", state_id, discovered_top_menu)
                break
        index += 1

    snapshot_payload = asdict(snapshot)
    snapshot_payload["mapping_partial"] = partial_mapping
    snapshot_payload["mapping_stop_reason"] = stop_reason
    state_actions = [item if isinstance(item, dict) else asdict(item) for item in all_actions]
    state_transitions = _build_state_transitions_from_actions(state_actions)

    final_top_menus = [retained_top_menus[key] for key in target_menu_map if key in retained_top_menus]
    logger.info(
        "MAP_RUNTIME_STATE_FINAL_COUNTS state_id={} retained_top_menus={} rows={} actions={} dialogs={} windows={} transitions={} partial={} stop_reason={}",
        state_id,
        [item["text_raw"] for item in final_top_menus],
        len(all_rows),
        len(state_actions),
        len(all_dialogs),
        len(all_windows),
        len(state_transitions),
        partial_mapping,
        stop_reason,
    )

    state_map = RuntimeStateMap(
        state_id=state_id,
        snapshot=snapshot_payload,
        top_menus=final_top_menus,
        menu_rows=[asdict(item) for item in all_rows],
        menu_tree=all_tree,
        actions=state_actions,
        dialogs=[asdict(item) for item in all_dialogs],
        windows=[asdict(item) for item in all_windows],
        skipped_actions=[item if isinstance(item, dict) else asdict(item) for item in all_actions if (item.get("attempted") if isinstance(item, dict) else item.attempted) is False],
        action_catalog=all_action_catalog,
        state_transitions=state_transitions,
    )
    state_map.state_atlas = _build_state_atlas_entry(state_map)
    return state_map


def run_single_row_probe(
    *,
    state_id: str,
    top_menu: str,
    probe_row_text: str,
    probe_row_index: int | None = None,
    repeat: int = 1,
) -> dict[str, Any]:
    repeat = max(1, int(repeat))
    if not restore_clean_menu_baseline(state_id=state_id, stage="single_row_probe:start"):
        raise UnrecoverableMainWindowError("single_row_probe_baseline_restore_failed")

    initial_snapshot = capture_state_snapshot(state_id)
    canonical_top_menus = get_canonical_top_menu_names(initial_snapshot.discovered_top_menus)
    canonical_name = canonical_top_menus["normalized_to_raw"].get(normalize_menu_title(top_menu))
    if not canonical_name:
        raise ValueError(f"Top menu {top_menu!r} not found.")

    logger.info(
        "SINGLE_ROW_PROBE_START state_id={} top_menu={} probe_row_text={!r} probe_row_index={} repeat={}",
        state_id,
        canonical_name,
        probe_row_text,
        probe_row_index,
        repeat,
    )

    iterations: list[dict[str, Any]] = []
    classification_priority = {
        "dialog_opened": 7,
        "window_opened": 6,
        "child_window_opened": 5,
        "mdi_child_opened": 5,
        "internal_window_opened": 5,
        "internal_child_window_opened": 5,
        "transient_hint_opened": 4,
        "popup_closed": 3,
        "focus_changed": 2,
        "no_observable_effect": 1,
    }

    for attempt in range(repeat):
        if not restore_clean_menu_baseline(state_id=state_id, stage=f"single_row_probe:attempt:{attempt + 1}:baseline"):
            raise UnrecoverableMainWindowError(f"single_row_probe_baseline_restore_failed:{attempt + 1}")
        popup_rows, _transition = _open_and_capture_root_menu(
            state_id=state_id,
            top_menu=canonical_name,
            canonical_top_menu_names=canonical_top_menus["normalized_names"],
        )
        menu_rows = _build_menu_rows_from_popup_rows(
            state_id,
            canonical_name,
            popup_rows,
            canonical_top_menu_names=canonical_top_menus["normalized_names"],
        )
        target_row, resolution = _select_probe_target_row(
            menu_rows=menu_rows,
            probe_row_text=probe_row_text,
            probe_row_index=probe_row_index,
        )
        logger.info(
            "SINGLE_ROW_PROBE_TARGET_RESOLUTION requested_text={!r} requested_index={} matched_by={} resolved_row_text={!r} resolved_row_index={} resolved_rectangle={}",
            resolution.get("requested_text"),
            resolution.get("requested_index"),
            resolution.get("matched_by"),
            resolution.get("resolved_row_text"),
            resolution.get("resolved_row_index"),
            resolution.get("resolved_rectangle"),
        )
        if target_row is None:
            diagnostic_summary = {
                "top_menu": canonical_name,
                "requested_text": probe_row_text,
                "requested_index": probe_row_index,
                "available_row_texts": resolution.get("available_row_texts", []),
                "available_row_indices": resolution.get("available_row_indices", []),
                "placeholder_count": resolution.get("placeholder_count", 0),
                "message": "Probe target could not be resolved from the currently available popup rows.",
            }
            logger.info("SINGLE_ROW_PROBE_TARGET_UNRESOLVED attempt={} payload={}", attempt + 1, diagnostic_summary)
            return {
                "state_id": state_id,
                "top_menu": canonical_name,
                "probe_row_text": probe_row_text,
                "probe_row_index": probe_row_index,
                "repeat": repeat,
                "iterations": iterations,
                "final_classification": "target_unresolved",
                "summary": {
                    "provable_change": False,
                    "action_like": False,
                    "repeat": repeat,
                    "top_menu": canonical_name,
                    "probe_row_text": probe_row_text,
                    "probe_row_index": probe_row_index,
                    "final_classification": "target_unresolved",
                    "action_type": _derive_action_type(classification="target_unresolved", provable_change=False, action_like=False),
                    "policy": _action_discovery_policy(_derive_action_type(classification="target_unresolved", provable_change=False, action_like=False)),
                    "diagnostic_summary": diagnostic_summary,
                },
            }
        target_payload = _single_row_probe_target_payload(top_menu=canonical_name, row=target_row)
        logger.info(
            "SINGLE_ROW_PROBE_TARGET attempt={} top_menu={} row_index={} text={!r} source_scope={} target_rect={} target_click_point={}",
            attempt + 1,
            canonical_name,
            target_row.row_index,
            target_row.text,
            target_payload["source_scope"],
            target_payload["target_rect"],
            target_payload["target_click_point"],
        )

        main_window = get_cached_main_window()
        before_state = _probe_snapshot(state_id=state_id, main_window=main_window, popup_rows=popup_rows)
        before_log = {key: value for key, value in before_state.items() if key != "runtime_snapshot"}
        logger.info("SINGLE_ROW_PROBE_PRE_STATE attempt={} payload={}", attempt + 1, before_log)

        _hover_single_row_probe_target(target=target_row, top_menu=canonical_name)

        click_error: str | None = None
        click_dispatch: dict[str, Any] | None = None
        try:
            click_dispatch = _dispatch_single_row_probe_click(target=target_row, popup_rows=popup_rows, top_menu=canonical_name)
        except Exception as exc:
            click_error = f"{exc.__class__.__name__}: {exc}"

        post_popup_rows = menu_helpers.capture_menu_popup_snapshot()
        after_state = _probe_snapshot(state_id=state_id, main_window=main_window, popup_rows=post_popup_rows)
        after_log = {key: value for key, value in after_state.items() if key != "runtime_snapshot"}
        logger.info("SINGLE_ROW_PROBE_POST_STATE attempt={} payload={}", attempt + 1, after_log)

        diff = _summarize_single_row_probe_diff(before=before_state, after=after_state)
        if click_error:
            diff["click_error"] = click_error
        logger.info("SINGLE_ROW_PROBE_DIFF attempt={} payload={}", attempt + 1, diff)
        iterations.append(
            {
                "attempt": attempt + 1,
                "target": {
                    "top_menu": canonical_name,
                    "row_index": target_row.row_index,
                    "text": target_row.text,
                    "rectangle": dict(target_row.rectangle),
                    "clickpoint": target_payload["target_click_point"],
                    "source_scope": target_payload["source_scope"],
                    "click_method": (click_dispatch or {}).get("click_method"),
                },
                "pre_state": before_log,
                "post_state": after_log,
                "diff": diff,
            }
        )

    final_classification = max(
        (item["diff"].get("classification") or "no_observable_effect" for item in iterations),
        key=lambda value: classification_priority.get(str(value), 0),
    )
    provable_change = final_classification != "no_observable_effect"
    action_like = final_classification in {
        "dialog_opened",
        "window_opened",
        "child_window_opened",
        "mdi_child_opened",
        "internal_window_opened",
        "internal_child_window_opened",
        "popup_closed",
        "focus_changed",
    }
    human_readable_outcome = {
        "dialog_opened": "A probe kattintás valódi dialogot nyitott.",
        "window_opened": "A probe kattintás valódi új ablakot nyitott.",
        "child_window_opened": "A probe kattintás a fő ablakon belül új belső child windowt nyitott.",
        "mdi_child_opened": "A probe kattintás a fő ablakon belül új MDI child ablakot nyitott.",
        "internal_window_opened": "A probe kattintás belső alkalmazásablakot nyitott a főablakon belül.",
        "internal_child_window_opened": "A probe kattintás a fő WinWatt ablakon belül valódi belső dokumentum/MDI gyerekablakot nyitott.",
        "transient_hint_opened": "A probe kattintás után csak transient hint/tooltip jelent meg, nem valódi dialog vagy funkcionális ablak.",
        "popup_closed": "A probe kattintás bezárta a popupot.",
        "focus_changed": "A probe kattintás fókuszváltást okozott.",
        "no_observable_effect": "A probe kattintás után nem látszott bizonyítható UI-változás.",
    }.get(final_classification, f"Probe outcome: {final_classification}")
    action_type = _derive_action_type(
        classification=final_classification,
        provable_change=provable_change,
        action_like=action_like,
    )
    summary = {
        "provable_change": provable_change,
        "action_like": action_like,
        "repeat": repeat,
        "top_menu": canonical_name,
        "probe_row_text": probe_row_text,
        "probe_row_index": probe_row_index,
        "final_classification": final_classification,
        "action_type": action_type,
        "policy": _action_discovery_policy(action_type),
        "human_readable_outcome": human_readable_outcome,
        "transient_hint_only": final_classification == "transient_hint_opened",
    }
    logger.info(
        "SINGLE_ROW_PROBE_FINAL_CLASSIFICATION top_menu={} probe_row_text={!r} probe_row_index={} repeat={} classification={} action_type={} provable_change={} action_like={}",
        canonical_name,
        probe_row_text,
        probe_row_index,
        repeat,
        final_classification,
        action_type,
        provable_change,
        action_like,
    )
    return {
        "state_id": state_id,
        "top_menu": canonical_name,
        "probe_row_text": probe_row_text,
        "probe_row_index": probe_row_index,
        "repeat": repeat,
        "iterations": iterations,
        "final_classification": final_classification,
        "summary": summary,
    }


def _normalized_path(path: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(normalize_menu_title(part) for part in path)


def _enabled_map(state: RuntimeStateMap) -> dict[tuple[str, ...], bool | None]:
    result: dict[tuple[str, ...], bool | None] = {}
    for row in state.menu_rows:
        if not _should_include_placeholder_in_final_outputs(row):
            continue
        path = _normalized_path(tuple(row.get("menu_path", [])))
        result[path] = row.get("enabled_guess")
    return result


def compare_runtime_states(state_a: RuntimeStateMap, state_b: RuntimeStateMap) -> RuntimeStateDiff:
    menus_a = {normalize_menu_title(item["text"]) for item in state_a.top_menus}
    menus_b = {normalize_menu_title(item["text"]) for item in state_b.top_menus}
    actions_a = {_normalized_path(tuple(item.get("menu_path", []))) for item in state_a.actions}
    actions_b = {_normalized_path(tuple(item.get("menu_path", []))) for item in state_b.actions}

    enabled_a = _enabled_map(state_a)
    enabled_b = _enabled_map(state_b)
    shared_paths = set(enabled_a) & set(enabled_b)
    enabled_changes = [
        {"path": list(path), "from": enabled_a[path], "to": enabled_b[path]}
        for path in sorted(shared_paths)
        if enabled_a[path] != enabled_b[path]
    ]

    project_only_paths = [list(path) for path in sorted(set(enabled_b) - set(enabled_a))]

    return RuntimeStateDiff(
        state_a=state_a.state_id,
        state_b=state_b.state_id,
        top_menu_diff={"only_in_a": sorted(menus_a - menus_b), "only_in_b": sorted(menus_b - menus_a), "shared": sorted(menus_a & menus_b)},
        menu_action_diff={"only_in_a": [list(x) for x in sorted(actions_a - actions_b)], "only_in_b": [list(x) for x in sorted(actions_b - actions_a)], "shared": [list(x) for x in sorted(actions_a & actions_b)]},
        dialog_diff={"only_in_a": [], "only_in_b": [], "shared": []},
        window_diff={"only_in_a": [], "only_in_b": [], "shared": []},
        summary={
            "shared_top_menus": len(menus_a & menus_b),
            "actions_only_in_a": len(actions_a - actions_b),
            "actions_only_in_b": len(actions_b - actions_a),
            "enabled_changes": len(enabled_changes),
            "project_only_paths": len(project_only_paths),
        },
        enabled_state_changes=enabled_changes,
        project_only_paths=project_only_paths,
    )


def _is_safe_mode_project_path_allowed(project_path: str) -> bool:
    normalized = str(project_path or "").replace("/", "\\").strip().lower()
    return normalized.endswith("\\winwatt_automation\\tests\\testwwp.wwp")


def open_test_project(project_path: str, *, safe_mode: str = "safe") -> dict[str, Any]:
    if safe_mode == "safe" and not _is_safe_mode_project_path_allowed(project_path):
        return {
            "success": False,
            "path": project_path,
            "dialog_found": False,
            "path_entered": False,
            "confirm_clicked": False,
            "dialog_closed": False,
            "project_state_changed": False,
            "detected_changes": [],
            "error": "Safe mode only allows explicitly approved test project path.",
            "project_open_audit": {
                "project_open_attempt_started": False,
                "project_open_menu_item_clicked": False,
                "open_file_dialog_detected": False,
                "file_dialog_path_entered": False,
                "file_dialog_confirm_clicked": False,
            },
        }

    before = asdict(capture_state_snapshot("project_open_before"))
    result = open_project_file_via_dialog_dict(
        project_path,
        before_snapshot=before,
        after_snapshot_provider=lambda: asdict(capture_state_snapshot("project_open_after")),
    )
    raw_path_entry_diagnostics = result.get("path_entry_diagnostics")
    path_entry_diagnostics = dict(raw_path_entry_diagnostics or {})
    interaction_helper_called = raw_path_entry_diagnostics is not None
    dialog_context_passed = dict(result.get("helper_received_dialog_context") or {})
    dialog_detected_before_interaction = bool(
        result.get("dialog_found")
        or dialog_context_passed.get("dialog_already_verified")
        or result.get("detected_dialog_snapshot")
    )
    path_entry_strategy_selected = path_entry_diagnostics.get("path_entry_strategy_selected")
    if path_entry_strategy_selected is None:
        if not interaction_helper_called:
            path_entry_strategy_null_reason = "interaction_helper_not_called"
        elif not dialog_context_passed:
            path_entry_strategy_null_reason = "dialog_context_missing"
        elif not dialog_context_passed.get("dialog_already_verified"):
            path_entry_strategy_null_reason = "precondition_failed"
        else:
            path_entry_strategy_null_reason = path_entry_diagnostics.get("path_entry_strategy_null_reason") or "interaction_aborted_before_strategy_selection"
    else:
        path_entry_strategy_null_reason = None
    audit = {
        "project_open_attempt_started": True,
        "project_open_menu_item_clicked": bool(result.get("dialog_found") or result.get("path_entered") or result.get("confirm_clicked") or result.get("dialog_closed") or result.get("project_state_changed")),
        "open_file_dialog_detected": bool(result.get("dialog_found")),
        "file_dialog_path_entered": bool(result.get("path_entered")),
        "file_dialog_confirm_clicked": bool(result.get("confirm_clicked")),
        "project_open_method": result.get("project_open_method"),
        "project_open_sequence": list(result.get("project_open_sequence") or []),
        "dialog_detected_before_interaction": dialog_detected_before_interaction,
        "dialog_context_passed_to_interaction": dialog_context_passed,
        "interaction_helper_called": interaction_helper_called,
        "interaction_helper_result_present": interaction_helper_called,
        "path_entry_strategy_selected": path_entry_strategy_selected,
        "path_entry_strategy_null_reason": path_entry_strategy_null_reason,
        "focused_input_entry_attempted": bool(path_entry_diagnostics.get("focused_input_entry_attempted")),
        "focused_input_entry_sent": bool(path_entry_diagnostics.get("focused_input_entry_sent")),
        "enter_confirm_sent": bool(path_entry_diagnostics.get("enter_confirm_sent")),
        "post_confirm_dialog_closed": bool(path_entry_diagnostics.get("post_confirm_dialog_closed", result.get("dialog_closed"))),
        "post_confirm_title": path_entry_diagnostics.get("post_confirm_title") or result.get("observed_main_window_title_after_open"),
        "post_confirm_path_match": bool(path_entry_diagnostics.get("post_confirm_path_match", result.get("path_match_normalized"))),
        "observed_project_path": result.get("observed_project_path"),
        "path_match_normalized": bool(result.get("path_match_normalized")),
    }
    result["project_open_audit"] = audit
    needs_recovery = bool(not result.get("dialog_closed") or not result.get("path_match_normalized"))
    if needs_recovery:
        recovery = recover_after_project_open()
        recovery["main_window_ready_after_attempt"] = bool(recovery.get("success"))
        recovery["attempted"] = True
    else:
        recovery = {
            "success": True,
            "main_window_ready_after_attempt": True,
            "attempted": False,
            "reason": "not_needed",
            "close_attempts": [],
            "diagnostics": {},
            "modal_pending": False,
        }
    result["recovery"] = recovery
    return result


def _write_state_outputs(state_dir: Path, state_map: RuntimeStateMap) -> None:
    write_json(state_dir / "snapshot.json", state_map.snapshot)
    write_json(state_dir / "menu_tree.json", state_map.menu_tree)
    write_json(state_dir / "top_menus.json", state_map.top_menus)
    write_json(state_dir / "top_menu_rows.json", state_map.menu_rows)
    write_json(state_dir / "actions.json", state_map.actions)
    write_json(state_dir / "action_catalog.json", state_map.action_catalog)
    write_json(state_dir / "state_transitions.json", state_map.state_transitions)
    write_json(state_dir / "state_atlas.json", state_map.state_atlas)
    write_json(state_dir / "dialogs.json", state_map.dialogs)
    write_json(state_dir / "windows.json", state_map.windows)
    (state_dir / "summary.md").write_text(_state_summary_markdown(state_map), encoding="utf-8")


def _collect_known_menu_paths(state_map: RuntimeStateMap) -> set[tuple[str, ...]]:
    paths: set[tuple[str, ...]] = set()
    for row in state_map.menu_rows:
        normalized = _normalized_path(tuple(row.get("menu_path", [])))
        if normalized:
            paths.add(normalized)
    return paths


def _collect_state_knowledge(state_map: RuntimeStateMap) -> dict[str, list[list[str]]]:
    menu_paths = [
        list(item)
        for item in sorted({_normalized_path(tuple(row.get("menu_path", []))) for row in state_map.menu_rows if row.get("menu_path")})
    ]
    dialog_signatures = sorted(
        {
            (
                normalize_menu_title(" > ".join(dialog.get("menu_path", []))),
                normalize_menu_title(dialog.get("title", "")),
                normalize_menu_title(dialog.get("class_name", "")),
            )
            for dialog in state_map.dialogs
        }
    )
    window_signatures = sorted(
        {
            (
                normalize_menu_title(" > ".join(window.get("menu_path", []))),
                normalize_menu_title(window.get("title", "")),
                normalize_menu_title(window.get("class_name", "")),
            )
            for window in state_map.windows
        }
    )
    return {
        "menu_paths": menu_paths,
        "dialog_signatures": [list(item) for item in dialog_signatures],
        "window_signatures": [list(item) for item in window_signatures],
    }


def _compute_knowledge_verification(current: dict[str, Any], baseline: dict[str, Any] | None) -> dict[str, Any]:
    baseline = baseline or {}

    def _to_set(values: list[Any] | None) -> set[tuple[Any, ...]]:
        return {tuple(item) if isinstance(item, list) else tuple([item]) for item in (values or [])}

    current_menus = _to_set(current.get("menu_paths"))
    baseline_menus = _to_set(baseline.get("menu_paths"))
    current_dialogs = _to_set(current.get("dialog_signatures"))
    baseline_dialogs = _to_set(baseline.get("dialog_signatures"))
    current_windows = _to_set(current.get("window_signatures"))
    baseline_windows = _to_set(baseline.get("window_signatures"))

    missing_menu_paths = [list(item) for item in sorted(baseline_menus - current_menus)]
    new_menu_paths = [list(item) for item in sorted(current_menus - baseline_menus)]
    missing_dialogs = [list(item) for item in sorted(baseline_dialogs - current_dialogs)]
    new_dialogs = [list(item) for item in sorted(current_dialogs - baseline_dialogs)]
    missing_windows = [list(item) for item in sorted(baseline_windows - current_windows)]
    new_windows = [list(item) for item in sorted(current_windows - baseline_windows)]

    baseline_total = len(baseline_menus)
    covered = baseline_total - len(missing_menu_paths)
    coverage_pct = 100.0 if baseline_total == 0 else round((covered / baseline_total) * 100, 2)

    return {
        "baseline_loaded": bool(baseline),
        "missing_menu_paths": missing_menu_paths,
        "new_menu_paths": new_menu_paths,
        "missing_dialogs": missing_dialogs,
        "new_dialogs": new_dialogs,
        "missing_windows": missing_windows,
        "new_windows": new_windows,
        "known_menu_paths": baseline_total,
        "current_menu_paths": len(current_menus),
        "covered_known_menu_paths": covered,
        "coverage_pct": coverage_pct,
    }


def _load_previous_knowledge(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("current") if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("knowledge_load_failed path={} error={}", path, exc)
        return None


def _knowledge_markdown(verification: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Runtime tudás verifikáció",
            "",
            f"- baseline loaded: {verification.get('baseline_loaded')}",
            f"- known menu paths: {verification.get('known_menu_paths')}",
            f"- covered known paths: {verification.get('covered_known_menu_paths')}",
            f"- missing menu paths: {len(verification.get('missing_menu_paths', []))}",
            f"- new menu paths: {len(verification.get('new_menu_paths', []))}",
            f"- missing dialogs: {len(verification.get('missing_dialogs', []))}",
            f"- missing windows: {len(verification.get('missing_windows', []))}",
            f"- coverage: {verification.get('coverage_pct')}%",
            "",
        ]
    )


def build_full_runtime_program_map(
    project_path: str | None = None,
    safe_mode: str = "off",
    output_dir: str | Path = "data/runtime_maps",
    state_id_prefix: str = "state",
    top_menus: list[str] | None = None,
    max_submenu_depth: int | None = None,
    include_disabled: bool = True,
    event_recorder: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    paths = ensure_output_dirs(Path(output_dir))
    knowledge_path = paths["base"] / "knowledge.json"
    previous_knowledge = _load_previous_knowledge(knowledge_path)
    no_project_id = "no_project" if state_id_prefix == "state" else f"{state_id_prefix}_no_project"
    project_id = "project_open" if state_id_prefix == "state" else f"{state_id_prefix}_project_open"
    effective_project_path = project_path or DEFAULT_TEST_PROJECT_PATH

    no_project_bootstrap = prepare_fresh_winwatt_session()

    startup_snapshot = _safe_capture_snapshot("startup_before_no_project_mapping")
    startup_project_path = _extract_project_path_from_title(startup_snapshot.main_window_title if startup_snapshot else "")
    startup_project_detected = bool(startup_project_path)
    already_open_before_mapping = startup_project_detected

    state_no_project = map_runtime_state(
        state_id=no_project_id,
        safe_mode=safe_mode,
        top_menus=top_menus,
        max_submenu_depth=max_submenu_depth,
        include_disabled=include_disabled,
    )
    state_no_project.snapshot["startup_project_detected"] = startup_project_detected
    state_no_project.snapshot["observed_startup_project_path"] = startup_project_path
    state_no_project.snapshot["already_open_before_mapping"] = already_open_before_mapping
    state_no_project.snapshot["bootstrap"] = no_project_bootstrap
    if event_recorder:
        event_recorder(
            "state_mapped",
            {
                "state_id": state_no_project.state_id,
                "top_menus": len(state_no_project.top_menus),
                "actions": len(state_no_project.actions),
                "dialogs": len(state_no_project.dialogs),
            },
        )
    _write_state_outputs(paths["state_no_project"], state_no_project)

    project_open_bootstrap = prepare_fresh_winwatt_session(project_path=effective_project_path)
    project_open_result = {
        "success": bool(project_open_bootstrap.get("snapshot_ready")),
        "dialog_found": False,
        "path_entry_attempted": False,
        "path_entered": False,
        "confirm_attempted": False,
        "confirm_clicked": False,
        "dialog_closed": False,
        "project_state_changed": bool(project_open_bootstrap.get("snapshot_ready")),
        "detected_changes": ["fresh_process_launch"] if project_open_bootstrap.get("snapshot_ready") else [],
        "project_open_method": "direct_launch",
        "project_open_sequence": [effective_project_path],
        "recovery": {
            "success": bool(project_open_bootstrap.get("snapshot_ready")),
            "reason": "fresh_process_launch",
            "modal_pending": False,
            "main_window_ready_after_attempt": bool(project_open_bootstrap.get("snapshot_ready")),
            "diagnostics": {"bootstrap": project_open_bootstrap},
            "close_attempts": [],
        },
        "project_open_audit": {
            "project_open_attempt_started": True,
            "project_open_method": "direct_launch",
            "project_open_sequence": [effective_project_path],
            "project_open_menu_item_clicked": False,
            "open_file_dialog_detected": False,
            "file_dialog_path_entered": False,
            "file_dialog_confirm_clicked": False,
            "interaction_helper_called": False,
            "interaction_helper_result_present": False,
            "path_entry_strategy_selected": None,
            "path_entry_strategy_null_reason": "direct_project_launch_bootstrap",
            "focused_input_entry_attempted": False,
            "focused_input_entry_sent": False,
            "enter_confirm_sent": False,
            "post_confirm_dialog_closed": False,
            "post_confirm_title": project_open_bootstrap.get("snapshot_title"),
            "post_confirm_path_match": bool(
                _normalize_project_path(project_open_bootstrap.get("snapshot_project_path")) == _normalize_project_path(effective_project_path)
            ),
        },
        "bootstrap": project_open_bootstrap,
        "error": None if project_open_bootstrap.get("snapshot_ready") else "fresh_process_launch_failed",
    }
    recovery = (project_open_result or {}).get("recovery") if project_open_result else None
    verification_snapshot = _safe_capture_snapshot("project_open_verification")
    project_path_verification = _build_project_path_verification(
        expected_project_path=effective_project_path,
        observed_main_window_title=verification_snapshot.main_window_title if verification_snapshot else "",
    )
    project_open_verdict = _project_open_verdict(
        already_open_before_mapping=already_open_before_mapping,
        path_match_normalized=bool(project_path_verification.get("path_match_normalized")),
        open_attempt_success=bool((project_open_result or {}).get("success")),
    )
    if project_open_result is not None:
        project_open_result.update(project_path_verification)
        project_open_result["startup_project_detected"] = startup_project_detected
        project_open_result["observed_startup_project_path"] = startup_project_path
        project_open_result["already_open_before_mapping"] = already_open_before_mapping
        project_open_result["project_open_verdict"] = project_open_verdict
        project_open_result["observed_main_window_title_after_open"] = verification_snapshot.main_window_title if verification_snapshot else ""
    _record_project_open_step_events(
        event_recorder,
        project_open_result=project_open_result,
        project_path_verification=project_path_verification,
        verification_snapshot=verification_snapshot,
    )
    if event_recorder and project_open_result:
        project_open_payload = {
            "success": bool(project_open_result.get("success")),
            "error": project_open_result.get("error"),
            "dialog_found": bool(project_open_result.get("dialog_found")),
            "startup_project_detected": startup_project_detected,
            "already_open_before_mapping": already_open_before_mapping,
            "project_open_verdict": project_open_verdict,
            "expected_project_path": project_path_verification.get("expected_project_path"),
            "observed_project_path": project_path_verification.get("observed_project_path"),
            "path_match_normalized": project_path_verification.get("path_match_normalized"),
            **dict(project_open_result.get("project_open_audit") or {}),
        }
        project_open_payload.setdefault("project_open_method", project_open_result.get("project_open_method"))
        project_open_payload.setdefault("project_open_sequence", list(project_open_result.get("project_open_sequence") or []))
        event_recorder("project_open_result", project_open_payload)
    if event_recorder and recovery:
        event_recorder(
            "project_open_recovery",
            {
                "success": bool(recovery.get("success")),
                "reason": recovery.get("reason"),
                "modal_detected": bool(recovery.get("modal_pending")),
                "main_window_ready_after_attempt": bool(recovery.get("main_window_ready_after_attempt")),
            },
        )

    if recovery and not recovery.get("success"):
        state_project_open = RuntimeStateMap(
            state_id=project_id,
            snapshot={
                "state_id": project_id,
                "mapping_partial": True,
                "mapping_stop_reason": "project_open_recovery_failed",
                "project_open_recovery": recovery,
                "recovery_diagnostics": recovery.get("diagnostics", {}),
            },
            top_menus=[],
            menu_rows=[],
            menu_tree=[],
            actions=[],
            dialogs=[],
            windows=[],
            skipped_actions=[],
        )
        state_project_open.state_atlas = _build_state_atlas_entry(state_project_open)
    else:
        state_project_open = map_runtime_state(
            state_id=project_id,
            safe_mode=safe_mode,
            top_menus=top_menus,
            max_submenu_depth=max_submenu_depth,
            include_disabled=include_disabled,
        )
        if recovery:
            state_project_open.snapshot["project_open_recovery"] = recovery
    state_project_open.snapshot["startup_project_detected"] = startup_project_detected
    state_project_open.snapshot["observed_startup_project_path"] = startup_project_path
    state_project_open.snapshot["already_open_before_mapping"] = already_open_before_mapping
    state_project_open.snapshot["bootstrap"] = project_open_bootstrap
    state_project_open.snapshot.update(project_path_verification)
    state_project_open.snapshot["project_open_verdict"] = project_open_verdict
    if event_recorder:
        event_recorder(
            "state_mapped",
            {
                "state_id": state_project_open.state_id,
                "top_menus": len(state_project_open.top_menus),
                "actions": len(state_project_open.actions),
                "dialogs": len(state_project_open.dialogs),
            },
        )
    _write_state_outputs(paths["state_project_open"], state_project_open)

    runtime_state_atlas = _build_runtime_state_atlas(states=[state_no_project, state_project_open])
    write_json(paths["base"] / "runtime_state_atlas.json", runtime_state_atlas)

    diff = compare_runtime_states(state_no_project, state_project_open)
    if event_recorder:
        event_recorder(
            "runtime_diff",
            {
                "summary": dict(diff.summary),
                "enabled_changes": len(diff.enabled_state_changes),
                "project_only_paths": len(diff.project_only_paths),
            },
        )
    write_json(paths["diff"] / "state_diff.json", asdict(diff))
    (paths["diff"] / "summary.md").write_text(_diff_summary_markdown(diff), encoding="utf-8")

    current_knowledge = {
        "state_no_project": _collect_state_knowledge(state_no_project),
        "state_project_open": _collect_state_knowledge(state_project_open),
    }
    merged_current_knowledge = {
        "menu_paths": sorted({tuple(item) for item in current_knowledge["state_no_project"]["menu_paths"] + current_knowledge["state_project_open"]["menu_paths"]}),
        "dialog_signatures": sorted({tuple(item) for item in current_knowledge["state_no_project"]["dialog_signatures"] + current_knowledge["state_project_open"]["dialog_signatures"]}),
        "window_signatures": sorted({tuple(item) for item in current_knowledge["state_no_project"]["window_signatures"] + current_knowledge["state_project_open"]["window_signatures"]}),
    }
    merged_current_knowledge = {key: [list(item) for item in values] for key, values in merged_current_knowledge.items()}
    knowledge_verification = _compute_knowledge_verification(merged_current_knowledge, previous_knowledge)
    knowledge_payload = {
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        "current": merged_current_knowledge,
        "states": current_knowledge,
        "verification": knowledge_verification,
    }
    write_json(knowledge_path, knowledge_payload)
    (paths["base"] / "knowledge_summary.md").write_text(_knowledge_markdown(knowledge_verification), encoding="utf-8")
    if event_recorder:
        event_recorder("knowledge_verification", dict(knowledge_verification))

    skipped = sum(1 for action in state_no_project.actions + state_project_open.actions if not action.get("attempted", False))
    print(f"no_project menük száma: {len(state_no_project.top_menus)}")
    print(f"project_open menük száma: {len(state_project_open.top_menus)}")
    print(f"diff változások: {len(diff.enabled_state_changes) + len(diff.project_only_paths)}")
    print(f"skipped_by_safety: {skipped}")
    print(f"startup_project_detected: {startup_project_detected}")
    print(f"already_open_before_mapping: {already_open_before_mapping}")
    print(f"project_open_verdict: {project_open_verdict}")
    print(f"expected_project_path: {project_path_verification.get('expected_project_path')}")
    print(f"observed_project_path: {project_path_verification.get('observed_project_path')}")
    print(f"path_match_normalized: {project_path_verification.get('path_match_normalized')}")
    print(
        "knowledge verification: "
        f"missing={len(knowledge_verification['missing_menu_paths'])}, "
        f"new={len(knowledge_verification['new_menu_paths'])}, "
        f"coverage={knowledge_verification['coverage_pct']}%"
    )
    print(f"output: {paths['base']}")

    return {
        "state_no_project": state_no_project,
        "state_project_open": state_project_open,
        "diff": diff,
        "project_open_result": project_open_result,
        "project_open_verdict": project_open_verdict,
        "project_path_verification": project_path_verification,
        "knowledge_verification": knowledge_verification,
        "runtime_state_atlas": runtime_state_atlas,
        "output_dir": str(paths["base"]),
    }
