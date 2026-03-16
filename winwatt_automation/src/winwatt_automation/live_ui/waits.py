"""Wait helpers for resolving WinWatt windows/dialogs."""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from winwatt_automation.live_ui.app_connector import get_main_window


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


def wait_for_dialog(timeout: float = 5.0) -> Any:
    """Wait for a visible dialog window owned by the WinWatt main process."""

    main_window = get_main_window()
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


def detect_open_file_dialog(timeout: float = 5.0) -> bool:
    """Conservatively detect whether a file-open dialog appeared for WinWatt."""

    dialog_keywords = ("open", "megnyit", "file name", "fájlnév")
    class_keywords = ("#32770", "dialog")

    main_window = get_main_window()
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

                title = _window_text(window)
                class_name = (window.class_name() or "").lower()
                title_lower = title.lower()
                has_title_match = any(keyword in title_lower for keyword in dialog_keywords)
                has_class_match = any(keyword in class_name for keyword in class_keywords)

                if has_title_match or has_class_match:
                    logger.info(
                        "Detected potential open-file dialog title='{}' class='{}' pid={}",
                        title,
                        class_name,
                        pid,
                    )
                    return True
            except Exception:
                continue

        time.sleep(0.1)

    logger.info("No open-file dialog detected within {:.1f}s", timeout)
    return False
