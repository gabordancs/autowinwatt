"""Helpers for interacting with WinWatt menu items via UI Automation."""

from __future__ import annotations

from collections import Counter
import re
import time
from contextlib import contextmanager
from typing import Any

from loguru import logger
from winwatt_automation.runtime_mapping.timing import (
    DEFAULT_UI_DELAY,
    POPUP_CLOSE_TIMEOUT,
    POPUP_WAIT_POLL_INTERVAL,
    POPUP_WAIT_TIMEOUT,
)
from winwatt_automation.live_ui.ui_cache import UIObjectCache
from winwatt_automation.runtime_mapping.config import diagnostic_options
from winwatt_automation.live_ui.app_connector import (
    describe_foreground_window,
    ensure_main_window_foreground_before_click,
    get_cached_main_window,
    get_cached_main_window_snapshot,
    is_winwatt_foreground_context,
    prepare_main_window_for_menu_interaction,
    _materialize_window_wrapper,
)

SYSTEM_MENU_CLASS_NAMES = {"#32768"}
TOP_MENU_NAMES = ("Fájl", "Jegyzékek", "Adatbázis", "Beállítások", "Ablak", "Súgó")
TITLEBAR_ICON_GUARD_WIDTH = 64
TITLEBAR_ICON_GUARD_HEIGHT = 40
SYSTEM_MENU_TITLE = "Rendszer"
SYSTEM_MENU_DEFAULT_ITEMS = {
    "restore",
    "move",
    "size",
    "minimize",
    "maximize",
    "close",
}
TOPBAR_BAND_CACHE_TTL_S = 0.5
POPUP_LOG_STATS = {
    "source_counts": Counter(),
    "dedupe": Counter(),
    "snapshot_count": 0,
    "topbar_like": 0,
    "popup_like": 0,
    "empty_text": 0,
}
_TOPBAR_PARENT_ERROR_STATE: dict[str, Any] = {"active": False, "contexts": set(), "count": 0}


def log_popup_snapshot_summary() -> None:
    logger.info(
        "POPUP_SNAPSHOT_SUMMARY snapshots={} sources={} dedupe={} topbar_like={} popup_like={} empty_text={}",
        POPUP_LOG_STATS["snapshot_count"],
        dict(sorted(POPUP_LOG_STATS["source_counts"].items())),
        dict(sorted(POPUP_LOG_STATS["dedupe"].items())),
        POPUP_LOG_STATS["topbar_like"],
        POPUP_LOG_STATS["popup_like"],
        POPUP_LOG_STATS["empty_text"],
    )

TOPBAR_MAX_EXPECTED_HEIGHT = 80
VERTICAL_POPUP_CLUSTER_MIN_ROWS = 4
VERTICAL_POPUP_CLUSTER_MAX_TOP_GAP = 24
VERTICAL_POPUP_CLUSTER_EDGE_TOLERANCE = 24
VERTICAL_POPUP_CLUSTER_HEIGHT_TOLERANCE = 10
VERTICAL_POPUP_CLUSTER_MIN_X_OVERLAP_RATIO = 0.8
REPEATED_LEGACY_TEXT_MIN_ROWS = 2
REPEATED_LEGACY_TEXT_MIN_RATIO = 0.4
POPUP_NOISE_RECT_TOLERANCE = 6
_MENU_ITEMS_REENTRANCY_DEPTH = 0
_TOPBAR_BAND_CACHE: dict[str, Any] = {"handle": None, "captured_at": 0.0, "band": None}
RECENT_PROJECT_ENTRY_PATTERN = re.compile(r"^\s*\d+\s*:")


def _log_phase_timing(phase: str, started_at: float, **payload: Any) -> None:
    details = " ".join(f"{key}={value}" for key, value in payload.items())
    suffix = f" {details}" if details else ""
    logger.debug("DBG_PHASE_TIMING phase={} elapsed_ms={:.3f}{}", phase, (time.monotonic() - started_at) * 1000.0, suffix)


def _popup_visibility_counts(rows: list[dict[str, Any]]) -> tuple[int, int]:
    popup_visible = sum(1 for row in rows if bool(row.get("popup_candidate")))
    topbar_visible = sum(1 for row in rows if bool(row.get("topbar_candidate")))
    return popup_visible, topbar_visible


def _rect_tuple(rect: dict[str, int] | None) -> tuple[int, int, int, int]:
    rect = rect or {}
    return (
        int(rect.get("left", 0)),
        int(rect.get("top", 0)),
        int(rect.get("right", 0)),
        int(rect.get("bottom", 0)),
    )


def _center_tuple(row: dict[str, Any]) -> tuple[int, int]:
    return int(row.get("center_x") or 0), int(row.get("center_y") or 0)


def _query_menu_items_from_root(root: Any, *, force_refresh: bool = False) -> list[Any]:
    handle = getattr(getattr(root, "element_info", root), "handle", None)
    descendants = getattr(root, "descendants", None)
    if not callable(descendants):
        return []

    def _query() -> list[Any]:
        return [item for item in descendants() if _control_type(item) == "menuitem"]

    ttl_s = 0.0 if force_refresh or handle is None else 0.5
    return _UI_CACHE.get_or_query((handle, "menu_items", "MenuItem"), _query, ttl_s=ttl_s)


@contextmanager
def _menu_items_reentrancy_guard(*, force_refresh: bool) -> Any:
    global _MENU_ITEMS_REENTRANCY_DEPTH
    if _MENU_ITEMS_REENTRANCY_DEPTH > 0:
        logger.warning(
            "DBG_WINWATT_MENU_REENTRANCY_GUARD depth={} force_refresh={} action=direct_query_fallback",
            _MENU_ITEMS_REENTRANCY_DEPTH,
            force_refresh,
        )
        yield False
        return

    _MENU_ITEMS_REENTRANCY_DEPTH += 1
    try:
        yield True
    finally:
        _MENU_ITEMS_REENTRANCY_DEPTH = max(0, _MENU_ITEMS_REENTRANCY_DEPTH - 1)


def _is_com_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    module = str(getattr(type(exc), "__module__", "")).lower()
    return "comerror" in name or "com_error" in name or "pythoncom" in module or "pywintypes" in module or "comtypes" in module


def _is_recent_project_entry_text(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    return bool(RECENT_PROJECT_ENTRY_PATTERN.match(value) and re.search(r"\.wwp\b", value, flags=re.IGNORECASE))


def _is_separator_row(*, text: str, rect: dict[str, int] | None = None, fragments: list[dict[str, Any]] | None = None) -> bool:
    value = str(text or "").strip()
    rect = dict(rect or {})
    if not value:
        if rect:
            return _is_separator_by_geometry({
                "width": max(0, int(rect.get("right", 0)) - int(rect.get("left", 0))),
                "height": max(0, int(rect.get("bottom", 0)) - int(rect.get("top", 0))),
            })
        return True
    if value in {"-", "—", "–", "_"} and len(value) <= 3:
        return True
    if fragments and all(not str(fragment.get("text") or "").strip() for fragment in fragments):
        return _is_separator_row(text="", rect=rect, fragments=None)
    return False


def _remember_topbar_parent_comerror(context: str, wrapper: Any, exc: Exception) -> None:
    _TOPBAR_PARENT_ERROR_STATE["active"] = True
    _TOPBAR_PARENT_ERROR_STATE["count"] = int(_TOPBAR_PARENT_ERROR_STATE.get("count") or 0) + 1
    contexts = _TOPBAR_PARENT_ERROR_STATE.setdefault("contexts", set())
    if isinstance(contexts, set):
        contexts.add(context)
    logger.info(
        "TOPBAR_PARENT_COMERROR_FALLBACK context={} wrapper_name={!r} control_type={} class_name={} rectangle={} error_type={} error={!r}",
        context,
        _name(wrapper),
        _control_type(wrapper),
        _class_name(wrapper),
        _rect_tuple(_rectangle_data(wrapper)),
        type(exc).__name__,
        str(exc),
    )
    logger.debug("TOPBAR_PARENT_COMERROR_FALLBACK exception detail", exception=exc)


def _consume_topbar_parent_error_state() -> dict[str, Any]:
    state = {
        "active": bool(_TOPBAR_PARENT_ERROR_STATE.get("active")),
        "contexts": sorted(str(item) for item in (_TOPBAR_PARENT_ERROR_STATE.get("contexts") or set())),
        "count": int(_TOPBAR_PARENT_ERROR_STATE.get("count") or 0),
    }
    _TOPBAR_PARENT_ERROR_STATE.update({"active": False, "contexts": set(), "count": 0})
    return state


def _geometry_only_top_level_menu_items_from_items(items: list[Any]) -> list[Any]:
    candidate_rows: list[dict[str, Any]] = []
    candidate_items: list[tuple[Any, dict[str, Any]]] = []
    normalized_top_names = {_normalize(name) for name in TOP_MENU_NAMES}
    for item in items:
        rect = _rectangle_data(item)
        if rect is None or not _is_visible(item):
            continue
        row = {"text": _name(item), "normalized_text": _normalize(_name(item)), "rectangle": rect, "center_x": rect["center_x"], "center_y": rect["center_y"]}
        candidate_items.append((item, row))
        if row["normalized_text"] in normalized_top_names:
            candidate_rows.append(row)
    if not candidate_items:
        return []
    seed_rows = candidate_rows or [row for _item, row in candidate_items]
    band = _compute_topbar_band_from_rows(seed_rows)
    if band is None:
        return [item for item, _row in candidate_items if _normalize(_name(item)) in normalized_top_names]
    selected: list[Any] = []
    for item, row in candidate_items:
        if _row_in_vertical_band(row, band):
            selected.append(item)
    return selected


def _top_level_menu_items_with_meta_from_items(items: list[Any]) -> tuple[list[Any], dict[str, Any]]:
    top_level_items: list[Any] = []
    geometry_needed = False
    for item in items:
        parent_wrapper, parent_comerror = _safe_parent_wrapper(item, context="top_level_menu_items")
        geometry_needed = geometry_needed or parent_comerror
        parent_type = _control_type(parent_wrapper)
        if parent_type not in {"menu", "menubar"}:
            continue
        if _has_menuitem_ancestor(item):
            continue
        top_level_items.append(item)
    geometry_items: list[Any] = []
    if geometry_needed:
        geometry_items = _geometry_only_top_level_menu_items_from_items(items)
        if geometry_items:
            logger.info(
                "TOPBAR_GEOMETRY_FALLBACK_USED context=top_level_menu_items items={} named_candidates={} parent_comerror_count={}",
                len(geometry_items),
                sum(1 for item in geometry_items if _normalize(_name(item)) in {_normalize(name) for name in TOP_MENU_NAMES}),
                int(_TOPBAR_PARENT_ERROR_STATE.get("count") or 0),
            )
    merged: list[Any] = []
    seen_ids: set[int] = set()
    for item in top_level_items + geometry_items:
        marker = id(item)
        if marker in seen_ids:
            continue
        seen_ids.add(marker)
        merged.append(item)
    return merged, {"geometry_fallback_used": bool(geometry_items), "parent_comerror": geometry_needed}


def _top_level_menu_items_from_items(items: list[Any]) -> list[Any]:
    top_level_items, _meta = _top_level_menu_items_with_meta_from_items(items)
    return top_level_items


def _compute_topbar_band_from_items(items: list[Any]) -> dict[str, int] | None:
    top_level_items, meta = _top_level_menu_items_with_meta_from_items(items)
    top_level_rects = [rect for item in top_level_items for rect in [_rectangle_data(item)] if rect is not None]
    if not top_level_rects:
        return None

    left = min(rect["left"] for rect in top_level_rects)
    top = min(rect["top"] for rect in top_level_rects)
    right = max(rect["right"] for rect in top_level_rects)
    bottom = max(rect["bottom"] for rect in top_level_rects)
    band = {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": max(0, right - left),
        "height": max(0, bottom - top),
        "center_x": int((left + right) / 2),
        "center_y": int((top + bottom) / 2),
    }
    if meta.get("geometry_fallback_used"):
        band["_fallback_mode"] = "geometry_only"
    return band


def _main_window_topbar_band(*, force_refresh: bool = False) -> dict[str, int] | None:
    try:
        main_window = get_cached_main_window()
    except Exception:
        return None

    handle = getattr(getattr(main_window, "element_info", main_window), "handle", None)
    now = time.monotonic()
    if (
        not force_refresh
        and _TOPBAR_BAND_CACHE.get("handle") == handle
        and now - float(_TOPBAR_BAND_CACHE.get("captured_at") or 0.0) < TOPBAR_BAND_CACHE_TTL_S
    ):
        return _TOPBAR_BAND_CACHE.get("band")

    band: dict[str, int] | None = None
    menu_bar = getattr(main_window, "child_window", None)
    if callable(menu_bar):
        try:
            menu_bar_ctrl = main_window.child_window(control_type="MenuBar").wrapper_object()
            band = _rectangle_data(menu_bar_ctrl)
        except Exception:
            band = None

    if band is None:
        low_level_items = _query_menu_items_from_root(main_window, force_refresh=force_refresh)
        band = _compute_topbar_band_from_items(low_level_items)
        if band is None:
            geometry_items = _geometry_only_top_level_menu_items_from_items(low_level_items)
            geometry_band = _compute_topbar_band_from_rows([
                {"text": _name(item), "normalized_text": _normalize(_name(item)), "rectangle": rect, "center_x": rect["center_x"], "center_y": rect["center_y"]}
                for item in geometry_items
                for rect in [_rectangle_data(item)]
                if rect is not None
            ])
            if geometry_band is not None:
                band = dict(geometry_band)
                band["_fallback_mode"] = "geometry_only"
                logger.info(
                    "TOPBAR_GEOMETRY_FALLBACK_USED context=main_window_topbar_band items={} handle={} force_refresh={}",
                    len(geometry_items),
                    handle,
                    force_refresh,
                )

    _TOPBAR_BAND_CACHE.update({"handle": handle, "captured_at": now, "band": band})
    return band


def _row_in_vertical_band(row: dict[str, Any], band: dict[str, int] | None) -> bool:
    if band is None:
        return False
    center_y = int(row.get("center_y") or 0)
    return int(band["top"]) <= center_y <= int(band["bottom"])


def _row_below_band(row: dict[str, Any], band: dict[str, int] | None) -> bool:
    if band is None:
        return False
    rect = row.get("rectangle") or {}
    return int(rect.get("top", 0)) >= int(band["bottom"])


def _resolved_topbar_band(rows: list[dict[str, Any]], topbar_band: dict[str, int] | None) -> dict[str, int] | None:
    if not rows:
        return topbar_band

    named_topbar_rows = [
        row
        for row in rows
        if _normalize(str(row.get("text") or "")) in {_normalize(name) for name in TOP_MENU_NAMES}
    ]
    if named_topbar_rows:
        candidate_band = _compute_topbar_band_from_rows(named_topbar_rows)
        if candidate_band is not None:
            return candidate_band

    if topbar_band is None:
        return None

    if int(topbar_band.get("height", 0)) <= TOPBAR_MAX_EXPECTED_HEIGHT:
        return topbar_band

    compact_band = _compute_topbar_band_from_rows(rows)
    if compact_band is not None and int(compact_band.get("height", 0)) < int(topbar_band.get("height", 0)):
        return compact_band
    return topbar_band


def _detect_empty_text_vertical_popup_cluster(
    rows: list[dict[str, Any]],
    topbar_band: dict[str, int] | None,
) -> tuple[set[tuple[int, int, int, int]], dict[str, Any]]:
    accepted_keys: set[tuple[int, int, int, int]] = set()
    diagnostic = {
        "detected": False,
        "accepted_rows": 0,
        "reason": "no_cluster",
    }
    if topbar_band is None:
        diagnostic["reason"] = "missing_topbar_band"
        return accepted_keys, diagnostic

    candidates = []
    for row in rows:
        rect = row.get("rectangle") or {}
        text = str(row.get("text") or "")
        if text.strip():
            continue
        if _normalize(str(row.get("control_type") or "")) != "menuitem":
            continue
        if int(rect.get("top", 0)) < int(topbar_band.get("bottom", 0)):
            continue
        candidates.append(row)

    if len(candidates) < VERTICAL_POPUP_CLUSTER_MIN_ROWS:
        diagnostic["reason"] = "candidate_count_below_threshold"
        return accepted_keys, diagnostic

    candidates.sort(key=lambda item: ((item.get("rectangle") or {}).get("top", 0), ((item.get("rectangle") or {}).get("left", 0))))
    cluster = [candidates[0]]
    base_rect = candidates[0].get("rectangle") or {}
    base_left = int(base_rect.get("left", 0))
    base_right = int(base_rect.get("right", 0))
    base_height = max(1, int(base_rect.get("bottom", 0)) - int(base_rect.get("top", 0)))
    last_top = int(base_rect.get("top", 0))
    for row in candidates[1:]:
        rect = row.get("rectangle") or {}
        left = int(rect.get("left", 0))
        right = int(rect.get("right", 0))
        top = int(rect.get("top", 0))
        height = max(1, int(rect.get("bottom", 0)) - top)
        overlap_width = max(0, min(base_right, right) - max(base_left, left))
        min_width = max(1, min(base_right - base_left, right - left))
        overlap_ratio = overlap_width / min_width
        if abs(left - base_left) > VERTICAL_POPUP_CLUSTER_EDGE_TOLERANCE and overlap_ratio < VERTICAL_POPUP_CLUSTER_MIN_X_OVERLAP_RATIO:
            continue
        if abs(right - base_right) > VERTICAL_POPUP_CLUSTER_EDGE_TOLERANCE and overlap_ratio < VERTICAL_POPUP_CLUSTER_MIN_X_OVERLAP_RATIO:
            continue
        if abs(height - base_height) > VERTICAL_POPUP_CLUSTER_HEIGHT_TOLERANCE:
            continue
        if top - last_top > VERTICAL_POPUP_CLUSTER_MAX_TOP_GAP:
            continue
        cluster.append(row)
        last_top = top

    if len(cluster) < VERTICAL_POPUP_CLUSTER_MIN_ROWS:
        diagnostic["reason"] = "cluster_below_threshold"
        return accepted_keys, diagnostic

    for row in cluster:
        rect = row.get("rectangle") or {}
        accepted_keys.add((int(rect.get("left", 0)), int(rect.get("top", 0)), int(rect.get("right", 0)), int(rect.get("bottom", 0))))

    diagnostic.update(
        {
            "detected": True,
            "accepted_rows": len(cluster),
            "reason": "empty_text_vertical_cluster_below_topbar",
            "cluster_left": base_left,
            "cluster_right": base_right,
            "cluster_height": base_height,
            "cluster_top": int((cluster[0].get("rectangle") or {}).get("top", 0)),
            "cluster_bottom": int((cluster[-1].get("rectangle") or {}).get("bottom", 0)),
        }
    )
    return accepted_keys, diagnostic


def _classify_row_geometry(
    row: dict[str, Any],
    topbar_band: dict[str, int] | None,
    *,
    vertical_popup_override_keys: set[tuple[int, int, int, int]] | None = None,
) -> tuple[bool, bool, str | None]:
    rect = row.get("rectangle") or {}
    rect_key = (int(rect.get("left", 0)), int(rect.get("top", 0)), int(rect.get("right", 0)), int(rect.get("bottom", 0)))
    if vertical_popup_override_keys and rect_key in vertical_popup_override_keys:
        return False, True, "empty_text_vertical_cluster_below_topbar"

    topbar_candidate = _row_in_vertical_band(row, topbar_band)
    popup_candidate = _row_below_band(row, topbar_band)
    return topbar_candidate, popup_candidate, ("below_topbar_band" if popup_candidate else None)


def _row_identity_payload(row: dict[str, Any]) -> dict[str, Any]:
    handle = row.get("native_handle")
    try:
        handle = int(handle) if handle is not None else None
    except Exception:
        handle = None

    process_id = row.get("process_id")
    try:
        process_id = int(process_id) if process_id is not None else None
    except Exception:
        process_id = None

    return {
        "source_scope": row.get("source_scope", ""),
        "control_type": row.get("control_type", ""),
        "class_name": row.get("class_name", ""),
        "text": row.get("text", ""),
        "rectangle": dict(row.get("rectangle") or {}),
        "center": _center_tuple(row),
        "process_id": process_id,
        "native_handle": handle,
        "topbar_candidate": bool(row.get("topbar_candidate")),
        "popup_candidate": bool(row.get("popup_candidate")),
    }


def _log_popup_fragment(label: str, row: dict[str, Any]) -> None:
    payload = _row_identity_payload(row)
    logger.debug(
        "{} source_scope={} control_type={} class_name={} text={!r} rectangle={} center={} process_id={} native_handle={} topbar_candidate={} popup_candidate={}",
        label,
        payload["source_scope"],
        payload["control_type"],
        payload["class_name"],
        payload["text"],
        payload["rectangle"],
        payload["center"],
        payload["process_id"],
        payload["native_handle"],
        payload["topbar_candidate"],
        payload["popup_candidate"],
    )


def _log_top_menu_popup_diagnostics(title: str, item_rect: Any, topbar_band: dict[str, int] | None) -> None:
    snapshot_rows = capture_menu_popup_snapshot()
    all_visible_menu_items = [item for item in _menu_items(force_refresh=True) if _is_visible(item)]
    topbar_count = 0
    popup_count = 0
    popup_texts_under_title: list[str] = []
    system_popup_cluster = False
    title_norm = _normalize(title)
    item_center_x = int((int(item_rect.left) + int(item_rect.right)) / 2)
    resolved_topbar_band = _resolved_topbar_band(snapshot_rows, topbar_band)
    vertical_popup_override_keys, vertical_popup_diag = _detect_empty_text_vertical_popup_cluster(snapshot_rows, resolved_topbar_band)
    logger.info(
        "DBG_MENU_EMPTY_TEXT_VERTICAL_CLUSTER detected={} accepted_popup_rows={} reason={} topbar_band={} ",
        vertical_popup_diag.get("detected"),
        vertical_popup_diag.get("accepted_rows"),
        vertical_popup_diag.get("reason"),
        _rect_tuple(resolved_topbar_band),
    )
    for row in snapshot_rows:
        topbar_candidate, popup_candidate, _popup_reason = _classify_row_geometry(row, resolved_topbar_band, vertical_popup_override_keys=vertical_popup_override_keys)
        if topbar_candidate:
            topbar_count += 1
        if popup_candidate:
            popup_count += 1
            left, _, right, _ = _rect_tuple(row.get("rectangle"))
            if left <= item_center_x <= right and str(row.get("normalized_text") or "") != title_norm:
                popup_texts_under_title.append(str(row.get("text") or ""))
    popup_cluster_tops = sorted(
        {int((row.get("rectangle") or {}).get("top", 0)) for row in snapshot_rows if bool(row.get("popup_candidate"))}
    )
    if popup_cluster_tops:
        topbar_bottom = int((topbar_band or {}).get("bottom", 0))
        system_popup_cluster = any(top > topbar_bottom for top in popup_cluster_tops)
    logger.info(
        "DBG_TOP_MENU_CLICK_POPUP_DIAG title={} total_visible_menuitems={} topbar_band_menuitems={} popup_region_menuitems={} new_cluster_below_topbar={} visible_texts_under_title={} topbar_band={} snapshot_row_count={} ",
        title,
        len(all_visible_menu_items),
        topbar_count,
        popup_count,
        system_popup_cluster,
        popup_texts_under_title,
        _rect_tuple(resolved_topbar_band),
        len(snapshot_rows),
    )


def _is_system_menu_title(title: str) -> bool:
    return _normalize(title) == _normalize(SYSTEM_MENU_TITLE)


def _system_menu_icon_point(main_window: Any) -> tuple[int, int]:
    rect = main_window.rectangle()
    left = int(rect.left)
    top = int(rect.top)
    return left + 16, top + 16


def _is_system_menu_window(wrapper: Any) -> bool:
    class_name_getter = getattr(wrapper, "class_name", None)
    class_name = class_name_getter() if callable(class_name_getter) else getattr(getattr(wrapper, "element_info", wrapper), "class_name", "")
    return _normalize(str(class_name)) in {_normalize(name) for name in SYSTEM_MENU_CLASS_NAMES}


def _system_menu_windows() -> list[Any]:
    try:
        from pywinauto import Desktop
    except Exception:
        return []

    windows: list[Any] = []
    for window in Desktop(backend="uia").windows(top_level_only=True):
        try:
            if not bool(getattr(window, "is_visible", lambda: False)()):
                continue
            if not _is_system_menu_window(window):
                continue
            windows.append(window)
        except Exception:
            continue
    logger.info(
        "DBG_WINWATT_SYSTEM_MENU_WINDOW_SCAN visible_system_menu_windows={} foreground={}",
        len(windows),
        describe_foreground_window(),
    )
    return windows


def _system_menu_fragment_candidates(window: Any) -> list[Any]:
    candidates: list[Any] = []
    children = getattr(window, "children", None)
    descendants = getattr(window, "descendants", None)
    for getter in (children, descendants):
        if not callable(getter):
            continue
        try:
            candidates.extend(list(getter()))
        except Exception:
            continue
    deduped: list[Any] = []
    seen: set[int] = set()
    for item in candidates:
        marker = id(item)
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(item)
    return deduped


def _system_menu_row_from_wrapper(item: Any, *, source_scope: str) -> dict[str, Any] | None:
    if not _is_visible(item):
        return None
    rect = _rectangle_data(item)
    if rect is None:
        return None
    info = getattr(item, "element_info", item)
    text = _name(item)
    control_type = getattr(info, "control_type", None)
    class_name = getattr(info, "class_name", None) or ""
    row = {
        "text": text,
        "normalized_text": _normalize(text),
        "control_type": control_type,
        "class_name": class_name,
        "rectangle": {
            "left": rect["left"],
            "top": rect["top"],
            "right": rect["right"],
            "bottom": rect["bottom"],
        },
        "width": rect["width"],
        "height": rect["height"],
        "center_x": rect["center_x"],
        "center_y": rect["center_y"],
        "is_separator": _is_separator_by_geometry(rect),
        "source_scope": source_scope,
        "process_id": getattr(info, "process_id", None),
        "native_handle": getattr(info, "handle", None),
        "enabled": getattr(info, "enabled", None),
        "topbar_candidate": False,
        "popup_candidate": True,
    }
    return row




def _compute_topbar_band_from_rows(rows: list[dict[str, Any]]) -> dict[str, int] | None:
    if not rows:
        return None
    min_top = min(int((row.get("rectangle") or {}).get("top", 0)) for row in rows)
    top_cluster = [
        row
        for row in rows
        if int((row.get("rectangle") or {}).get("top", 0)) <= min_top + TITLEBAR_ICON_GUARD_HEIGHT
    ]
    if not top_cluster:
        return None

    left = min(int((row.get("rectangle") or {}).get("left", 0)) for row in top_cluster)
    top = min(int((row.get("rectangle") or {}).get("top", 0)) for row in top_cluster)
    right = max(int((row.get("rectangle") or {}).get("right", 0)) for row in top_cluster)
    bottom = max(int((row.get("rectangle") or {}).get("bottom", 0)) for row in top_cluster)
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": max(0, right - left),
        "height": max(0, bottom - top),
        "center_x": int((left + right) / 2),
        "center_y": int((top + bottom) / 2),
    }


def _capture_popup_region_rows_for_system_menu() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int] | None]:
    logger.info("DBG_WINWATT_SYSTEM_MENU_FALLBACK_PATH method=isolated_popup_region_capture")
    try:
        main_window = _materialize_window_wrapper(get_cached_main_window_snapshot())
        items = _query_menu_items_from_root(main_window, force_refresh=True)
        if not items and not is_winwatt_foreground_context(main_window, allow_dialog=True):
            logger.info(
                "DBG_WINWATT_SYSTEM_MENU_FALLBACK_RETRY reason_code=empty_snapshot_off_foreground foreground={}",
                describe_foreground_window(),
            )
            time.sleep(max(0.05, DEFAULT_UI_DELAY / 2))
            items = _query_menu_items_from_root(main_window, force_refresh=True)
    except Exception as exc:
        logger.warning(
            "DBG_WINWATT_SYSTEM_MENU_FALLBACK_CAPTURE_FAILED stage=query exception_class={} exception_message={}",
            exc.__class__.__name__,
            exc,
        )
        return [], [], None

    preliminary_rows = [
        row
        for item in items
        for row in [_menu_row_from_wrapper(item, source_scope="system_menu_fallback_main_window", topbar_band=None)]
        if row is not None
    ]
    topbar_band = _compute_topbar_band_from_items(items) or _compute_topbar_band_from_rows(preliminary_rows)
    popup_candidates: list[dict[str, Any]] = []
    excluded_topbar: list[dict[str, Any]] = []
    logger.info(
        "DBG_WINWATT_SYSTEM_MENU_FALLBACK_SNAPSHOT menu_items={} preliminary_rows={} topbar_band={} foreground={}",
        len(items),
        len(preliminary_rows),
        _rect_tuple(topbar_band),
        describe_foreground_window(),
    )
    for item in items:
        row = _menu_row_from_wrapper(item, source_scope="system_menu_fallback_main_window", topbar_band=topbar_band)
        if row is None:
            continue
        if row["popup_candidate"] and not row["topbar_candidate"]:
            popup_candidates.append(row)
            _log_popup_fragment("DBG_WINWATT_SYSTEM_MENU_FALLBACK_POPUP_CANDIDATE", row)
            continue
        if row["topbar_candidate"]:
            excluded_topbar.append(row)
            _log_popup_fragment("DBG_WINWATT_SYSTEM_MENU_FALLBACK_EXCLUDED_TOPBAR", row)
    return popup_candidates, excluded_topbar, topbar_band


def _system_menu_fallback_rows_from_popup_region() -> list[dict[str, Any]]:
    popup_candidates, excluded_topbar, topbar_band = _capture_popup_region_rows_for_system_menu()

    popup_candidates.sort(key=lambda item: (item["rectangle"]["top"], item["rectangle"]["left"]))
    logical_rows = _group_popup_fragments_into_logical_rows(popup_candidates)
    for index, row in enumerate(logical_rows):
        row["index"] = index
        row["topbar_candidate"] = False
        row["popup_candidate"] = True
        row["source_scope"] = "system_menu_fallback"
        logger.info(
            "DBG_WINWATT_SYSTEM_MENU_FALLBACK_FINAL_ROW row_index={} text={!r} rectangle={} fragments={} source_scope_summary={}",
            index,
            row.get("text"),
            row.get("rectangle"),
            [fragment.get("text", "") for fragment in row.get("fragments", [])],
            row.get("source_scope_summary", []),
        )

    logger.info(
        "DBG_WINWATT_SYSTEM_MENU_FALLBACK_SUMMARY snapshot_rows={} popup_region_candidates={} excluded_topbar_candidates={} logical_rows={} topbar_band={} foreground={}",
        len(popup_candidates) + len(excluded_topbar),
        len(popup_candidates),
        len(excluded_topbar),
        len(logical_rows),
        _rect_tuple(topbar_band),
        describe_foreground_window(),
    )
    return logical_rows


def open_system_menu(main_window: Any) -> None:
    ensure_main_window_foreground_before_click(action_label="open_system_menu")
    logger.info("DBG_WINWATT_SYSTEM_MENU_OPEN_START method=alt_space foreground_before={}", describe_foreground_window())
    try:
        from pywinauto import keyboard

        keyboard.send_keys("%{SPACE}")
    except Exception as exc:
        logger.warning("DBG_WINWATT_SYSTEM_MENU_ALTSPACE_FAILED error={} fallback=titlebar_icon_click", exc)
        _mouse_click(_system_menu_icon_point(main_window))

    time.sleep(max(0.05, DEFAULT_UI_DELAY / 2))
    fg = describe_foreground_window()
    logger.info("DBG_WINWATT_SYSTEM_MENU_OPEN_RESULT foreground_after={} system_menu_foreground={}", fg, _is_system_menu_foreground())


def capture_system_menu_popup() -> list[dict[str, Any]]:
    windows = _system_menu_windows()
    if not windows:
        return _system_menu_fallback_rows_from_popup_region()

    rows: list[dict[str, Any]] = []
    seen: set[tuple[int, int, int, int, str, str]] = set()

    for window_index, window in enumerate(windows):
        info = getattr(window, "element_info", window)
        logger.info(
            "DBG_WINWATT_SYSTEM_MENU_WINDOW window_index={} class_name={} name={!r} control_type={} handle={} process_id={}",
            window_index,
            getattr(info, "class_name", None),
            getattr(info, "name", None),
            getattr(info, "control_type", None),
            getattr(info, "handle", None),
            getattr(info, "process_id", None),
        )
        for item in _system_menu_fragment_candidates(window):
            row = _system_menu_row_from_wrapper(item, source_scope="system_menu_window")
            if row is None:
                continue
            rect = row["rectangle"]
            key = (
                rect["left"],
                rect["top"],
                rect["right"],
                rect["bottom"],
                row["normalized_text"],
                _normalize(str(row.get("control_type") or "")),
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
            logger.info(
                "DBG_WINWATT_SYSTEM_MENU_FRAGMENT source_scope={} control_type={} class_name={} text={!r} rectangle={} center={} process_id={} native_handle={} is_separator={} enabled={}",
                row.get("source_scope"),
                row.get("control_type"),
                row.get("class_name"),
                row.get("text"),
                row.get("rectangle"),
                (row.get("center_x"), row.get("center_y")),
                row.get("process_id"),
                row.get("native_handle"),
                row.get("is_separator"),
                row.get("enabled"),
            )

    rows.sort(key=lambda item: (item["rectangle"]["top"], item["rectangle"]["left"]))
    logical_rows = _group_popup_fragments_into_logical_rows(rows)
    for index, row in enumerate(logical_rows):
        row["index"] = index
        row["topbar_candidate"] = False
        row["popup_candidate"] = True

    control_types = sorted({str(row.get("control_type") or "") for row in rows})
    class_names = sorted({str(row.get("class_name") or "") for row in rows})
    default_item_rows = [row.get("text") for row in logical_rows if _normalize(str(row.get("text") or "")) in SYSTEM_MENU_DEFAULT_ITEMS]
    logger.info(
        "DBG_WINWATT_SYSTEM_MENU_CAPTURE_SUMMARY raw_fragments={} logical_rows={} control_types={} class_names={} default_item_rows={} foreground={}",
        len(rows),
        len(logical_rows),
        control_types,
        class_names,
        default_item_rows,
        describe_foreground_window(),
    )
    return logical_rows


def _mouse_click(coords: tuple[int, int]) -> None:
    from pywinauto import mouse

    mouse.click(button="left", coords=coords)


def _is_system_menu_foreground() -> bool:
    fg = describe_foreground_window()
    class_name = _normalize(str(fg.get("class_name", "")))
    return class_name in {_normalize(name) for name in SYSTEM_MENU_CLASS_NAMES}


def _validate_not_in_forbidden_top_left_zone(main_window: Any, point: tuple[int, int]) -> None:
    rect = main_window.rectangle()
    left = int(rect.left)
    top = int(rect.top)
    if point[0] <= left + TITLEBAR_ICON_GUARD_WIDTH and point[1] <= top + TITLEBAR_ICON_GUARD_HEIGHT:
        logger.error("blocked_click_forbidden_zone point={} main_left={} main_top={}", point, left, top)
        raise RuntimeError("click_blocked_forbidden_zone")


def _coerce_point_outside_forbidden_top_left_zone(
    main_window: Any,
    point: tuple[int, int],
    *,
    target_rect: Any | None = None,
) -> tuple[int, int]:
    rect = main_window.rectangle()
    left = int(rect.left)
    top = int(rect.top)
    right = int(rect.right)
    bottom = int(rect.bottom)
    guard_right = left + TITLEBAR_ICON_GUARD_WIDTH
    guard_bottom = top + TITLEBAR_ICON_GUARD_HEIGHT

    safe_x, safe_y = point
    if safe_x <= guard_right and safe_y <= guard_bottom and target_rect is not None:
        target_left = int(getattr(target_rect, "left", safe_x))
        target_top = int(getattr(target_rect, "top", safe_y))
        target_right = int(getattr(target_rect, "right", safe_x + 1))
        target_bottom = int(getattr(target_rect, "bottom", safe_y + 1))
        candidate_y = max(safe_y, guard_bottom + 1)
        if target_top <= candidate_y < target_bottom:
            safe_y = candidate_y
        else:
            candidate_x = max(safe_x, guard_right + 1)
            if target_left <= candidate_x < target_right:
                safe_x = candidate_x

    if safe_x <= guard_right and safe_y <= guard_bottom:
        safe_x = max(safe_x, left + TITLEBAR_ICON_GUARD_WIDTH + 8)
        safe_y = max(safe_y, top + TITLEBAR_ICON_GUARD_HEIGHT + 8)

    safe_x = min(max(left + 1, safe_x), max(left + 1, right - 1))
    safe_y = min(max(top + 1, safe_y), max(top + 1, bottom - 1))

    if (safe_x, safe_y) != point:
        logger.warning(
            "adjusted_click_outside_forbidden_zone original_point={} adjusted_point={} main_left={} main_top={} target_rect_preserved={}",
            point,
            (safe_x, safe_y),
            left,
            top,
            target_rect is not None,
        )

    return safe_x, safe_y


def _relative_coords_for_point(main_window: Any, point: tuple[int, int]) -> tuple[int, int]:
    menu_bar = getattr(main_window, "child_window", None)
    if callable(menu_bar):
        try:
            menu_bar_ctrl = main_window.child_window(control_type="MenuBar").wrapper_object()
            menu_bar_rect = menu_bar_ctrl.rectangle()
            return int(point[0] - int(menu_bar_rect.left)), int(point[1] - int(menu_bar_rect.top))
        except Exception:
            pass

    window_rect = main_window.rectangle()
    return int(point[0] - int(window_rect.left)), int(point[1] - int(window_rect.top))


def _click_main_window_at_point(
    main_window: Any,
    point: tuple[int, int],
    *,
    log_label: str,
    target_rect: Any | None = None,
) -> None:
    safe_point = _coerce_point_outside_forbidden_top_left_zone(main_window, point, target_rect=target_rect)
    rel_x, rel_y = _relative_coords_for_point(main_window, safe_point)
    if callable(getattr(main_window, "click_input", None)):
        main_window.click_input(coords=(rel_x, rel_y))
        logger.info("{} rel_x={} rel_y={}", log_label, rel_x, rel_y)
        return

    _mouse_click(safe_point)
    logger.info("{} x={} y={}", log_label, safe_point[0], safe_point[1])


def _validate_post_menu_open_foreground(main_window: Any, *, title: str) -> None:
    fg = describe_foreground_window()
    logger.info("post_click_foreground_validation title={} foreground={}", title, fg)
    if _is_system_menu_foreground():
        try:
            from pywinauto import keyboard

            keyboard.send_keys("{ESC}")
        except Exception:
            pass
        logger.error("system_menu_opened_instead_of_top_menu top_menu={} foreground={}", title, fg)
        raise RuntimeError("failed_system_menu")
    if not is_winwatt_foreground_context(main_window, allow_dialog=True):
        raise RuntimeError("failed_wrong_window")


_LAST_MENU_SNAPSHOT_BEFORE_OPEN: set[tuple[str, str, str, str, str]] | None = None
_UI_CACHE = UIObjectCache()


def _normalize(text: str | None) -> str:
    return (text or "").strip().lower()


def _name(wrapper: Any) -> str:
    info = getattr(wrapper, "element_info", wrapper)
    return (getattr(info, "name", None) or "").strip()


def _is_visible(wrapper: Any) -> bool:
    is_visible = getattr(wrapper, "is_visible", None)
    if callable(is_visible):
        try:
            return bool(is_visible())
        except Exception:
            return False
    return False


def _control_type(wrapper: Any) -> str:
    info = getattr(wrapper, "element_info", wrapper)
    return _normalize(getattr(info, "control_type", None))


def _class_name(wrapper: Any) -> str:
    info = getattr(wrapper, "element_info", wrapper)
    return (getattr(info, "class_name", None) or "").strip()


def _rectangle_data(wrapper: Any) -> dict[str, int] | None:
    rectangle = getattr(wrapper, "rectangle", None)
    if not callable(rectangle):
        return None
    try:
        rect = rectangle()
    except Exception:
        return None

    left = getattr(rect, "left", None)
    top = getattr(rect, "top", None)
    right = getattr(rect, "right", None)
    bottom = getattr(rect, "bottom", None)
    if None in (left, top, right, bottom):
        return None

    left_i = int(left)
    top_i = int(top)
    right_i = int(right)
    bottom_i = int(bottom)
    width = max(0, right_i - left_i)
    height = max(0, bottom_i - top_i)
    return {
        "left": left_i,
        "top": top_i,
        "right": right_i,
        "bottom": bottom_i,
        "width": width,
        "height": height,
        "center_x": int((left_i + right_i) / 2),
        "center_y": int((top_i + bottom_i) / 2),
    }


def _safe_parent_wrapper(wrapper: Any, *, context: str) -> tuple[Any | None, bool]:
    parent = getattr(wrapper, "parent", None)
    if not callable(parent):
        return None, False
    try:
        return parent(), False
    except Exception as exc:
        if _is_com_error(exc):
            _remember_topbar_parent_comerror(context, wrapper, exc)
            return None, True
        raise


def _parent_wrapper(wrapper: Any) -> Any | None:
    parent, _parent_comerror = _safe_parent_wrapper(wrapper, context="parent_wrapper")
    return parent


def _has_menuitem_ancestor(wrapper: Any) -> bool:
    seen: set[int] = set()
    current = _parent_wrapper(wrapper)
    while current is not None:
        marker = id(current)
        if marker in seen:
            break
        seen.add(marker)

        if _control_type(current) == "menuitem":
            return True
        current = _parent_wrapper(current)
    return False


def _menu_items(*, force_refresh: bool = False) -> list[Any]:
    started_at = time.monotonic()
    root = get_main_window()
    with _menu_items_reentrancy_guard(force_refresh=force_refresh) as can_inspect_topbar:
        if not can_inspect_topbar:
            return _query_menu_items_from_root(root, force_refresh=force_refresh)
        topbar_band = _main_window_topbar_band(force_refresh=force_refresh)
        items = _query_menu_items_from_root(root, force_refresh=force_refresh)
    handle = getattr(getattr(root, "element_info", root), "handle", None)
    topbar_visible = 0
    popup_visible = 0
    visible_count = 0
    for item in items:
        if not _is_visible(item):
            continue
        visible_count += 1
        rect = _rectangle_data(item)
        if rect is None:
            continue
        row = {"rectangle": rect, "center_x": rect["center_x"], "center_y": rect["center_y"]}
        topbar_candidate, popup_candidate, _popup_reason = _classify_row_geometry(row, topbar_band)
        if topbar_candidate:
            topbar_visible += 1
        if popup_candidate:
            popup_visible += 1
    logger.info(
        "DBG_MENU_ITEMS_SUMMARY total_items={} visible_items={} topbar_band={} topbar_band_visible_count={} popup_region_visible_count={} force_refresh={} handle={}",
        len(items),
        visible_count,
        _rect_tuple(topbar_band),
        topbar_visible,
        popup_visible,
        force_refresh,
        handle,
    )
    logger.debug("Discovered {} MenuItem controls", len(items))
    _log_phase_timing("_menu_items", started_at, force_refresh=force_refresh, total_items=len(items), visible_items=visible_count)
    return items


def get_main_window() -> Any:
    """Backward-compatible accessor used by tests and helper code."""

    return get_cached_main_window()


def _top_level_menu_items_raw(*, force_refresh: bool = False) -> list[Any]:
    return _top_level_menu_items_from_items(_menu_items(force_refresh=force_refresh))


def list_top_menu_items() -> list[str]:
    started_at = time.monotonic()
    names: list[str] = []
    seen: set[str] = set()

    for item in _top_level_menu_items_raw(force_refresh=True):
        text = _name(item)
        if not text:
            continue
        key = _normalize(text)
        if key in seen:
            continue
        seen.add(key)
        names.append(text)

    logger.info("Top-level menu items (raw): {}", names)
    _log_phase_timing("list_top_menu_items", started_at, count=len(names))
    return names


def list_open_menu_items() -> list[str]:
    names: list[str] = []
    seen: set[str] = set()

    for item in _menu_items():
        if not _is_visible(item):
            continue
        text = _name(item)
        if not text:
            continue

        parent_wrapper = _parent_wrapper(item)
        parent_type = _control_type(parent_wrapper)
        if parent_type not in {"menu", "menuitem"}:
            continue

        key = _normalize(text)
        if key in seen:
            continue
        seen.add(key)
        names.append(text)

    logger.info("Open/visible menu entries: {}", names)
    return names




def _clean_text_candidate(text: Any) -> str:
    return " ".join(str(text or "").replace(" ", " ").split()).strip()


def _safe_window_text(wrapper: Any) -> str:
    getter = getattr(wrapper, "window_text", None)
    if callable(getter):
        try:
            return _clean_text_candidate(getter())
        except Exception:
            return ""
    return ""


def _safe_legacy_text(wrapper: Any) -> str:
    legacy_props = getattr(wrapper, "legacy_properties", None)
    if callable(legacy_props):
        try:
            props = legacy_props() or {}
            for key in ("Name", "Value", "DefaultAction", "Description"):
                value = _clean_text_candidate(props.get(key))
                if value:
                    return value
        except Exception:
            return ""
    iface = getattr(wrapper, "iface_legacy_iaccessible", None)
    if iface is not None:
        for attr in ("accName", "accValue", "accDescription"):
            try:
                value = getattr(iface, attr)(0) if callable(getattr(iface, attr, None)) else getattr(iface, attr, None)
            except Exception:
                value = None
            value = _clean_text_candidate(value)
            if value:
                return value
    return ""


def _rect_intersects(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return not (
        int(first.get("right") or 0) <= int(second.get("left") or 0)
        or int(first.get("left") or 0) >= int(second.get("right") or 0)
        or int(first.get("bottom") or 0) <= int(second.get("top") or 0)
        or int(first.get("top") or 0) >= int(second.get("bottom") or 0)
    )


def _merge_text_fragments(fragments: list[dict[str, Any]], *, rect: dict[str, Any] | None = None) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    ordered = sorted(fragments or [], key=lambda item: (int((item.get("rectangle") or {}).get("left") or 0), int((item.get("rectangle") or {}).get("top") or 0)))
    for fragment in ordered:
        fragment_rect = dict(fragment.get("rectangle") or {})
        if rect and fragment_rect and not _rect_intersects(rect, fragment_rect):
            center = fragment.get("center") or ()
            if len(center) == 2:
                cx, cy = int(center[0]), int(center[1])
                if not (int(rect.get("left") or 0) <= cx <= int(rect.get("right") or 0) and int(rect.get("top") or 0) <= cy <= int(rect.get("bottom") or 0)):
                    continue
            else:
                continue
        text = _clean_text_candidate(fragment.get("text"))
        if not text:
            continue
        key = _normalize(text)
        if key in seen:
            continue
        seen.add(key)
        merged.append(text)
    return " ".join(merged).strip()


def _child_text_fragments(wrapper: Any, *, row_rect: dict[str, Any]) -> list[dict[str, Any]]:
    descendants = getattr(wrapper, "descendants", None)
    if not callable(descendants):
        return []
    fragments: list[dict[str, Any]] = []
    try:
        children = descendants()
    except Exception:
        return []
    for child in children:
        control_type = _control_type(child)
        class_name = _class_name(child)
        if control_type not in {"text", "static"} and _normalize(class_name) not in {"static", "text"}:
            continue
        child_rect = _rectangle_data(child)
        if child_rect is None or not _rect_intersects(row_rect, child_rect):
            continue
        text = _clean_text_candidate(_name(child) or _safe_window_text(child) or _safe_legacy_text(child))
        if not text:
            continue
        fragments.append({
            "text": text,
            "rectangle": {k: child_rect[k] for k in ("left", "top", "right", "bottom")},
            "center": (child_rect["center_x"], child_rect["center_y"]),
            "control_type": control_type,
            "class_name": class_name,
            "source_scope": "child_text",
        })
    return fragments


def _source_priority(raw_sources: list[str], *, popup_priority: bool) -> tuple[int, int]:
    if not raw_sources:
        return (99, 99)
    primary = str(raw_sources[0])
    popup_order = {
        "child_text": 0,
        "fragment_merge": 1,
        "uia_name": 2,
        "window_text": 3,
        "legacy_text": 4,
    }
    default_order = {
        "uia_name": 0,
        "window_text": 1,
        "child_text": 2,
        "fragment_merge": 3,
        "legacy_text": 4,
    }
    order = popup_order if popup_priority else default_order
    return (order.get(primary, 98), len(raw_sources))


def _select_cluster_text_candidate(cluster: list[dict[str, Any]], *, rect: dict[str, int], popup_priority: bool) -> tuple[str, list[str], str, str]:
    candidates: list[dict[str, Any]] = []
    for item in cluster:
        item_text = str(item.get("text") or "").strip()
        if not item_text:
            continue
        raw_sources = [str(source) for source in list(item.get("raw_text_sources") or []) if str(source)] or ["existing_text"]
        confidence = str(item.get("text_confidence") or ("high" if item_text else "none"))
        candidates.append({
            "text": item_text,
            "raw_sources": raw_sources,
            "confidence": confidence,
            "origin": "direct",
        })

    cluster_fragments = []
    for item in cluster:
        for fragment in list(item.get("child_fragments") or []):
            cluster_fragments.append(dict(fragment))
    merged_fragment_text = _merge_text_fragments(cluster_fragments, rect=rect)
    if merged_fragment_text:
        candidates.append({
            "text": merged_fragment_text,
            "raw_sources": ["fragment_merge"],
            "confidence": "medium",
            "origin": "fragment_merge",
        })

    if not candidates:
        return "", [], "none", "none"

    ranked = sorted(
        candidates,
        key=lambda candidate: (
            _source_priority(candidate["raw_sources"], popup_priority=popup_priority),
            -len(candidate["text"]),
        ),
    )
    selected = ranked[0]
    return selected["text"], list(selected["raw_sources"]), selected["confidence"], selected["origin"]


def _popup_row_has_reliable_local_text(row: dict[str, Any]) -> bool:
    raw_sources = [str(source) for source in list(row.get("raw_text_sources") or []) if str(source)]
    if any(source in {"child_text", "fragment_merge", "uia_name", "window_text"} for source in raw_sources):
        return True
    fragments = list(row.get("fragments") or [])
    return any(str(fragment.get("source_scope") or "") == "child_text" for fragment in fragments)


def _adjust_popup_row_text_confidence(row: dict[str, Any], *, row_index: int) -> None:
    if not bool(row.get("popup_candidate") or row.get("popup_priority_candidate")):
        return
    raw_sources = [str(source) for source in list(row.get("raw_text_sources") or []) if str(source)]
    original_confidence = str(row.get("text_confidence") or "none")
    updated_confidence = original_confidence
    if raw_sources and raw_sources[0] == "legacy_text":
        updated_confidence = "medium" if _popup_row_has_reliable_local_text(row) else "low"
    if updated_confidence != original_confidence:
        row["text_confidence"] = updated_confidence
        logger.info(
            "POPUP_ROW_TEXT_CONFIDENCE_ADJUSTED row_index={} source={} old_confidence={} new_confidence={} text={!r}",
            row_index,
            raw_sources[0] if raw_sources else "none",
            original_confidence,
            updated_confidence,
            row.get("text"),
        )


def _reject_repeated_popup_legacy_texts(logical_rows: list[dict[str, Any]]) -> None:
    popup_rows = [row for row in logical_rows if bool(row.get("popup_candidate") or row.get("popup_priority_candidate"))]
    if not popup_rows:
        return
    counts = Counter(
        _normalize(str(row.get("text") or ""))
        for row in popup_rows
        if str(row.get("text") or "").strip() and list(row.get("raw_text_sources") or [None])[0] == "legacy_text"
    )
    if not counts:
        return
    popup_count = len(popup_rows)
    suspicious = {
        text for text, count in counts.items()
        if text and count >= REPEATED_LEGACY_TEXT_MIN_ROWS and (count / popup_count) >= REPEATED_LEGACY_TEXT_MIN_RATIO
    }
    for row_index, row in enumerate(logical_rows):
        text = str(row.get("text") or "").strip()
        normalized = _normalize(text)
        raw_sources = [str(source) for source in list(row.get("raw_text_sources") or []) if str(source)]
        if not text or normalized not in suspicious or not raw_sources or raw_sources[0] != "legacy_text":
            continue
        if _popup_row_has_reliable_local_text(row) or str(row.get("text_confidence") or "none") == "high":
            continue
        logger.warning(
            "TEXT_EXTRACTION_REJECTED_REPEATED_LEGACY_TEXT row_index={} repeated_text={!r} occurrence_count={} popup_row_count={} raw_sources={} rectangle={}",
            row_index,
            text,
            counts[normalized],
            popup_count,
            raw_sources,
            row.get("rectangle"),
        )
        logger.info(
            "POPUP_TEXT_RECOVERY_SOURCE_REJECTED row_index={} source=legacy_text reason=repeated_fallback_text repeated_text={!r}",
            row_index,
            text,
        )
        row["text"] = ""
        row["normalized_text"] = ""
        row["text_confidence"] = "none"
        row["rejected_text_recovery_reason"] = "repeated_legacy_text"


def _popup_noise_rect_band(row: dict[str, Any]) -> tuple[int, int, int, int]:
    rect = dict(row.get("rectangle") or {})
    left = int(rect.get("left") or 0)
    right = int(rect.get("right") or 0)
    width = max(0, right - left)
    height = max(0, int(rect.get("bottom") or 0) - int(rect.get("top") or 0))
    tolerance = max(1, POPUP_NOISE_RECT_TOLERANCE)
    return (
        round(left / tolerance),
        round(right / tolerance),
        round(width / tolerance),
        round(height / tolerance),
    )


def _popup_row_raw_source_pattern(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(source) for source in list(row.get("raw_text_sources") or []) if str(source))


def _popup_row_has_interaction_evidence(row: dict[str, Any]) -> bool:
    evidence = dict(row.get("interaction_evidence") or {})
    evidence_result = str(evidence.get("result_type") or row.get("interaction_result_type") or "")
    return bool(
        evidence_result
        or row.get("invoked")
        or row.get("activated")
        or row.get("probe_result_type")
        or row.get("child_popup_opened")
        or row.get("dialog_opened")
    )


def _suppress_popup_text_noise_duplicates(logical_rows: list[dict[str, Any]]) -> None:
    popup_rows = [row for row in logical_rows if bool(row.get("popup_candidate") or row.get("popup_priority_candidate"))]
    if len(popup_rows) < REPEATED_LEGACY_TEXT_MIN_ROWS:
        return

    duplicate_groups: dict[tuple[str, tuple[str, ...], tuple[int, int, int, int]], list[tuple[int, dict[str, Any]]]] = {}
    text_counts = Counter()
    for row_index, row in enumerate(logical_rows):
        normalized_text = _normalize(str(row.get("text") or ""))
        raw_source_pattern = _popup_row_raw_source_pattern(row)
        if (
            not normalized_text
            or raw_source_pattern != ("legacy_text",)
            or _popup_row_has_reliable_local_text(row)
            or _popup_row_has_interaction_evidence(row)
        ):
            continue
        if not bool(row.get("popup_candidate") or row.get("popup_priority_candidate")):
            continue
        text_counts[normalized_text] += 1
        group_key = (normalized_text, raw_source_pattern, _popup_noise_rect_band(row))
        duplicate_groups.setdefault(group_key, []).append((row_index, row))

    for (normalized_text, raw_source_pattern, rect_band), group in duplicate_groups.items():
        if len(group) < REPEATED_LEGACY_TEXT_MIN_ROWS or text_counts[normalized_text] < REPEATED_LEGACY_TEXT_MIN_ROWS:
            continue
        ranked_group = sorted(
            group,
            key=lambda item: (
                1 if str(item[1].get("text_confidence") or "none") == "medium" else 0,
                len(list(item[1].get("fragments") or [])),
                -item[0],
            ),
            reverse=True,
        )
        kept_row_index, _kept_row = ranked_group[0]
        for row_index, row in ranked_group[1:]:
            row["popup_noise_suppressed"] = True
            row["suppressed_as_duplicate_of"] = kept_row_index
            row["rejected_text_recovery_reason"] = "legacy_text_duplicate_noise"
            logger.info(
                "LEGACY_TEXT_DUPLICATE_SUPPRESSED row_index={} kept_row_index={} repeated_text={!r} raw_sources={} rect_band={} rectangle={}",
                row_index,
                kept_row_index,
                row.get("text"),
                list(raw_source_pattern),
                rect_band,
                row.get("rectangle"),
            )
            logger.info(
                "POPUP_TEXT_NOISE_REJECTED row_index={} reason=repeated_legacy_text_duplicate normalized_text={} source_pattern={} interaction_evidence=false",
                row_index,
                normalized_text,
                list(raw_source_pattern),
            )


def _extract_text_with_fallbacks(wrapper: Any, *, row_rect: dict[str, Any]) -> tuple[str, list[str], str, list[dict[str, Any]]]:
    source_values = [
        ("uia_name", _clean_text_candidate(_name(wrapper)), "high"),
        ("window_text", _safe_window_text(wrapper), "high"),
    ]
    raw_sources: list[str] = []
    for label, value, confidence in source_values:
        if value:
            raw_sources.append(label)
            return value, raw_sources, confidence, []
    child_fragments = _child_text_fragments(wrapper, row_rect=row_rect)
    child_text = _merge_text_fragments(child_fragments, rect=row_rect)
    if child_text:
        return child_text, ["child_text"], "medium", child_fragments
    legacy_text = _safe_legacy_text(wrapper)
    if legacy_text:
        return legacy_text, ["legacy_text"], "medium", child_fragments
    return "", [], "none", child_fragments
def _is_separator_by_geometry(rect: dict[str, int]) -> bool:
    width = rect["width"]
    height = rect["height"]
    return height <= 3 or width <= 6 or (height <= 5 and width >= 40)




def _menu_row_from_wrapper(item: Any, *, source_scope: str, topbar_band: dict[str, int] | None) -> dict[str, Any] | None:
    if not _is_visible(item):
        return None

    rect = _rectangle_data(item)
    if rect is None:
        return None

    info = getattr(item, "element_info", item)
    row_rect = {
        "left": rect["left"],
        "top": rect["top"],
        "right": rect["right"],
        "bottom": rect["bottom"],
    }
    extracted_text, raw_text_sources, text_confidence, child_fragments = _extract_text_with_fallbacks(item, row_rect=row_rect)
    if extracted_text and raw_text_sources and raw_text_sources[0] != "uia_name":
        logger.info("TEXT_EXTRACTION_FALLBACK_USED source={} confidence={} rect={}", raw_text_sources[0], text_confidence, row_rect)
    elif not extracted_text:
        logger.warning("TEXT_EXTRACTION_FAILED source_scope={} rect={}", source_scope, row_rect)
    enabled_value = getattr(info, "enabled", None)
    if enabled_value is None:
        is_enabled = getattr(item, "is_enabled", None)
        if callable(is_enabled):
            try:
                enabled_value = is_enabled()
            except Exception:
                enabled_value = None
    row = {
        "text": extracted_text,
        "normalized_text": _normalize(extracted_text),
        "raw_text_sources": raw_text_sources,
        "text_confidence": text_confidence,
        "control_type": getattr(getattr(item, "element_info", item), "control_type", None),
        "class_name": _class_name(item),
        "rectangle": {
            "left": rect["left"],
            "top": rect["top"],
            "right": rect["right"],
            "bottom": rect["bottom"],
        },
        "width": rect["width"],
        "height": rect["height"],
        "center_x": rect["center_x"],
        "center_y": rect["center_y"],
        "is_separator": _is_separator_row(text=extracted_text, rect=row_rect, fragments=child_fragments),
        "source_scope": source_scope,
        "process_id": getattr(info, "process_id", None),
        "native_handle": getattr(info, "handle", None),
        "fragments": child_fragments,
        "enabled": enabled_value,
    }
    row["recent_project_entry"] = _is_recent_project_entry_text(extracted_text)
    topbar_candidate, popup_candidate, popup_reason = _classify_row_geometry(row, topbar_band)
    row["topbar_candidate"] = topbar_candidate
    row["popup_candidate"] = popup_candidate
    row["popup_reason"] = popup_reason
    return row


def _menu_like_controls_from_main_window() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    topbar_parent_state = _consume_topbar_parent_error_state()
    topbar_band = _main_window_topbar_band()
    for item in _menu_items():
        row = _menu_row_from_wrapper(item, source_scope="main_window", topbar_band=topbar_band)
        if row is None:
            continue
        rows.append(row)
        _log_popup_fragment("DBG_MENU_FRAGMENT_MAIN_WINDOW", row)
    POPUP_LOG_STATS["source_counts"]["main_window"] += len(rows)
    logger.debug("DBG_MENU_FRAGMENT_SOURCE_SUMMARY source_scope=main_window count={}", len(rows))
    return rows


def _menu_like_controls_from_global_process_scan() -> list[dict[str, Any]]:
    try:
        from pywinauto import Desktop
    except Exception:
        return []

    main_window = get_cached_main_window()
    process_id = main_window.process_id()
    desktop = Desktop(backend="uia")
    topbar_band = _main_window_topbar_band()

    rows: list[dict[str, Any]] = []
    for window in desktop.windows(top_level_only=True):
        try:
            if window.process_id() != process_id:
                continue
            descendants = getattr(window, "descendants", None)
            if not callable(descendants):
                continue
            for item in descendants(control_type="MenuItem"):
                row = _menu_row_from_wrapper(item, source_scope="global_process_scan", topbar_band=topbar_band)
                if row is None:
                    continue
                rows.append(row)
                _log_popup_fragment("DBG_MENU_FRAGMENT_GLOBAL_SCAN", row)
        except Exception:
            continue
    POPUP_LOG_STATS["source_counts"]["global_process_scan"] += len(rows)
    logger.debug("DBG_MENU_FRAGMENT_SOURCE_SUMMARY source_scope=global_process_scan count={} process_id={}", len(rows), process_id)
    return rows


def _snapshot_keys(rows: list[dict[str, Any]]) -> set[tuple[str, str, str, str, str]]:
    keys: set[tuple[str, str, str, str, str]] = set()
    for row in rows:
        rect = row.get("rectangle") or {}
        rect_key = f"({rect.get('left')},{rect.get('top')})-({rect.get('right')},{rect.get('bottom')})"
        keys.add(
            (
                row.get("normalized_text", ""),
                _normalize(str(row.get("control_type", ""))),
                _normalize(str(row.get("class_name", ""))),
                rect_key,
                row.get("source_scope", ""),
            )
        )
    return keys


def capture_menu_popup_snapshot() -> list[dict[str, Any]]:
    """Capture current menu-like controls from main window and global process scans."""

    started_at = time.monotonic()
    options = diagnostic_options()
    main_rows = _menu_like_controls_from_main_window()
    global_rows = [] if options.disable_global_process_scan_rows else _menu_like_controls_from_global_process_scan()
    merged = main_rows + global_rows
    topbar_band = _main_window_topbar_band()
    topbar_parent_state = _consume_topbar_parent_error_state()
    seen: set[tuple[int, int, int, int, str, str, str]] = set()
    unique_rows: list[dict[str, Any]] = []

    for row in merged:
        rect = row["rectangle"]
        key = (
            rect["left"],
            rect["top"],
            rect["right"],
            rect["bottom"],
            row["normalized_text"],
            _normalize(str(row["class_name"])),
            row["source_scope"],
        )
        if key in seen:
            POPUP_LOG_STATS["dedupe"]["deduplicated"] += 1
            logger.debug("DBG_POPUP_ROW_DEDUPE rect={} normalized_text={} class_name={} source_scope={} deduplicated=True", rect, row["normalized_text"], row["class_name"], row["source_scope"])
            continue
        seen.add(key)
        POPUP_LOG_STATS["dedupe"]["kept"] += 1
        logger.debug("DBG_POPUP_ROW_DEDUPE rect={} normalized_text={} class_name={} source_scope={} deduplicated=False", rect, row["normalized_text"], row["class_name"], row["source_scope"])
        row["appeared_after_popup_open"] = False
        unique_rows.append(row)

    resolved_topbar_band = _resolved_topbar_band(unique_rows, topbar_band)
    if topbar_parent_state.get("active"):
        logger.info(
            "POPUP_SNAPSHOT_COMSAFE_RECOVERY contexts={} parent_comerror_count={} topbar_band={} recovered_rows={}",
            topbar_parent_state.get("contexts"),
            topbar_parent_state.get("count"),
            _rect_tuple(resolved_topbar_band),
            len(unique_rows),
        )
    if resolved_topbar_band is not None and str(resolved_topbar_band.get("_fallback_mode") or "") == "geometry_only":
        logger.info(
            "TOPBAR_GEOMETRY_FALLBACK_USED context=capture_menu_popup_snapshot topbar_band={} unique_rows={}",
            _rect_tuple(resolved_topbar_band),
            len(unique_rows),
        )
    vertical_popup_override_keys, vertical_popup_diag = _detect_empty_text_vertical_popup_cluster(unique_rows, resolved_topbar_band)
    topbar_like_count = 0
    popup_like_count = 0
    empty_text_count = 0
    for row in unique_rows:
        topbar_candidate, popup_candidate, popup_reason = _classify_row_geometry(
            row,
            resolved_topbar_band,
            vertical_popup_override_keys=vertical_popup_override_keys,
        )
        row["topbar_candidate"] = topbar_candidate
        row["popup_candidate"] = popup_candidate
        row["popup_reason"] = popup_reason
        if topbar_candidate:
            topbar_like_count += 1
        if popup_candidate:
            popup_like_count += 1
        if not str(row.get("text") or "").strip():
            empty_text_count += 1
    POPUP_LOG_STATS["snapshot_count"] += 1
    POPUP_LOG_STATS["topbar_like"] += topbar_like_count
    POPUP_LOG_STATS["popup_like"] += popup_like_count
    POPUP_LOG_STATS["empty_text"] += empty_text_count
    logger.info(
        "POPUP_SNAPSHOT_SUMMARY main_window_fragments={} global_scan_fragments={} deduped_fragments={} topbar_like={} popup_like={} empty_text={} topbar_band={} empty_text_vertical_cluster_detected={} accepted_popup_rows={} popup_heuristic={}",
        len(main_rows),
        len(global_rows),
        len(unique_rows),
        topbar_like_count,
        popup_like_count,
        empty_text_count,
        _rect_tuple(resolved_topbar_band),
        vertical_popup_diag.get("detected"),
        vertical_popup_diag.get("accepted_rows"),
        vertical_popup_diag.get("reason"),
    )
    logger.debug("Captured menu snapshot rows={}", len(unique_rows))
    _log_phase_timing("capture_menu_popup_snapshot", started_at, main_rows=len(main_rows), global_rows=len(global_rows), unique_rows=len(unique_rows), diagnostic_fast_mode=options.diagnostic_fast_mode)
    return unique_rows


def _reject_popup_candidate_reason(
    entry: dict[str, Any],
    top_level_rects: set[tuple[int, int, int, int]],
    top_level_texts: set[str],
    *,
    permissive: bool = False,
) -> str | None:
    rect = entry.get("rectangle") or {}
    left = int(rect.get("left", 0))
    top = int(rect.get("top", 0))
    right = int(rect.get("right", 0))
    bottom = int(rect.get("bottom", 0))
    width = int(entry.get("width") or (right - left))
    height = int(entry.get("height") or (bottom - top))

    if right <= left or bottom <= top:
        return "non-positive rectangle dimensions"
    if width <= 0 or height <= 0:
        return "zero-sized row"
    if width < 2:
        return "width below minimum threshold"
    if height < 1:
        return "height below minimum threshold"

    rect_key = (left, top, right, bottom)
    normalized_text = _normalize(str(entry.get("text", "")))
    if rect_key in top_level_rects and normalized_text in top_level_texts and normalized_text:
        return "identical to top menu bar item"

    if not permissive:
        return None
    return None


def _structured_popup_rows_from_snapshots(
    before_rows: list[dict[str, Any]],
    after_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract structured popup rows by diffing two menu snapshots."""

    before_keys = _snapshot_keys(before_rows)
    after_keys = _snapshot_keys(after_rows)
    new_keys = after_keys - before_keys

    top_level_rects = {
        (rect["left"], rect["top"], rect["right"], rect["bottom"])
        for item in _top_level_menu_items_raw()
        for rect in [_rectangle_data(item)]
        if rect is not None
    }

    top_level_texts = {_normalize(_name(item)) for item in _top_level_menu_items_raw() if _normalize(_name(item))}

    popup_candidates: list[dict[str, Any]] = []
    for row in after_rows:
        rect = row["rectangle"]
        row_key = (
            row["normalized_text"],
            _normalize(str(row.get("control_type", ""))),
            _normalize(str(row.get("class_name", ""))),
            f"({rect['left']},{rect['top']})-({rect['right']},{rect['bottom']})",
            row["source_scope"],
        )
        row["appeared_after_popup_open"] = row_key in new_keys
        if not row["appeared_after_popup_open"]:
            continue
        rejection_reason = _reject_popup_candidate_reason(row, top_level_rects, top_level_texts)
        if rejection_reason is not None:
            logger.info(
                "Rejected popup row: rect={} text={!r} scope={} control_type={} reason={}",
                row.get("rectangle"),
                row.get("text", ""),
                row.get("source_scope", ""),
                row.get("control_type", ""),
                rejection_reason,
            )
            continue
        popup_candidates.append(row)

    if not popup_candidates and new_keys:
        logger.info("Strict popup filtering returned 0 rows; entering permissive fallback mode")
        seen_fallback: set[tuple[tuple[int, int, int, int], str, str]] = set()
        for row in after_rows:
            rect = row["rectangle"]
            row_key = (
                row["normalized_text"],
                _normalize(str(row.get("control_type", ""))),
                _normalize(str(row.get("class_name", ""))),
                f"({rect['left']},{rect['top']})-({rect['right']},{rect['bottom']})",
                row["source_scope"],
            )
            if row_key not in new_keys:
                continue

            rejection_reason = _reject_popup_candidate_reason(row, top_level_rects, top_level_texts, permissive=True)
            if rejection_reason is not None:
                logger.debug(
                    "Rejected popup row: rect={} text={!r} scope={} control_type={} reason={}",
                    row.get("rectangle"),
                    row.get("text", ""),
                    row.get("source_scope", ""),
                    row.get("control_type", ""),
                    rejection_reason,
                )
                continue

            rect = row["rectangle"]
            dedupe_key = (
                (rect["left"], rect["top"], rect["right"], rect["bottom"]),
                str(row.get("text", "")),
                str(row.get("source_scope", "")),
            )
            if dedupe_key in seen_fallback:
                logger.debug(
                    "Rejected popup row: rect={} text={!r} scope={} control_type={} reason={}",
                    row.get("rectangle"),
                    row.get("text", ""),
                    row.get("source_scope", ""),
                    row.get("control_type", ""),
                    "exact duplicate in permissive fallback",
                )
                continue
            seen_fallback.add(dedupe_key)
            popup_candidates.append(row)

    if not popup_candidates:
        logger.debug(
            "Structured popup rows: before snapshot row count={} after snapshot row count={} structured row count=0",
            len(before_rows),
            len(after_rows),
        )
        return []

    popup_candidates.sort(key=lambda item: (item["rectangle"]["top"], item["rectangle"]["left"]))

    source_preference = {"main_window": 0, "global_process_scan": 1}
    deduped_by_visual_identity: dict[tuple[tuple[int, int, int, int], str, str], dict[str, Any]] = {}
    for candidate in popup_candidates:
        rect = candidate["rectangle"]
        identity_key = (
            (rect["left"], rect["top"], rect["right"], rect["bottom"]),
            _normalize(str(candidate.get("text", ""))),
            _normalize(str(candidate.get("control_type", ""))),
        )

        existing = deduped_by_visual_identity.get(identity_key)
        if existing is None:
            deduped_by_visual_identity[identity_key] = candidate
            logger.debug(
                "Popup row dedupe: rect={} text={!r} control_type={} chosen preferred source={}",
                candidate.get("rectangle"),
                candidate.get("text", ""),
                candidate.get("control_type", ""),
                candidate.get("source_scope", ""),
            )
            continue

        existing_rank = source_preference.get(str(existing.get("source_scope", "")), 999)
        candidate_rank = source_preference.get(str(candidate.get("source_scope", "")), 999)
        if candidate_rank < existing_rank:
            deduped_by_visual_identity[identity_key] = candidate

        preferred = deduped_by_visual_identity[identity_key]
        logger.debug(
            "Popup row dedupe: rect={} text={!r} control_type={} chosen preferred source={} dropped source={}",
            preferred.get("rectangle"),
            preferred.get("text", ""),
            preferred.get("control_type", ""),
            preferred.get("source_scope", ""),
            candidate.get("source_scope", "") if preferred is existing else existing.get("source_scope", ""),
        )

    deduped_fragments = sorted(
        deduped_by_visual_identity.values(),
        key=lambda item: (item["rectangle"]["top"], item["rectangle"]["left"]),
    )

    filtered = _group_popup_fragments_into_logical_rows(deduped_fragments)
    for idx, entry in enumerate(filtered):
        entry["index"] = idx

    logger.debug(
        "Structured popup rows: before snapshot row count={} after snapshot row count={} structured row count={} deduped fragment count={} logical row count={}",
        len(before_rows),
        len(after_rows),
        len(popup_candidates),
        len(deduped_fragments),
        len(filtered),
    )
    return filtered


def _overlap_ratio_by_min_height(first: dict[str, Any], second: dict[str, Any]) -> float:
    first_top = int(first["rectangle"]["top"])
    first_bottom = int(first["rectangle"]["bottom"])
    second_top = int(second["rectangle"]["top"])
    second_bottom = int(second["rectangle"]["bottom"])

    overlap_height = max(0, min(first_bottom, second_bottom) - max(first_top, second_top))
    min_height = max(1, min(first_bottom - first_top, second_bottom - second_top))
    return overlap_height / min_height


def _belongs_to_same_logical_row(first: dict[str, Any], second: dict[str, Any]) -> bool:
    overlap_ratio = _overlap_ratio_by_min_height(first, second)
    if overlap_ratio >= 0.5:
        return True

    center_distance = abs(int(first["center_y"]) - int(second["center_y"]))
    first_height = max(1, int(first["height"]))
    second_height = max(1, int(second["height"]))
    center_threshold = max(6, int(min(first_height, second_height) * 0.5))
    return center_distance <= center_threshold


def _group_popup_fragments_into_logical_rows(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not fragments:
        return []

    ordered = sorted(fragments, key=lambda item: (item["rectangle"]["top"], item["rectangle"]["left"]))
    clusters: list[list[dict[str, Any]]] = []

    for fragment in ordered:
        matched_cluster: list[dict[str, Any]] | None = None
        for cluster in clusters:
            if any(_belongs_to_same_logical_row(fragment, member) for member in cluster):
                matched_cluster = cluster
                break

        if matched_cluster is None:
            clusters.append([fragment])
            continue

        matched_cluster.append(fragment)

    logical_rows: list[dict[str, Any]] = []
    for row_index, cluster in enumerate(clusters):
        left = min(int(item["rectangle"]["left"]) for item in cluster)
        top = min(int(item["rectangle"]["top"]) for item in cluster)
        right = max(int(item["rectangle"]["right"]) for item in cluster)
        bottom = max(int(item["rectangle"]["bottom"]) for item in cluster)
        width = max(0, right - left)
        height = max(0, bottom - top)

        texts = [str(item.get("text", "")) for item in cluster]
        representative = cluster[0]
        popup_priority = any(bool(item.get("popup_candidate")) for item in cluster) and not any(bool(item.get("topbar_candidate")) for item in cluster)
        cluster_fragments = [
            {
                "rectangle": dict(item.get("rectangle") or {}),
                "text": item.get("text", ""),
                "control_type": item.get("control_type", ""),
                "source_scope": item.get("source_scope", ""),
                "class_name": item.get("class_name", ""),
                "center": (int(item.get("center_x") or 0), int(item.get("center_y") or 0)),
                "process_id": item.get("process_id"),
                "native_handle": item.get("native_handle"),
                "topbar_candidate": bool(item.get("topbar_candidate")),
                "popup_candidate": bool(item.get("popup_candidate")),
                "raw_text_sources": list(item.get("raw_text_sources") or []),
                "text_confidence": item.get("text_confidence"),
            }
            for item in cluster
        ]
        representative_text, raw_text_sources, text_confidence, selected_origin = _select_cluster_text_candidate(
            cluster,
            rect={"left": left, "top": top, "right": right, "bottom": bottom},
            popup_priority=popup_priority,
        )
        if popup_priority:
            if representative_text:
                logger.info(
                    "POPUP_TEXT_RECOVERY_SOURCE_SELECTED row_index={} source={} confidence={} text={!r}",
                    row_index,
                    raw_text_sources[0] if raw_text_sources else selected_origin,
                    text_confidence,
                    representative_text,
                )
            else:
                logger.info(
                    "POPUP_TEXT_RECOVERY_SOURCE_REJECTED row_index={} source=none reason=no_viable_text_candidate",
                    row_index,
                )

        source_scope_summary = sorted({str(item.get("source_scope", "")) for item in cluster})
        row_class_summary = sorted({str(item.get("class_name", "")) for item in cluster})
        logical_rows.append(
            {
                "text": representative_text,
                "normalized_text": _normalize(representative_text),
                "raw_text_sources": raw_text_sources,
                "text_confidence": text_confidence,
                "control_type": representative.get("control_type") or "MenuRow",
                "class_name": representative.get("class_name", ""),
                "rectangle": {
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                },
                "width": width,
                "height": height,
                "center_x": int((left + right) / 2),
                "center_y": int((top + bottom) / 2),
                "is_separator": all(bool(item.get("is_separator")) for item in cluster),
                "source_scope": representative.get("source_scope", ""),
                "appeared_after_popup_open": any(bool(item.get("appeared_after_popup_open")) for item in cluster),
                "topbar_candidate": False,
                "popup_candidate": False,
                "popup_reason": None,
                "popup_priority_candidate": popup_priority,
                "source_scope_summary": source_scope_summary,
                "row_class_summary": row_class_summary,
                "fragment_texts": texts,
                "fragments": cluster_fragments,
                "child_fragments": cluster_fragments,
                "enabled": (
                    False
                    if any(item.get("enabled") is False for item in cluster)
                    else True
                    if any(item.get("enabled") is True for item in cluster)
                    else None
                ),
                "recent_project_entry": _is_recent_project_entry_text(representative_text),
            }
        )

    resolved_topbar_band = _resolved_topbar_band(logical_rows, _main_window_topbar_band())
    vertical_popup_override_keys, _vertical_popup_diag = _detect_empty_text_vertical_popup_cluster(logical_rows, resolved_topbar_band)
    for row_index, row in enumerate(logical_rows):
        topbar_candidate, popup_candidate, popup_reason = _classify_row_geometry(
            row,
            resolved_topbar_band,
            vertical_popup_override_keys=vertical_popup_override_keys,
        )
        row["topbar_candidate"] = topbar_candidate
        row["popup_candidate"] = popup_candidate
        row["popup_reason"] = popup_reason
        _adjust_popup_row_text_confidence(row, row_index=row_index)
        logger.info(
            "DBG_MENU_GROUP_ROW row_index={} representative_text={!r} fragment_count={} fragment_texts={} row_rectangle={} source_scope_summary={} row_class_summary={} topbar_like={} popup_like={} popup_reason={}",
            row_index,
            row["text"],
            len(row["fragments"]),
            row["fragment_texts"],
            row["rectangle"],
            row["source_scope_summary"],
            row["row_class_summary"],
            topbar_candidate,
            popup_candidate,
            popup_reason,
        )
    _reject_repeated_popup_legacy_texts(logical_rows)
    _suppress_popup_text_noise_duplicates(logical_rows)
    logical_rows.sort(key=lambda item: (item["rectangle"]["top"], item["rectangle"]["left"]))
    return logical_rows


def open_top_menu_and_capture_popup_state(title: str) -> dict[str, Any]:
    """Open a top menu once and return popup snapshots plus structured rows."""

    main_window = prepare_main_window_for_menu_interaction()
    focus_status = "focus_ok"
    action_suffix = _normalize(title) or "top_menu"
    try:
        main_window = ensure_main_window_foreground_before_click(action_label=f"open_top_menu:{action_suffix}")
    except Exception as exc:
        focus_status = "focus_failed"
        return {
            "before_snapshot": [],
            "after_snapshot": [],
            "rows": [],
            "popup_open": False,
            "top_menu_click_count": 0,
            "process_id": None,
            "deduped_fragment_count": 0,
            "status": "failed_focus",
            "error": str(exc),
            "focus_status": focus_status,
            "clicked_target": title,
            "system_menu_opened": False,
        }

    item = find_top_menu_item(title)

    before_rows = capture_menu_popup_snapshot()
    process_id = None
    process_id_getter = getattr(main_window, "process_id", None)
    if callable(process_id_getter):
        try:
            process_id = int(process_id_getter())
        except Exception:
            process_id = None
    top_menu_click_count = 0
    click_mode = "object"
    item_rect = item.rectangle()
    point = (
        int((int(item_rect.left) + int(item_rect.right)) / 2),
        int((int(item_rect.top) + int(item_rect.bottom)) / 2),
    )
    safe_point = _coerce_point_outside_forbidden_top_left_zone(main_window, point, target_rect=item_rect)
    try:
        if safe_point == point:
            item.click_input()
        else:
            click_mode = "adjusted_coordinate"
            _click_main_window_at_point(main_window, safe_point, log_label=f"Adjusted top menu click used title={title}", target_rect=item_rect)
        top_menu_click_count += 1
    except Exception as exc:
        logger.warning("Top menu item '{}' click_input() failed: {}", title, exc)
        logger.warning("using_coordinate_fallback_for_top_menu top_menu={}", title)
        click_mode = "coordinate_fallback"
        main_window = ensure_main_window_foreground_before_click(action_label=f"open_top_menu_fallback:{action_suffix}")
        _click_by_relative_rect_center(item, main_window)
        top_menu_click_count += 1

    time.sleep(max(0.02, DEFAULT_UI_DELAY / 4))
    try:
        _validate_post_menu_open_foreground(main_window, title=title)
    except Exception as exc:
        return {
            "before_snapshot": before_rows,
            "after_snapshot": [],
            "rows": [],
            "popup_open": False,
            "top_menu_click_count": top_menu_click_count,
            "process_id": process_id,
            "deduped_fragment_count": 0,
            "status": str(exc),
            "error": str(exc),
            "focus_status": focus_status,
            "clicked_target": title,
            "system_menu_opened": "system_menu" in str(exc),
            "click_mode": click_mode,
        }

    wait_for_new_menu_popup(_snapshot_keys(before_rows))
    after_rows = capture_menu_popup_snapshot()
    popup_open = did_any_new_menu_popup_appear(_snapshot_keys(before_rows), _snapshot_keys(after_rows))
    structured_rows = _structured_popup_rows_from_snapshots(before_rows, after_rows)
    deduped_fragment_count = sum(len(row.get("fragments", [])) or 1 for row in structured_rows)

    logger.info(
        "Menu open transitions: before snapshot row count={} after snapshot row count={} structured row count={} top menu clicked more than once={}",
        len(before_rows),
        len(after_rows),
        len(structured_rows),
        top_menu_click_count > 1,
    )

    global _LAST_MENU_SNAPSHOT_BEFORE_OPEN
    _LAST_MENU_SNAPSHOT_BEFORE_OPEN = _snapshot_keys(before_rows)
    return {
        "before_snapshot": before_rows,
        "after_snapshot": after_rows,
        "rows": structured_rows,
        "popup_open": popup_open,
        "top_menu_click_count": top_menu_click_count,
        "process_id": process_id,
        "deduped_fragment_count": deduped_fragment_count,
        "status": "success_popup_opened" if popup_open and structured_rows else "failed_no_visible_change",
        "focus_status": focus_status,
        "clicked_target": title,
        "system_menu_opened": False,
        "click_mode": click_mode,
    }


def open_file_menu_and_capture_popup_state() -> dict[str, Any]:
    """Open ``Fájl`` once and return popup snapshots plus structured rows."""

    return open_top_menu_and_capture_popup_state("Fájl")


def click_structured_popup_row(rows: list[dict[str, Any]], index: int) -> dict[str, Any]:
    """Click one already-discovered popup row without reopening the top menu."""

    if index < 0:
        raise ValueError("index must be >= 0")
    if not rows:
        raise ValueError("popup rows are empty; cannot click submenu row")
    if index >= len(rows):
        raise IndexError(f"Requested popup index {index}, but only {len(rows)} entries exist")

    selected = rows[index]
    if selected.get("is_separator"):
        raise ValueError(f"Requested popup index {index} is a separator and cannot be clicked")

    ensure_main_window_foreground_before_click(
        action_label=f"click_structured_popup_row[{index}]",
        allow_dialog=True,
        allow_stale_wrapper_refresh=True,
    )
    x = int(selected["center_x"])
    y = int(selected["center_y"])
    _mouse_click((x, y))
    logger.info(
        "Popup row click: selected row index={} selected row rectangle={} top menu clicked more than once={}",
        index,
        selected.get("rectangle"),
        False,
    )
    return selected


def list_open_menu_items_structured() -> list[dict[str, Any]]:
    """Return popup submenu entries in deterministic visual order using snapshot diff."""

    state = open_file_menu_and_capture_popup_state()
    return state["rows"]


def find_top_menu_item(title: str) -> Any:
    wanted = _normalize(title)
    matches = [item for item in _top_level_menu_items_raw() if _normalize(_name(item)) == wanted]
    if matches:
        return next((match for match in matches if _is_visible(match)), matches[0])
    raise LookupError(f"Top menu item '{title}' was not found")


def _menu_snapshot() -> set[tuple[str, str, str, str, str]]:
    rows = capture_menu_popup_snapshot()
    return _snapshot_keys(rows)


def did_any_new_menu_popup_appear(
    before_snapshot: set[tuple[str, str, str, str, str]],
    after_snapshot: set[tuple[str, str, str, str, str]],
) -> bool:
    new_items = after_snapshot - before_snapshot
    logger.debug(
        "Menu popup snapshot diff: before={} after={} new={}",
        len(before_snapshot),
        len(after_snapshot),
        len(new_items),
    )
    return bool(new_items)


def wait_for_new_menu_popup(
    before_snapshot: set[tuple[str, str, str, str, str]],
    *,
    timeout: float = POPUP_WAIT_TIMEOUT,
    poll_interval: float = POPUP_WAIT_POLL_INTERVAL,
) -> set[tuple[str, str, str, str, str]]:
    deadline = time.monotonic() + max(timeout, poll_interval)
    latest_snapshot = before_snapshot
    while time.monotonic() <= deadline:
        latest_snapshot = _menu_snapshot()
        if did_any_new_menu_popup_appear(before_snapshot, latest_snapshot):
            return latest_snapshot
        time.sleep(poll_interval)
    return latest_snapshot


def wait_for_popup_to_close(
    *,
    timeout: float = POPUP_CLOSE_TIMEOUT,
    poll_interval: float = POPUP_WAIT_POLL_INTERVAL,
) -> bool:
    deadline = time.monotonic() + max(timeout, poll_interval)
    while time.monotonic() <= deadline:
        if not capture_menu_popup_snapshot():
            return True
        time.sleep(poll_interval)
    return False


def _click_by_relative_rect_center(item: Any, main_window: Any) -> None:
    rect = item.rectangle()
    point = (int((int(rect.left) + int(rect.right)) / 2), int((int(rect.top) + int(rect.bottom)) / 2))

    ensure_main_window_foreground_before_click(action_label="relative_menu_click")
    _click_main_window_at_point(main_window, point, log_label="Fallback menu click used", target_rect=rect)


def click_top_menu_item(title: str) -> None:
    if _is_system_menu_title(title):
        raise ValueError("system menu must be opened via open_system_menu()")
    topbar_band = _main_window_topbar_band()
    if topbar_band is not None and str(topbar_band.get("_fallback_mode") or "") == "geometry_only":
        logger.info("TOPBAR_GEOMETRY_FALLBACK_USED context=click_top_menu_item title={} topbar_band={}", title, _rect_tuple(topbar_band))
    main_window = prepare_main_window_for_menu_interaction()
    main_window = ensure_main_window_foreground_before_click(action_label=f"click_top_menu_item:{title}")
    logger.info("click_top_menu_item('{}'): foreground_before_click={}", title, describe_foreground_window())

    item = find_top_menu_item(title)
    global _LAST_MENU_SNAPSHOT_BEFORE_OPEN
    before_snapshot = _menu_snapshot()
    _LAST_MENU_SNAPSHOT_BEFORE_OPEN = before_snapshot

    item_rect = item.rectangle()
    point = (
        int((int(item_rect.left) + int(item_rect.right)) / 2),
        int((int(item_rect.top) + int(item_rect.bottom)) / 2),
    )
    safe_point = _coerce_point_outside_forbidden_top_left_zone(main_window, point, target_rect=item_rect)

    try:
        if safe_point == point:
            item.click_input()
        else:
            _click_main_window_at_point(main_window, safe_point, log_label=f"Adjusted top menu click used title={title}", target_rect=item_rect)
    except Exception as exc:
        logger.warning("Top menu item '{}' click_input() failed: {}", title, exc)

    _validate_post_menu_open_foreground(main_window, title=title)
    after_snapshot = wait_for_new_menu_popup(before_snapshot)
    if did_any_new_menu_popup_appear(before_snapshot, after_snapshot):
        _log_top_menu_popup_diagnostics(title, item_rect, topbar_band)
        return

    _click_by_relative_rect_center(item, main_window)
    fallback_snapshot = wait_for_new_menu_popup(before_snapshot)
    if did_any_new_menu_popup_appear(before_snapshot, fallback_snapshot):
        _log_top_menu_popup_diagnostics(title, item_rect, topbar_band)
        return

    raise RuntimeError(f"Top menu item '{title}' click attempts did not open a menu popup")


def click_open_menu_item_by_index(index: int) -> dict[str, Any]:
    if index < 0:
        raise ValueError("index must be >= 0")

    prepare_main_window_for_menu_interaction()
    popup_state = open_file_menu_and_capture_popup_state()
    popup_rows = popup_state["rows"]
    if popup_rows:
        return click_structured_popup_row(popup_rows, index)

    logger.info("Popup rows empty after open; retrying open/capture for index={}", index)
    retry_rows = open_file_menu_and_capture_popup_state()["rows"]
    return click_structured_popup_row(retry_rows, index)
