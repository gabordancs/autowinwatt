"""Connection helpers for attaching to a running WinWatt instance."""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from loguru import logger

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

    candidates_with_handle = [candidate for candidate in candidates if candidate.get("handle") is not None]
    if not candidates_with_handle:
        raise WinWattNotRunningError(f"No WinWatt-like windows with valid handle were found on backend={backend}")

    visible_candidates = [candidate for candidate in candidates_with_handle if candidate.get("is_visible")]
    ranked_pool = visible_candidates or candidates_with_handle
    if not visible_candidates:
        logger.warning("No visible candidate windows found; falling back to all candidates")

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
        f"visible={bool(winner.get('is_visible'))}",
        f"enabled={bool(winner.get('is_enabled'))}",
        f"title_has_winwatt={'winwatt' in str(winner.get('title') or '').lower()}",
        f"area={((winner.get('rectangle') or {}).get('width', 0)) * ((winner.get('rectangle') or {}).get('height', 0))}",
    ]
    logger.info("Selected main window handle={} score={} reasons={}", winner.get("handle"), winner_score, reasons)

    return winner


def _resolve_main_window_candidate(backend: str = "win32") -> dict[str, Any]:
    candidates = list_candidate_windows(backend=backend)
    if not candidates:
        raise WinWattNotRunningError(f"No WinWatt-like windows found on backend={backend}")

    return select_main_window(candidates, backend=backend)


def _connect_with_win32_handle() -> tuple[Any, dict[str, Any]]:
    from pywinauto import Application

    selected = _resolve_main_window_candidate(backend="win32")
    handle = selected.get("handle")
    app = Application(backend="win32").connect(handle=handle)
    logger.info("Connected to WinWatt backend=win32 handle={}", handle)
    return app, selected



def connect_to_winwatt() -> Any:
    """Attach to a running WinWatt application.

    Always resolves the main window using ``win32`` and attaches by handle.
    """

    try:
        app, _ = _connect_with_win32_handle()
        return app
    except Exception as win32_error:
        logger.error("Unable to connect to WinWatt: {}", win32_error)
        raise WinWattNotRunningError("WinWatt is not running or no eligible main window was found") from win32_error



def get_main_window() -> Any:
    """Return the main WinWatt window wrapper."""

    from pywinauto import Application

    _, selected = _connect_with_win32_handle()
    process_id = selected.get("process_id")
    if process_id is None:
        raise WinWattNotRunningError("Selected WinWatt window has no process_id")

    app_uia = Application(backend="uia").connect(process=process_id)
    logger.info("Connected to WinWatt backend=uia process_id={}", process_id)

    candidates = list_candidate_windows(backend="win32")
    selected = select_main_window(candidates, backend="win32")
    logger.info("Resolving main WinWatt window by process_id={} backend=uia", process_id)
    return app_uia.window(handle=selected["handle"])
