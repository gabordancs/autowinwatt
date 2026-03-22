"""Connection helpers for attaching to a running WinWatt instance."""

from __future__ import annotations

from collections import Counter
import ctypes
import time
from typing import TYPE_CHECKING
from typing import Any

from loguru import logger
from winwatt_automation.runtime_mapping.config import diagnostic_options
from winwatt_automation.runtime_mapping.timing import WINDOW_READY_POLL_INTERVAL, WINDOW_READY_TIMEOUT

MAIN_FRAME_CLASS_HINTS = ("main", "frame", "mdi", "awin", "tmain")
MODAL_CLASS_HINTS = ("dialog", "popup", "tool", "splash")

if TYPE_CHECKING:
    from pywinauto.base_wrapper import BaseWrapper


class WinWattNotRunningError(RuntimeError):
    """Raised when a running WinWatt process/window cannot be found."""


class WinWattMultipleWindowsError(WinWattNotRunningError):
    """Raised when multiple windows match and no deterministic winner can be picked."""

    def __init__(self, message: str, backend: str, candidates: list[dict[str, Any]]):
        super().__init__(message)
        self.backend = backend
        self.candidates = candidates


class FocusGuardError(RuntimeError):
    """Raised when focus guard validation fails with structured diagnostics."""

    def __init__(self, message: str, *, diagnostic: dict[str, Any] | None = None):
        super().__init__(message)
        self.diagnostic = diagnostic or {}


class WinWattSession:
    """Cached WinWatt attachment state for the current mapper run."""

    app: Any | None = None
    main_window: Any | None = None
    process_id: int | None = None
    handle: int | None = None


class MainWindowSession:
    window: Any | None = None
    process_id: int | None = None
    last_validation_monotonic: float = 0.0
    validation_interval_s: float = 4.0
    foreground_failure_count: int = 0
    last_foreground_failure_monotonic: float = 0.0
    last_resolve_attempt_monotonic: float = 0.0
    foreground_resolve_throttle_window_s: float = 12.0
    foreground_resolve_attempt_limit: int = 2
    last_focus_guard_diagnostic: dict[str, Any] = {}




def get_last_focus_guard_diagnostic() -> dict[str, Any]:
    """Return the most recent structured focus-guard diagnostic."""

    return dict(MainWindowSession.last_focus_guard_diagnostic)

def _safe_call(obj: Any, method_name: str, default: Any = None) -> Any:
    method = getattr(obj, method_name, None)
    if not callable(method):
        return default
    try:
        return method()
    except Exception:
        return default


def _safe_getattr(obj: Any, attr_name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, attr_name, default)
    except Exception:
        return default


def _rect_payload(rectangle: Any) -> dict[str, int] | None:
    if rectangle is None:
        return None

    left = getattr(rectangle, "left", None)
    top = getattr(rectangle, "top", None)
    right = getattr(rectangle, "right", None)
    bottom = getattr(rectangle, "bottom", None)
    if None in (left, top, right, bottom):
        return None

    width = max(0, int(right) - int(left))
    height = max(0, int(bottom) - int(top))
    return {
        "left": int(left),
        "top": int(top),
        "right": int(right),
        "bottom": int(bottom),
        "width": width,
        "height": height,
    }


def _candidate_from_window(window: "BaseWrapper", backend: str = "win32") -> dict[str, Any]:
    element_info = _safe_getattr(window, "element_info", window)
    title = _safe_call(window, "window_text", "") or ""
    class_name = _safe_call(window, "class_name", None) or _safe_getattr(element_info, "class_name", None)
    if backend == "uia":
        control_type = _safe_getattr(element_info, "control_type", None)
    else:
        control_type = None
    process_id = _safe_call(window, "process_id", None)
    handle = _safe_call(window, "handle", None)
    rectangle = _safe_call(window, "rectangle", None)

    candidate = {
        "title": title,
        "window_text": title,
        "class_name": class_name,
        "control_type": str(control_type) if control_type is not None else None,
        "process_id": process_id,
        "handle": int(handle) if handle is not None else None,
        "is_visible": bool(_safe_call(window, "is_visible", False)),
        "is_enabled": bool(_safe_call(window, "is_enabled", False)),
        "rectangle": _rect_payload(rectangle),
    }
    candidate["size"] = (
        {
            "width": candidate["rectangle"]["width"],
            "height": candidate["rectangle"]["height"],
        }
        if candidate["rectangle"]
        else None
    )
    return candidate


def list_candidate_windows(backend: str = "win32") -> list[dict[str, Any]]:
    """Enumerate top-level windows that can be considered WinWatt candidates."""

    from pywinauto import Desktop

    desktop = Desktop(backend=backend)
    candidates: list[dict[str, Any]] = []
    for window in desktop.windows(top_level_only=True):
        try:
            candidate = _candidate_from_window(window, backend=backend)
        except Exception:
            logger.exception("Skipping window during candidate discovery for backend={}", backend)
            continue
        text = (candidate.get("title") or "").lower()
        class_name = str(candidate.get("class_name") or "").lower()
        if "winwatt" in text and class_name == "tmainform":
            candidates.append(candidate)

    logger.debug("Discovered {} WinWatt-like windows on backend={}", len(candidates), backend)
    for candidate in candidates:
        logger.debug("Candidate[{}]: {}", backend, candidate)
    return candidates


def _selection_score(candidate: dict[str, Any]) -> tuple[int, int, int, int, int]:
    title = str(candidate.get("title") or "").lower()
    class_name = str(candidate.get("class_name") or "").lower()
    rect = candidate.get("rectangle") or {}
    area = int(rect.get("width", 0)) * int(rect.get("height", 0))
    title_has_winwatt = int("winwatt" in title)
    enabled = int(bool(candidate.get("is_enabled")))
    visible = int(bool(candidate.get("is_visible")))
    main_frame_hint = int(any(hint in class_name for hint in MAIN_FRAME_CLASS_HINTS))
    modal_penalty = int(any(hint in class_name for hint in MODAL_CLASS_HINTS) or area < 100_000)

    return (visible, enabled, title_has_winwatt, main_frame_hint - modal_penalty, area)


def select_main_window(candidates: list[dict[str, Any]], backend: str = "unknown") -> dict[str, Any]:
    """Select best main-window candidate using ranked heuristics."""

    if not candidates:
        raise WinWattNotRunningError("No WinWatt-like windows were found")

    candidates_with_process = [candidate for candidate in candidates if candidate.get("process_id") is not None]
    if not candidates_with_process:
        raise WinWattNotRunningError(f"No WinWatt-like windows with process_id were found on backend={backend}")

    ranked_pool = candidates_with_process

    scored = [(candidate, _selection_score(candidate)) for candidate in ranked_pool]
    scored.sort(key=lambda item: item[1], reverse=True)

    if len(scored) > 1 and scored[0][1] == scored[1][1]:
        raise WinWattMultipleWindowsError(
            "Multiple WinWatt windows matched with equal ranking",
            backend=backend,
            candidates=ranked_pool,
        )

    winner, winner_score = scored[0]
    for candidate, score in scored:
        logger.info("Candidate ranking score={} data={}", score, candidate)

    reasons = [
        f"has_process_id={winner.get('process_id') is not None}",
        f"has_handle={winner.get('handle') is not None}",
        f"visible={bool(winner.get('is_visible'))}",
        f"enabled={bool(winner.get('is_enabled'))}",
        f"title_has_winwatt={'winwatt' in str(winner.get('title') or '').lower()}",
        f"area={((winner.get('rectangle') or {}).get('width', 0)) * ((winner.get('rectangle') or {}).get('height', 0))}",
    ]
    logger.info(
        "Selected main window process_id={} handle={} score={} reasons={}",
        winner.get("process_id"),
        winner.get("handle"),
        winner_score,
        reasons,
    )

    return winner


def _resolve_main_window_candidate(backend: str = "win32") -> dict[str, Any]:
    candidates = list_candidate_windows(backend=backend)
    if not candidates:
        raise WinWattNotRunningError(f"No WinWatt-like windows found on backend={backend}")

    return select_main_window(candidates, backend=backend)


def _pywinauto_application_class() -> Any:
    """Return the ``pywinauto`` Application class across package layouts."""

    import pywinauto

    application_class = getattr(pywinauto, "Application", None)
    if application_class is not None:
        return application_class

    from pywinauto.application import Application

    return Application


def _connect_with_win32_handle() -> tuple[Any, dict[str, Any]]:
    Application = _pywinauto_application_class()

    candidates = list_candidate_windows(backend="win32")
    ranked_candidates = sorted(
        ((candidate, _selection_score(candidate)) for candidate in candidates if candidate.get("process_id") is not None),
        key=lambda item: item[1],
        reverse=True,
    )
    logger.info(
        "DBG_WINWATT_CONNECT_WIN32_CANDIDATES locator=backend=win32 ranked_candidates={} ",
        [
            {
                "rank": index + 1,
                "score": score,
                "process_id": candidate.get("process_id"),
                "handle": candidate.get("handle"),
                "class_name": candidate.get("class_name"),
                "title": candidate.get("title"),
                "visible": candidate.get("is_visible"),
                "enabled": candidate.get("is_enabled"),
            }
            for index, (candidate, score) in enumerate(ranked_candidates)
        ],
    )
    selected = select_main_window(candidates, backend="win32")
    logger.info(
        "DBG_WINWATT_CONNECT_WIN32_SELECTED selected_payload={} selected_handle_is_none={}",
        selected,
        selected.get("handle") is None,
    )
    process_id = selected.get("process_id")
    if process_id is None:
        raise WinWattNotRunningError("Selected WinWatt window has no process_id")

    handle = selected.get("handle")
    connector = Application(backend="win32")
    if handle is not None:
        try:
            app = connector.connect(handle=handle)
        except Exception as exc:
            logger.exception(
                "DBG_WINWATT_CONNECT_WIN32_EXCEPTION locator=handle:{} exception_class={} exception_message={}",
                handle,
                exc.__class__.__name__,
                exc,
            )
            raise
        logger.info(
            "Connected to WinWatt backend=win32 attach_mode=handle candidate={}",
            {
                "process_id": process_id,
                "handle": handle,
                "class_name": selected.get("class_name"),
                "title": selected.get("title"),
            },
        )
        return app, selected

    try:
        app = connector.connect(process=process_id)
    except Exception as exc:
        logger.exception(
            "DBG_WINWATT_CONNECT_WIN32_EXCEPTION locator=process:{} exception_class={} exception_message={}",
            process_id,
            exc.__class__.__name__,
            exc,
        )
        raise
    logger.info(
        "Connected to WinWatt backend=win32 attach_mode=process candidate={}",
        {
            "process_id": process_id,
            "handle": handle,
            "class_name": selected.get("class_name"),
            "title": selected.get("title"),
        },
    )

    selected_window = app.window(class_name="TMainForm", title_re=".*WinWatt.*")
    resolved_handle = _safe_call(selected_window, "handle", None)
    if resolved_handle is not None:
        selected["handle"] = int(resolved_handle)
    logger.info(
        "DBG_WINWATT_CONNECT_WIN32_RESOLVED process_id={} resolved_handle={} selected_payload={}",
        process_id,
        selected.get("handle"),
        selected,
    )
    return app, selected



def connect_to_winwatt() -> Any:
    """Attach to a running WinWatt application.

    Resolves the main window using ``win32`` and prefers process-based attachment.
    """

    try:
        app, _ = _connect_with_win32_handle()
        WinWattSession.app = app
        return app
    except Exception as win32_error:
        logger.error("Unable to connect to WinWatt: {}", win32_error)
        raise WinWattNotRunningError("WinWatt is not running or no eligible main window was found") from win32_error



def _resolve_uia_main_window() -> Any:
    """Resolve a fresh UIA main window wrapper and update cached session metadata."""

    Application = _pywinauto_application_class()

    _, selected = _connect_with_win32_handle()
    logger.info("DBG_WINWATT_RESOLVE_UIA_WIN32_SELECTED selected_payload={}", selected)
    process_id = selected.get("process_id")
    if process_id is None:
        raise WinWattNotRunningError("Selected WinWatt window has no process_id")

    app_uia = Application(backend="uia").connect(process=process_id)
    logger.info("Connected to WinWatt backend=uia process_id={}", process_id)

    logger.info(
        "Resolving main WinWatt window backend=uia class_name=TMainForm title_re=.*WinWatt.*",
    )

    try:
        main_window = app_uia.window(class_name="TMainForm", title_re=".*WinWatt.*")
        exists = getattr(main_window, "exists", None)
        if callable(exists) and not exists(timeout=1):
            raise WinWattNotRunningError("UIA main window lookup did not resolve an existing window")
        main_window = _materialize_window_wrapper(main_window)
        logger.info(
            "DBG_WINWATT_RESOLVE_UIA_PRIMARY selected_payload={} primary_result={} identity_match_with_win32={}",
            selected,
            _window_identity_payload(main_window),
            _wrapper_handle(main_window) == selected.get("handle") if selected.get("handle") is not None else None,
        )
        WinWattSession.app = app_uia
        WinWattSession.main_window = main_window
        WinWattSession.process_id = process_id
        WinWattSession.handle = _wrapper_handle(main_window)
        return main_window
    except Exception as exc:
        logger.exception(
            "DBG_WINWATT_RESOLVE_UIA_PRIMARY_EXCEPTION process_id={} reason={} exception_class={} exception_message={}",
            process_id,
            "primary_lookup_failed",
            exc.__class__.__name__,
            exc,
        )

    top_level_windows = app_uia.windows(top_level_only=True)
    candidates = [_candidate_from_window(window, backend="uia") for window in top_level_windows]
    logger.info("DBG_WINWATT_RESOLVE_UIA_FALLBACK_CANDIDATES candidates={}", candidates)

    def _uia_fallback_score(candidate: dict[str, Any]) -> tuple[int, int, int, int]:
        title = str(candidate.get("title") or "").lower()
        class_name = str(candidate.get("class_name") or "")
        rect = candidate.get("rectangle") or {}
        area = int(rect.get("width", 0)) * int(rect.get("height", 0))
        return (
            int("winwatt" in title),
            int(class_name == "TMainForm"),
            int(bool(candidate.get("is_visible"))),
            area,
        )

    ranked_candidates = sorted(candidates, key=_uia_fallback_score, reverse=True)
    if not ranked_candidates:
        raise WinWattNotRunningError("No UIA top-level windows available after process attach")

    best_candidate = ranked_candidates[0]
    best_handle = best_candidate.get("handle")
    logger.info(
        "DBG_WINWATT_RESOLVE_UIA_FALLBACK_SELECTED process_id={} selected_candidate={} win32_selected={} identity_match_with_win32={}",
        process_id,
        best_candidate,
        selected,
        best_handle == selected.get("handle") if best_handle is not None and selected.get("handle") is not None else None,
    )
    if best_handle is not None:
        main_window = app_uia.window(handle=best_handle)
    else:
        main_window = app_uia.window(title=best_candidate.get("title"), class_name=best_candidate.get("class_name"))
    main_window = _materialize_window_wrapper(main_window)

    WinWattSession.app = app_uia
    WinWattSession.main_window = main_window
    WinWattSession.process_id = process_id
    WinWattSession.handle = _wrapper_handle(main_window)
    return main_window


def _cached_window_health_status(main_window: Any) -> tuple[bool, str]:
    exists = getattr(main_window, "exists", None)
    if callable(exists):
        try:
            if not bool(exists(timeout=0.2)):
                logger.info("DBG_WINWATT_CACHE_HEALTH reason_code=exists_failed payload={}", _window_identity_payload(main_window))
                return False, "exists_failed"
        except Exception as exc:
            logger.info("DBG_WINWATT_CACHE_HEALTH reason_code=exists_failed payload={} exception_class={} exception_message={}", _window_identity_payload(main_window), exc.__class__.__name__, exc)
            return False, "exists_failed"

    cached_process_id = WinWattSession.process_id
    process_id = _safe_call(main_window, "process_id", None)
    if cached_process_id is not None and process_id is not None and int(process_id) != int(cached_process_id):
        logger.info("DBG_WINWATT_CACHE_HEALTH reason_code=pid_mismatch cached_process_id={} actual_process_id={} payload={}", cached_process_id, process_id, _window_identity_payload(main_window))
        return False, "pid_mismatch"

    cached_handle = WinWattSession.handle
    handle = _wrapper_handle(main_window)
    if cached_handle is not None and handle is not None and int(handle) != int(cached_handle):
        logger.info("DBG_WINWATT_CACHE_HEALTH reason_code=handle_mismatch cached_handle={} actual_handle={} payload={}", cached_handle, handle, _window_identity_payload(main_window))
        return False, "handle_mismatch"

    if not is_winwatt_foreground_context(main_window, allow_dialog=True):
        logger.info("DBG_WINWATT_CACHE_HEALTH reason_code=foreground_context_failed payload={} foreground={}", _window_identity_payload(main_window), describe_foreground_window())
        return False, "foreground_context_failed"

    logger.info("DBG_WINWATT_CACHE_HEALTH reason_code=healthy payload={}", _window_identity_payload(main_window))
    return True, "healthy"


def _register_cached_window_health_result(*, reason_code: str, now: float) -> None:
    if reason_code == "foreground_context_failed":
        if now - MainWindowSession.last_foreground_failure_monotonic > MainWindowSession.foreground_resolve_throttle_window_s:
            MainWindowSession.foreground_failure_count = 0
        MainWindowSession.foreground_failure_count += 1
        MainWindowSession.last_foreground_failure_monotonic = now
        return

    MainWindowSession.foreground_failure_count = 0
    MainWindowSession.last_foreground_failure_monotonic = 0.0


def _foreground_resolve_is_throttled(now: float) -> bool:
    if MainWindowSession.foreground_failure_count < MainWindowSession.foreground_resolve_attempt_limit:
        return False
    last_attempt = MainWindowSession.last_resolve_attempt_monotonic
    if last_attempt <= 0:
        return False
    return now - last_attempt < MainWindowSession.foreground_resolve_throttle_window_s




CACHE_LOG_STATS = {
    "reason_counts": Counter(),
    "last_validation_age_s": [],
    "throttle_count": 0,
}


def _record_cache_log(reason_code: str, *, last_validation_age_s: float | None = None) -> None:
    CACHE_LOG_STATS["reason_counts"][reason_code] += 1
    if last_validation_age_s is not None:
        CACHE_LOG_STATS["last_validation_age_s"].append(round(float(last_validation_age_s), 3))
    if reason_code == "cache_resolve_throttled":
        CACHE_LOG_STATS["throttle_count"] += 1


def log_cache_usage_summary() -> None:
    reason_counts = dict(sorted(CACHE_LOG_STATS["reason_counts"].items()))
    ages = CACHE_LOG_STATS["last_validation_age_s"]
    age_summary = {
        "count": len(ages),
        "min_s": min(ages) if ages else None,
        "max_s": max(ages) if ages else None,
    }
    logger.info(
        "CACHE_USAGE_SUMMARY reasons={} validation_age_summary={} throttled_resolves={} ",
        reason_counts,
        age_summary,
        CACHE_LOG_STATS["throttle_count"],
    )

def get_cached_main_window() -> Any:
    """Return cached WinWatt main window wrapper, reconnecting only when unhealthy."""

    started_at = time.monotonic()
    options = diagnostic_options()
    validation_interval_s = MainWindowSession.validation_interval_s
    if options.minimize_cache_validation:
        validation_interval_s = max(validation_interval_s, 30.0)

    cached_main_window = WinWattSession.main_window
    if cached_main_window is not None:
        cached_main_window = _materialize_window_wrapper(cached_main_window)
        WinWattSession.main_window = cached_main_window
        now = time.monotonic()
        MainWindowSession.window = cached_main_window
        MainWindowSession.process_id = WinWattSession.process_id
        if now - MainWindowSession.last_validation_monotonic < validation_interval_s:
            cache_age_s = now - MainWindowSession.last_validation_monotonic
            _record_cache_log("cache_reused_without_validation", last_validation_age_s=cache_age_s)
            logger.debug("DBG_WINWATT_CACHE_GET reason_code=cache_reused_without_validation payload={} last_validation_age_s={} diagnostic_fast_mode={}", _window_identity_payload(cached_main_window), cache_age_s, options.diagnostic_fast_mode)
            logger.debug("DBG_PHASE_TIMING phase=get_cached_main_window elapsed_ms={:.3f} reason_code=cache_reused_without_validation", (time.monotonic() - started_at) * 1000.0)
            return cached_main_window
        age_s = now - MainWindowSession.last_validation_monotonic
        is_healthy, reason_code = _cached_window_health_status(cached_main_window)
        _register_cached_window_health_result(reason_code=reason_code, now=now)
        if is_healthy:
            MainWindowSession.last_validation_monotonic = now
            _record_cache_log("cache_validated_ok", last_validation_age_s=age_s)
            logger.debug("DBG_WINWATT_CACHE_GET reason_code=cache_validated_ok payload={} last_validation_age_s={} diagnostic_fast_mode={}", _window_identity_payload(cached_main_window), age_s, options.diagnostic_fast_mode)
            logger.debug("DBG_PHASE_TIMING phase=get_cached_main_window elapsed_ms={:.3f} reason_code=cache_validated_ok", (time.monotonic() - started_at) * 1000.0)
            return cached_main_window
        if reason_code == "foreground_context_failed" and _foreground_resolve_is_throttled(now):
            elapsed_since_last_resolve_s = now - MainWindowSession.last_resolve_attempt_monotonic
            logger.info(
                "DBG_WINWATT_CACHE_RESOLVE_THROTTLED reason_code={} failure_count={} throttle_window_s={} elapsed_since_last_resolve_s={} payload={} foreground={}",
                reason_code,
                MainWindowSession.foreground_failure_count,
                MainWindowSession.foreground_resolve_throttle_window_s,
                elapsed_since_last_resolve_s,
                _window_identity_payload(cached_main_window),
                describe_foreground_window(),
            )
            MainWindowSession.last_validation_monotonic = now
            _record_cache_log("cache_resolve_throttled")
            logger.debug("DBG_PHASE_TIMING phase=get_cached_main_window elapsed_ms={:.3f} reason_code=cache_resolve_throttled", (time.monotonic() - started_at) * 1000.0)
            return cached_main_window
        MainWindowSession.last_resolve_attempt_monotonic = now
        _record_cache_log("cache_invalid_resolving_fresh")
        logger.info("DBG_WINWATT_CACHE_GET reason_code=cache_invalid_resolving_fresh payload={} health_reason={} diagnostic_fast_mode={}", _window_identity_payload(cached_main_window), reason_code, options.diagnostic_fast_mode)
    else:
        _record_cache_log("cache_missing_resolving_fresh")
        logger.info("DBG_WINWATT_CACHE_GET reason_code=cache_missing_resolving_fresh diagnostic_fast_mode={}", options.diagnostic_fast_mode)

    resolved = _resolve_uia_main_window()
    MainWindowSession.window = resolved
    MainWindowSession.process_id = WinWattSession.process_id
    MainWindowSession.last_validation_monotonic = time.monotonic()
    MainWindowSession.foreground_failure_count = 0
    MainWindowSession.last_foreground_failure_monotonic = 0.0
    _record_cache_log("fresh_resolve")
    logger.debug("DBG_PHASE_TIMING phase=get_cached_main_window elapsed_ms={:.3f} reason_code=fresh_resolve", (time.monotonic() - started_at) * 1000.0)
    return resolved




def get_cached_main_window_snapshot() -> Any:
    """Return the current cached main-window wrapper without forcing health validation."""

    cached_main_window = WinWattSession.main_window or MainWindowSession.window
    if cached_main_window is None:
        return get_cached_main_window()

    cached_main_window = _materialize_window_wrapper(cached_main_window)
    WinWattSession.main_window = cached_main_window
    MainWindowSession.window = cached_main_window
    logger.info(
        "DBG_WINWATT_CACHE_SNAPSHOT reason_code=cache_snapshot_reused payload={}",
        _window_identity_payload(cached_main_window),
    )
    return cached_main_window


def get_main_window() -> Any:
    """Backward-compatible wrapper around cached main window access."""

    return get_cached_main_window()




def _materialize_window_wrapper(window: Any) -> Any:
    if window is None:
        return None
    wrapper_object = getattr(window, "wrapper_object", None)
    if callable(wrapper_object):
        try:
            materialized = wrapper_object()
            if materialized is not None:
                return materialized
        except Exception as exc:
            logger.warning(
                "DBG_WINWATT_WINDOW_MATERIALIZE_FAILED wrapper_type={} exception_class={} exception_message={}",
                type(window).__name__,
                exc.__class__.__name__,
                exc,
            )
    return window


def _best_effort_focus_window(window: Any, *, maximize: bool = False) -> None:
    restore = getattr(window, "restore", None)
    if callable(restore):
        try:
            restore()
        except Exception:
            pass

    set_focus = getattr(window, "set_focus", None)
    if callable(set_focus):
        try:
            set_focus()
        except Exception:
            pass

    set_keyboard_focus = getattr(window, "set_keyboard_focus", None)
    if callable(set_keyboard_focus):
        try:
            set_keyboard_focus()
        except Exception:
            pass

    if maximize:
        maximize_fn = getattr(window, "maximize", None)
        if callable(maximize_fn):
            try:
                maximize_fn()
            except Exception:
                pass


def _wrapper_handle(wrapper: Any) -> int | None:
    handle = _safe_call(wrapper, "handle", None)
    if handle is not None:
        return int(handle)
    element_info = _safe_getattr(wrapper, "element_info", None)
    if element_info is None:
        return None
    info_handle = _safe_getattr(element_info, "handle", None)
    return int(info_handle) if info_handle is not None else None


def _window_identity_payload(window: Any) -> dict[str, Any]:
    """Return best-effort identity payload for a wrapper."""

    element_info = _safe_getattr(window, "element_info", None)
    title = _safe_call(window, "window_text", "") or ""
    class_name = _safe_call(window, "class_name", None)
    if class_name in (None, ""):
        class_name = _safe_getattr(element_info, "class_name", None) or ""
    process_id = _safe_call(window, "process_id", None)
    handle = _wrapper_handle(window)
    wrapper_type = type(window).__name__ if window is not None else None
    control_type = _safe_getattr(element_info, "control_type", None)
    return {
        "wrapper_type": wrapper_type,
        "handle": int(handle) if handle is not None else None,
        "process_id": int(process_id) if process_id is not None else None,
        "title": title,
        "class_name": class_name,
        "control_type": str(control_type) if control_type is not None else None,
    }


def _foreground_context_alignment(expected: dict[str, Any], actual: dict[str, Any], *, allow_dialog: bool) -> tuple[str, bool]:
    expected_handle = expected.get("handle")
    actual_handle = actual.get("handle")
    expected_pid = expected.get("process_id")
    actual_pid = actual.get("process_id")
    if expected_handle is not None and actual_handle == expected_handle:
        return "handle_match", True
    if allow_dialog and expected_pid is not None and actual_pid == expected_pid:
        return "pid_match_allow_dialog", True
    return "no_match", False


def _is_probationary_focus_action(action_label: str) -> bool:
    normalized = (action_label or "").strip().lower()
    return normalized == "open_system_menu" or normalized.startswith("baseline_restore:")


def _is_normal_top_menu_click_focus_action(action_label: str) -> bool:
    normalized = (action_label or "").strip().lower()
    return normalized.startswith("click_top_menu_item:")


def _is_open_top_menu_focus_action(action_label: str) -> bool:
    normalized = (action_label or "").strip().lower()
    return normalized.startswith("open_top_menu:")


def _is_relative_menu_click_focus_action(action_label: str) -> bool:
    normalized = (action_label or "").strip().lower()
    return normalized == "relative_menu_click"


def _is_single_row_probe_click_focus_action(action_label: str) -> bool:
    normalized = (action_label or "").strip().lower()
    return normalized.startswith("single_row_probe_click[")


def _rects_meaningfully_match(left: dict[str, int] | None, right: dict[str, int] | None, *, tolerance: int = 20) -> bool:
    if left is None or right is None:
        return False
    keys = ("left", "top", "right", "bottom", "width", "height")
    try:
        return all(abs(int(left.get(key, 0)) - int(right.get(key, 0))) <= tolerance for key in keys)
    except Exception:
        return False


def _should_allow_stale_wrapper_refresh(action_label: str, *, allow_stale_wrapper_refresh: bool) -> bool:
    normalized = (action_label or "").strip().lower()
    return allow_stale_wrapper_refresh and normalized in {
        "open_project_accelerator_smoke",
        "open_project_file_via_dialog",
    }


def _refresh_stale_main_window_if_identity_matches(
    *,
    action_label: str,
    cached_identity: dict[str, Any],
    cached_rect_payload: dict[str, int] | None,
    visible: bool,
    enabled: bool,
    allow_stale_wrapper_refresh: bool,
) -> tuple[Any | None, dict[str, Any]]:
    diagnostic: dict[str, Any] = {
        "action_label": action_label,
        "cached_identity": cached_identity,
        "cached_rect": cached_rect_payload,
        "visible": visible,
        "enabled": enabled,
        "refresh_attempted": False,
        "refresh_permitted": _should_allow_stale_wrapper_refresh(action_label, allow_stale_wrapper_refresh=allow_stale_wrapper_refresh),
    }
    if not diagnostic["refresh_permitted"]:
        diagnostic["reason"] = "refresh_not_permitted"
        return None, diagnostic
    if not visible or not enabled:
        diagnostic["reason"] = "cached_window_not_ready"
        return None, diagnostic

    diagnostic["refresh_attempted"] = True
    refreshed_window = _resolve_uia_main_window()
    refreshed_identity = _window_identity_payload(refreshed_window)
    refreshed_rect = _rect_payload(_safe_call(refreshed_window, "rectangle", None))
    refreshed_exists = bool(_safe_call(refreshed_window, "exists", False))
    refreshed_visible = bool(_safe_call(refreshed_window, "is_visible", False))
    refreshed_enabled = bool(_safe_call(refreshed_window, "is_enabled", False))
    diagnostic.update({
        "refreshed_identity": refreshed_identity,
        "refreshed_rect": refreshed_rect,
        "refreshed_exists": refreshed_exists,
        "refreshed_visible": refreshed_visible,
        "refreshed_enabled": refreshed_enabled,
    })

    identity_match = (
        cached_identity.get("process_id") is not None
        and cached_identity.get("process_id") == refreshed_identity.get("process_id")
        and cached_identity.get("title") == refreshed_identity.get("title")
        and cached_identity.get("class_name") == refreshed_identity.get("class_name")
        and _rects_meaningfully_match(cached_rect_payload, refreshed_rect)
    )
    diagnostic["identity_match"] = identity_match
    foreground = describe_foreground_window()
    foreground_reason, foreground_match = _foreground_context_alignment(refreshed_identity, foreground, allow_dialog=False)
    diagnostic["foreground"] = foreground
    diagnostic["foreground_match"] = foreground_match
    diagnostic["foreground_reason"] = foreground_reason
    relaxed_pass = bool(identity_match and refreshed_visible and refreshed_enabled and foreground_match)
    diagnostic["focus_guard_relaxed_pass"] = relaxed_pass
    if refreshed_exists and refreshed_visible and refreshed_enabled and identity_match:
        diagnostic["relaxed_pass_reason"] = None
        diagnostic["reason"] = "stale_wrapper_refreshed"
        WinWattSession.main_window = refreshed_window
        MainWindowSession.window = refreshed_window
        MainWindowSession.process_id = refreshed_identity.get("process_id")
        return refreshed_window, diagnostic
    if relaxed_pass:
        diagnostic["relaxed_pass_reason"] = "identity_foreground_visible_enabled_match"
        diagnostic["reason"] = "stale_wrapper_relaxed_foreground_identity_pass"
        WinWattSession.main_window = refreshed_window
        MainWindowSession.window = refreshed_window
        MainWindowSession.process_id = refreshed_identity.get("process_id")
        return refreshed_window, diagnostic

    diagnostic["relaxed_pass_reason"] = None
    diagnostic["reason"] = "refresh_identity_mismatch" if not identity_match else "refresh_not_ready"
    return None, diagnostic


def _has_probationary_main_window_identity(identity: dict[str, Any], rect_payload: dict[str, int] | None, *, visible: bool, enabled: bool) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if identity.get("handle") is not None:
        reasons.append("handle")
    if identity.get("process_id") is not None:
        reasons.append("process_id")
    if identity.get("title"):
        reasons.append("title")
    if identity.get("class_name"):
        reasons.append("class_name")
    if rect_payload is not None and rect_payload.get("width", 0) > 0 and rect_payload.get("height", 0) > 0:
        reasons.append("rect")
    if visible:
        reasons.append("visible")
    if enabled:
        reasons.append("enabled")

    strong_identity = (
        visible
        and enabled
        and rect_payload is not None
        and rect_payload.get("width", 0) > 0
        and rect_payload.get("height", 0) > 0
        and any(identity.get(key) is not None for key in ("handle", "process_id"))
        and bool(identity.get("title") or identity.get("class_name"))
    )
    return strong_identity, reasons


def focus_main_window() -> Any:
    """Bring WinWatt main window to the foreground and focus it."""

    main_window = get_cached_main_window()
    logger.info("focus_main_window: resolved WinWatt main window handle={}", _wrapper_handle(main_window))

    set_focus = getattr(main_window, "set_focus", None)
    if callable(set_focus):
        try:
            set_focus()
            logger.info("focus_main_window: set_focus() succeeded")
        except Exception as exc:
            logger.warning("focus_main_window: set_focus() failed: {}", exc)
    else:
        logger.info("focus_main_window: set_focus() unavailable")

    set_keyboard_focus = getattr(main_window, "set_keyboard_focus", None)
    if callable(set_keyboard_focus):
        try:
            set_keyboard_focus()
            logger.info("focus_main_window: set_keyboard_focus() succeeded")
        except Exception as exc:
            logger.warning("focus_main_window: set_keyboard_focus() failed: {}", exc)
    else:
        logger.info("focus_main_window: set_keyboard_focus() unavailable")

    is_minimized = getattr(main_window, "is_minimized", None)
    minimized = False
    if callable(is_minimized):
        try:
            minimized = bool(is_minimized())
        except Exception as exc:
            logger.warning("focus_main_window: is_minimized() failed: {}", exc)
    logger.info("focus_main_window: minimized={}", minimized)

    if minimized:
        restore = getattr(main_window, "restore", None)
        if callable(restore):
            try:
                restore()
                logger.info("focus_main_window: restore() succeeded")
            except Exception as exc:
                logger.warning("focus_main_window: restore() failed: {}", exc)
        else:
            logger.info("focus_main_window: restore() unavailable")

    is_maximized = getattr(main_window, "is_maximized", None)
    maximized = False
    if callable(is_maximized):
        try:
            maximized = bool(is_maximized())
        except Exception as exc:
            logger.warning("focus_main_window: is_maximized() failed: {}", exc)
    logger.info("focus_main_window: maximized={}", maximized)

    if not minimized and not maximized:
        maximize = getattr(main_window, "maximize", None)
        if callable(maximize):
            try:
                maximize()
                logger.info("focus_main_window: maximize() succeeded")
            except Exception as exc:
                logger.warning("focus_main_window: maximize() failed: {}", exc)
        else:
            logger.info("focus_main_window: maximize() unavailable")
    else:
        logger.info("focus_main_window: maximize() skipped")

    if callable(set_focus):
        try:
            set_focus()
            logger.info("focus_main_window: final set_focus() succeeded")
        except Exception as exc:
            logger.warning("focus_main_window: final set_focus() failed: {}", exc)

    return main_window




def prepare_main_window_for_menu_interaction() -> Any:
    """Normalize WinWatt window geometry/focus before menu clicks."""

    logger.info("Preparing WinWatt window for menu interaction")
    main_window = get_cached_main_window()

    minimized = False
    is_minimized = getattr(main_window, "is_minimized", None)
    if callable(is_minimized):
        try:
            minimized = bool(is_minimized())
        except Exception as exc:
            logger.warning("prepare_main_window_for_menu_interaction: is_minimized() failed: {}", exc)

    maximized = False
    is_maximized = getattr(main_window, "is_maximized", None)
    if callable(is_maximized):
        try:
            maximized = bool(is_maximized())
        except Exception as exc:
            logger.warning("prepare_main_window_for_menu_interaction: is_maximized() failed: {}", exc)

    state = "minimized" if minimized else ("maximized" if maximized else "normal")
    logger.info("Window state before: {}", state)

    if minimized:
        restore = getattr(main_window, "restore", None)
        if callable(restore):
            try:
                restore()
            except Exception as exc:
                logger.warning("prepare_main_window_for_menu_interaction: restore() failed: {}", exc)

    set_focus = getattr(main_window, "set_focus", None)
    if callable(set_focus):
        try:
            set_focus()
        except Exception as exc:
            logger.warning("prepare_main_window_for_menu_interaction: initial set_focus() failed: {}", exc)

    maximize = getattr(main_window, "maximize", None)
    if callable(maximize):
        try:
            maximize()
            logger.info("Window maximized")
        except Exception as exc:
            logger.warning("prepare_main_window_for_menu_interaction: maximize() failed: {}", exc)
    else:
        logger.warning("prepare_main_window_for_menu_interaction: maximize() unavailable")

    if callable(set_focus):
        try:
            set_focus()
            logger.info("Focus confirmed")
        except Exception as exc:
            logger.warning("prepare_main_window_for_menu_interaction: final set_focus() failed: {}", exc)

    wait_for_main_window_ready(
        main_window,
        timeout=WINDOW_READY_TIMEOUT,
        poll_interval=WINDOW_READY_POLL_INTERVAL,
    )

    return main_window


def wait_for_main_window_ready(
    main_window: Any,
    *,
    timeout: float = WINDOW_READY_TIMEOUT,
    poll_interval: float = WINDOW_READY_POLL_INTERVAL,
) -> bool:
    """Wait briefly until the main window becomes interactable."""

    deadline = time.monotonic() + max(timeout, poll_interval)
    while time.monotonic() <= deadline:
        visible = bool(_safe_call(main_window, "is_visible", False))
        enabled = bool(_safe_call(main_window, "is_enabled", False))
        if visible and enabled:
            return True
        time.sleep(poll_interval)
    return False

def is_main_window_foreground() -> bool:
    """Return whether WinWatt main window is currently the OS foreground window."""

    main_window = get_cached_main_window()
    main_handle = _wrapper_handle(main_window)
    if main_handle is None:
        logger.warning("is_main_window_foreground: main window has no handle")
        return False

    try:
        foreground_handle = int(ctypes.windll.user32.GetForegroundWindow())
    except Exception as exc:
        logger.warning("is_main_window_foreground: GetForegroundWindow() failed: {}", exc)
        return False

    main_title = _safe_call(main_window, "window_text", "") or ""
    main_class = _safe_call(main_window, "class_name", "") or ""

    foreground_title = ""
    foreground_class = ""
    try:
        from pywinauto import Desktop

        foreground_wrapper = Desktop(backend="win32").window(handle=foreground_handle)
        foreground_title = _safe_call(foreground_wrapper, "window_text", "") or ""
        foreground_class = _safe_call(foreground_wrapper, "class_name", "") or ""
    except Exception as exc:
        logger.warning("is_main_window_foreground: failed to inspect foreground window details: {}", exc)

    is_foreground = foreground_handle == main_handle
    logger.info(
        "is_main_window_foreground: main_handle={} foreground_handle={} is_foreground={} main_title='{}' foreground_title='{}' main_class='{}' foreground_class='{}'",
        main_handle,
        foreground_handle,
        is_foreground,
        main_title,
        foreground_title,
        main_class,
        foreground_class,
    )
    return is_foreground


def describe_foreground_window() -> dict[str, Any]:
    """Return diagnostic metadata about the current foreground window."""

    try:
        foreground_handle = int(ctypes.windll.user32.GetForegroundWindow())
    except Exception as exc:
        logger.warning("describe_foreground_window: GetForegroundWindow() failed: {}", exc)
        return {"handle": None, "title": "", "class_name": "", "process_id": None}

    try:
        from pywinauto import Desktop

        foreground_wrapper = Desktop(backend="win32").window(handle=foreground_handle)
        return {
            "handle": foreground_handle,
            "title": _safe_call(foreground_wrapper, "window_text", "") or "",
            "class_name": _safe_call(foreground_wrapper, "class_name", "") or "",
            "process_id": _safe_call(foreground_wrapper, "process_id", None),
        }
    except Exception as exc:
        logger.warning("describe_foreground_window: failed to inspect foreground details: {}", exc)
        return {"handle": foreground_handle, "title": "", "class_name": "", "process_id": None}


def is_winwatt_foreground_context(main_window: Any, *, allow_dialog: bool = True) -> bool:
    """Validate whether foreground belongs to WinWatt main window or its own dialogs."""

    expected = _window_identity_payload(main_window)
    actual = describe_foreground_window()
    result_reason, is_match = _foreground_context_alignment(expected, actual, allow_dialog=allow_dialog)
    logger.info(
        "DBG_WINWATT_FOREGROUND_CONTEXT expected_handle={} expected_process_id={} expected_title={} expected_class_name={} actual_foreground_handle={} actual_foreground_process_id={} actual_foreground_title={} actual_foreground_class_name={} allow_dialog={} result_reason={}",
        expected.get("handle"),
        expected.get("process_id"),
        expected.get("title"),
        expected.get("class_name"),
        actual.get("handle"),
        actual.get("process_id"),
        actual.get("title"),
        actual.get("class_name"),
        allow_dialog,
        result_reason,
    )
    return is_match


def ensure_main_window_foreground_before_click(
    *,
    action_label: str,
    timeout: float = 2.0,
    poll_interval: float = 0.1,
    allow_dialog: bool = False,
    allow_stale_wrapper_refresh: bool = False,
) -> Any:
    """Ensure main window is valid and foreground before click operations."""

    MainWindowSession.last_focus_guard_diagnostic = {
        "action_label": action_label,
        "cached_identity": None,
        "refreshed_identity": None,
        "focus_guard_relaxed_pass": False,
        "relaxed_pass_reason": None,
        "identity_match": None,
        "refreshed_exists": None,
        "refreshed_visible": None,
        "refreshed_enabled": None,
    }

    main_window = get_cached_main_window()
    exists = bool(_safe_call(main_window, "exists", False))
    visible = bool(_safe_call(main_window, "is_visible", False))
    enabled = bool(_safe_call(main_window, "is_enabled", False))
    rect_payload = _rect_payload(_safe_call(main_window, "rectangle", None))
    identity = _window_identity_payload(main_window)
    probationary_allowed = _is_probationary_focus_action(action_label)
    top_menu_click_override = _is_normal_top_menu_click_focus_action(action_label)
    open_top_menu_override = _is_open_top_menu_focus_action(action_label)
    relative_menu_click_override = _is_relative_menu_click_focus_action(action_label)
    single_row_probe_click_override = _is_single_row_probe_click_focus_action(action_label)
    strong_identity, identity_reasons = _has_probationary_main_window_identity(
        identity,
        rect_payload,
        visible=visible,
        enabled=enabled,
    )
    logger.info(
        "DBG_WINWATT_FOCUS_GUARD_PRECHECK action_label={} wrapper_type={} cached_handle={} cached_pid={} cached_title={} cached_class={} precheck_exists={} precheck_visible={} precheck_enabled={} rect={}",
        action_label,
        identity.get("wrapper_type"),
        identity.get("handle"),
        identity.get("process_id"),
        identity.get("title"),
        identity.get("class_name"),
        exists,
        visible,
        enabled,
        rect_payload,
    )
    if not exists:
        refreshed_window, refresh_diagnostic = _refresh_stale_main_window_if_identity_matches(
            action_label=action_label,
            cached_identity=identity,
            cached_rect_payload=rect_payload,
            visible=visible,
            enabled=enabled,
            allow_stale_wrapper_refresh=allow_stale_wrapper_refresh,
        )
        MainWindowSession.last_focus_guard_diagnostic = {
            "action_label": action_label,
            "cached_identity": refresh_diagnostic.get("cached_identity"),
            "refreshed_identity": refresh_diagnostic.get("refreshed_identity"),
            "focus_guard_relaxed_pass": bool(refresh_diagnostic.get("focus_guard_relaxed_pass")),
            "relaxed_pass_reason": refresh_diagnostic.get("relaxed_pass_reason"),
            "identity_match": refresh_diagnostic.get("identity_match"),
            "refreshed_exists": refresh_diagnostic.get("refreshed_exists"),
            "refreshed_visible": refresh_diagnostic.get("refreshed_visible"),
            "refreshed_enabled": refresh_diagnostic.get("refreshed_enabled"),
            "foreground": refresh_diagnostic.get("foreground"),
            "foreground_reason": refresh_diagnostic.get("foreground_reason"),
            "foreground_match": refresh_diagnostic.get("foreground_match"),
        }
        if refreshed_window is not None:
            logger.warning(
                "DBG_WINWATT_FOCUS_GUARD_STALE_REFRESH_CONTINUE action_label={} reason={} relaxed_pass={} relaxed_pass_reason={} cached_identity={} refreshed_identity={} cached_rect={} refreshed_rect={} foreground={}",
                action_label,
                refresh_diagnostic.get("reason"),
                refresh_diagnostic.get("focus_guard_relaxed_pass"),
                refresh_diagnostic.get("relaxed_pass_reason"),
                identity,
                refresh_diagnostic.get("refreshed_identity"),
                rect_payload,
                refresh_diagnostic.get("refreshed_rect"),
                refresh_diagnostic.get("foreground"),
            )
            main_window = refreshed_window
            exists = bool(_safe_call(main_window, "exists", False))
            visible = bool(_safe_call(main_window, "is_visible", False))
            enabled = bool(_safe_call(main_window, "is_enabled", False))
            rect_payload = _rect_payload(_safe_call(main_window, "rectangle", None))
            identity = _window_identity_payload(main_window)
            strong_identity, identity_reasons = _has_probationary_main_window_identity(
                identity,
                rect_payload,
                visible=visible,
                enabled=enabled,
            )
        elif probationary_allowed and strong_identity:
            logger.warning(
                "DBG_WINWATT_FOCUS_GUARD_SOFT_CONTINUE action_label={} reason=exists_false_but_identity_strong wrapper_type={} identity_reasons={} cached_identity={} rect={}",
                action_label,
                identity.get("wrapper_type"),
                identity_reasons,
                identity,
                rect_payload,
            )
        elif single_row_probe_click_override and strong_identity:
            logger.warning(
                "DBG_WINWATT_FOCUS_GUARD_PROBE_CLICK_SOFT_CONTINUE action_label={} reason=exists_false_but_identity_strong wrapper_type={} identity_reasons={} cached_identity={} rect={}",
                action_label,
                identity.get("wrapper_type"),
                identity_reasons,
                identity,
                rect_payload,
            )
        elif open_top_menu_override and strong_identity:
            logger.warning(
                "DBG_WINWATT_FOCUS_GUARD_OPEN_TOP_MENU_OVERRIDE action_label={} reason=exists_false_but_identity_strong wrapper_type={} identity_reasons={} cached_identity={} rect={}",
                action_label,
                identity.get("wrapper_type"),
                identity_reasons,
                identity,
                rect_payload,
            )
        elif (top_menu_click_override or relative_menu_click_override) and strong_identity:
            logger.warning(
                "DBG_WINWATT_FOCUS_GUARD_CLICK_OVERRIDE action_label={} reason=exists_false_but_identity_strong wrapper_type={} identity_reasons={} cached_identity={} rect={}",
                action_label,
                identity.get("wrapper_type"),
                identity_reasons,
                identity,
                rect_payload,
            )
        else:
            if single_row_probe_click_override:
                logger.error(
                    "DBG_WINWATT_FOCUS_GUARD_PROBE_CLICK_HARD_FAIL action_label={} reason=exists_false identity_reasons={} cached_identity={} rect={} refresh_diagnostic={}",
                    action_label,
                    identity_reasons,
                    identity,
                    rect_payload,
                    refresh_diagnostic,
                )
            logger.error(
                "DBG_WINWATT_FOCUS_GUARD_HARD_FAIL action_label={} reason=exists_false identity_reasons={} cached_identity={} rect={} refresh_diagnostic={}",
                action_label,
                identity_reasons,
                identity,
                rect_payload,
                refresh_diagnostic,
            )
            raise FocusGuardError(
                f"focus_not_restored: main window no longer exists before action={action_label}",
                diagnostic={
                    "action_label": action_label,
                    "reason": "exists_false",
                    "cached_identity": identity,
                    "cached_rect": rect_payload,
                    "identity_reasons": identity_reasons,
                    "refresh_diagnostic": refresh_diagnostic,
                },
            )
    if not visible or not enabled:
        logger.error(
            "DBG_WINWATT_FOCUS_GUARD_HARD_FAIL action_label={} reason=window_not_ready precheck_visible={} precheck_enabled={} cached_identity={} rect={}",
            action_label,
            visible,
            enabled,
            identity,
            rect_payload,
        )
        raise FocusGuardError(
            f"focus_not_restored: main window not ready before action={action_label} visible={visible} enabled={enabled}",
            diagnostic={
                "action_label": action_label,
                "reason": "window_not_ready",
                "cached_identity": identity,
                "cached_rect": rect_payload,
                "precheck_visible": visible,
                "precheck_enabled": enabled,
            },
        )

    deadline = time.time() + max(timeout, poll_interval)
    while time.time() < deadline:
        if is_winwatt_foreground_context(main_window, allow_dialog=allow_dialog):
            fg = describe_foreground_window()
            context_reason, same_context = _foreground_context_alignment(identity, fg, allow_dialog=allow_dialog)
            logger.info(
                "DBG_WINWATT_FOCUS_GUARD_RESULT action_label={} status=focus_ok reason={} foreground={} same_context_as_cached_main={} win32_uia_identity_match={}",
                action_label,
                context_reason,
                fg,
                same_context,
                fg.get("handle") == identity.get("handle") if fg.get("handle") is not None and identity.get("handle") is not None else None,
            )
            return main_window

        logger.info(
            "DBG_WINWATT_FOCUS_GUARD_REFOCUS_ATTEMPT action_label={} exists={} probationary_allowed={} strong_identity={} identity_reasons={}",
            action_label,
            exists,
            probationary_allowed,
            strong_identity,
            identity_reasons,
        )
        set_focus = getattr(main_window, "set_focus", None)
        if callable(set_focus):
            try:
                set_focus()
            except Exception as exc:
                logger.warning("focus_guard set_focus failed action={} error={}", action_label, exc)
        set_keyboard_focus = getattr(main_window, "set_keyboard_focus", None)
        if callable(set_keyboard_focus):
            try:
                set_keyboard_focus()
            except Exception:
                pass
        restore = getattr(main_window, "restore", None)
        if callable(restore):
            try:
                restore()
            except Exception:
                pass
        time.sleep(poll_interval)

    fg = describe_foreground_window()
    context_reason, same_context = _foreground_context_alignment(identity, fg, allow_dialog=allow_dialog)
    logger.error(
        "DBG_WINWATT_FOCUS_GUARD_RESULT action_label={} status=focus_failed reason={} foreground={} same_context_as_cached_main={} win32_uia_identity_match={} probationary_allowed={} strong_identity={}",
        action_label,
        context_reason,
        fg,
        same_context,
        fg.get("handle") == identity.get("handle") if fg.get("handle") is not None and identity.get("handle") is not None else None,
        probationary_allowed,
        strong_identity,
    )
    raise RuntimeError(
        "focus_not_restored: could not bring WinWatt to foreground "
        f"for action={action_label} foreground_title={fg.get('title')} foreground_class={fg.get('class_name')}"
    )
