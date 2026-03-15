"""Connection helpers for attaching to a running WinWatt instance."""

from __future__ import annotations

from typing import Any

from loguru import logger

WINWATT_TITLE_PATTERN = ".*WinWatt.*"


class WinWattNotRunningError(RuntimeError):
    """Raised when a running WinWatt process/window cannot be found."""



def connect_to_winwatt() -> Any:
    """Attach to a running WinWatt application.

    Tries ``uia`` backend first as requested, then falls back to ``win32``.
    """

    logger.info("Attempting to connect to WinWatt using UIA backend")
    try:
        from pywinauto import Application

        app = Application(backend="uia").connect(title_re=WINWATT_TITLE_PATTERN)
        logger.info("Connected to WinWatt via UIA backend")
        return app
    except Exception as uia_error:
        logger.warning("UIA connection failed: {}", uia_error)

    logger.info("Attempting to connect to WinWatt using win32 backend")
    try:
        from pywinauto import Application

        app = Application(backend="win32").connect(title_re=WINWATT_TITLE_PATTERN)
        logger.info("Connected to WinWatt via win32 backend")
        return app
    except Exception as win32_error:
        logger.error("Unable to connect to WinWatt: {}", win32_error)
        raise WinWattNotRunningError(
            "WinWatt is not running or no main window matched title pattern"
        ) from win32_error



def get_main_window() -> Any:
    """Return the main WinWatt window wrapper."""

    app = connect_to_winwatt()
    logger.info("Resolving main WinWatt window")
    return app.window(title_re=WINWATT_TITLE_PATTERN)
