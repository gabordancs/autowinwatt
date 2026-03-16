"""Wait helpers for resolving WinWatt windows/dialogs."""

from __future__ import annotations

import time
from typing import Any

from loguru import logger
from winwatt_automation.live_ui.app_connector import get_cached_main_window



def _window_handle(window: Any) -> int | None:
    handle = getattr(window, "handle", None)
    if callable(handle):
        try:
            handle = handle()
        except Exception:
            return None
    try:
        return int(handle) if handle is not None else None
    except Exception:
        return None


def _window_text(window: Any) -> str:
    text = getattr(window, "window_text", None)
    if callable(text):
        try:
            return (text() or "").strip()
        except Exception:
            return ""
    return ""




def _window_class_name(window: Any) -> str:
    class_name = getattr(window, "class_name", None)
    if callable(class_name):
        try:
            return (class_name() or "").strip()
        except Exception:
            return ""
    return ""


def _safe_process_id(window: Any) -> int | None:
    process_id = getattr(window, "process_id", None)
    if not callable(process_id):
        return None
    try:
        return int(process_id())
    except Exception:
        return None


def _safe_is_visible(window: Any) -> bool:
    is_visible = getattr(window, "is_visible", None)
    if not callable(is_visible):
        return False
    try:
        return bool(is_visible())
    except Exception:
        return False


def _dialog_candidate_snapshot(window: Any) -> dict[str, Any]:
    return {
        "title": _window_text(window),
        "class_name": _window_class_name(window),
        "process_id": _safe_process_id(window),
        "handle": _window_handle(window),
    }


def _looks_like_open_dialog_title(title: str) -> bool:
    title_lower = (title or "").strip().lower()
    if not title_lower:
        return False
    keywords = (
        "open",
        "open file",
        "file name",
        "megnyit",
        "megnyitás",
        "fájlnév",
        "fájl",
    )
    return any(keyword in title_lower for keyword in keywords)


def _looks_like_open_dialog_class(class_name: str) -> bool:
    class_lower = (class_name or "").strip().lower()
    if not class_lower:
        return False
    class_keywords = ("#32770", "dialog", "dlg")
    return any(keyword in class_lower for keyword in class_keywords)


def detect_open_file_dialog_from_context(process_id: int | None, timeout: float = 5.0) -> dict[str, Any]:
    """Detect an Open File dialog using known process/window context without reacquiring main window."""

    from pywinauto import Desktop

    deadline = time.monotonic() + timeout
    desktop = Desktop(backend="uia")

    initial_handles = {
        _window_handle(window)
        for window in desktop.windows(top_level_only=True)
        if _window_handle(window) is not None
    }

    logger.info(
        "Dialog detection context: process_id used for dialog detection={} timeout={}",
        process_id,
        timeout,
    )

    while time.monotonic() < deadline:
        visible_top_level = [window for window in desktop.windows(top_level_only=True) if _safe_is_visible(window)]

        raw_candidates: list[dict[str, Any]] = []
        matching_candidates: list[dict[str, Any]] = []

        for window in visible_top_level:
            snapshot = _dialog_candidate_snapshot(window)
            raw_candidates.append(snapshot)

            candidate_pid = snapshot.get("process_id")
            pid_match = process_id is not None and candidate_pid == process_id
            newly_appeared = snapshot.get("handle") not in initial_handles
            title_match = _looks_like_open_dialog_title(str(snapshot.get("title", "")))
            class_match = _looks_like_open_dialog_class(str(snapshot.get("class_name", "")))

            # Conservative gating:
            # - require title/class dialog signature
            # - and either pid match, or a newly appeared top-level dialog-like window
            if not (title_match or class_match):
                continue
            if not (pid_match or newly_appeared or process_id is None):
                continue

            matching_candidates.append(
                {
                    **snapshot,
                    "pid_match": pid_match,
                    "newly_appeared": newly_appeared,
                    "title_match": title_match,
                    "class_match": class_match,
                }
            )

        logger.info("Dialog detection raw dialog candidates found={}", raw_candidates)

        if matching_candidates:
            best = sorted(
                matching_candidates,
                key=lambda c: (
                    int(bool(c.get("pid_match"))),
                    int(bool(c.get("newly_appeared"))),
                    int(bool(c.get("title_match"))),
                    int(bool(c.get("class_match"))),
                ),
                reverse=True,
            )[0]
            result = {
                "dialog_detected": True,
                "dialog_title": best.get("title") or None,
                "dialog_class": best.get("class_name") or None,
                "candidate_count": len(matching_candidates),
            }
            logger.info("Dialog detection final result={}", result)
            return result

        time.sleep(0.1)

    result = {
        "dialog_detected": False,
        "dialog_title": None,
        "dialog_class": None,
        "candidate_count": 0,
    }
    logger.info("Dialog detection final result={}", result)
    return result


def detect_open_file_dialog(timeout: float = 5.0) -> bool:
    """Backward-compatible bool API; gracefully degrades when process context is unavailable."""

    result = detect_open_file_dialog_from_context(process_id=None, timeout=timeout)
    return bool(result.get("dialog_detected"))


def wait_for_any_window_title_contains(text: str, timeout: float = 5.0) -> Any:
    """Wait until any visible top-level window title contains ``text``."""

    needle = (text or "").strip().lower()
    deadline = time.monotonic() + timeout

    from pywinauto import Desktop

    desktop = Desktop(backend="uia")

    while time.monotonic() < deadline:
        for window in desktop.windows(top_level_only=True):
            title = _window_text(window)
            if needle and needle in title.lower():
                return window
        time.sleep(0.1)

    raise TimeoutError(f"No top-level window title containing '{text}' appeared within {timeout:.1f}s")


def wait_for_dialog_from_context(process_id: int | None, timeout: float = 5.0) -> Any:
    """Wait for a visible dialog with optional process context; never raises for missing context."""

    if process_id is None:
        raise TimeoutError("No process context provided for dialog wait")

    deadline = time.monotonic() + timeout

    from pywinauto import Desktop

    desktop = Desktop(backend="uia")

    while time.monotonic() < deadline:
        for window in desktop.windows(top_level_only=True):
            try:
                if _safe_process_id(window) != process_id:
                    continue
                if not _safe_is_visible(window):
                    continue
                class_name = _window_class_name(window).lower()
                control_type = (getattr(window.element_info, "control_type", "") or "").lower()
                if "dialog" in class_name or control_type == "window":
                    return window
            except Exception:
                continue
        time.sleep(0.1)

    raise TimeoutError(f"No dialog for process_id={process_id} appeared within {timeout:.1f}s")


def wait_for_dialog(timeout: float = 5.0) -> Any:
    """Wait for a visible dialog window owned by the WinWatt main process."""

    main_window = get_cached_main_window()
    pid = main_window.process_id()
    deadline = time.monotonic() + timeout

    from pywinauto import Desktop

    desktop = Desktop(backend="uia")

    while time.monotonic() < deadline:
        for window in desktop.windows(top_level_only=True):
            try:
                if window.process_id() != pid:
                    continue
                if _window_handle(window) == _window_handle(main_window):
                    continue
                if not window.is_visible():
                    continue
                class_name = (window.class_name() or "").lower()
                control_type = (getattr(window.element_info, "control_type", "") or "").lower()
                if "dialog" in class_name or control_type == "window":
                    return window
            except Exception:
                continue
        time.sleep(0.1)

    raise TimeoutError(f"No WinWatt dialog appeared within {timeout:.1f}s")


