"""Persistent runtime states for WinWatt's active MDI catalog contexts.

The legacy mapper distinguishes only whether a project is open.  This module
adds a fail-closed state layer keyed by the active MDI child title.  A state
transition records a UI screenshot, the complete native top-menu tree, a
value-free MDI identity, and a structural diff to the immediately preceding
state.  It never invokes a command in an MDI menu.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from winwatt_automation.live_ui.app_connector import (
    ensure_main_window_foreground_before_click,
    get_main_window,
    prepare_main_window_for_menu_interaction,
)
from winwatt_automation.live_ui.menu_helpers import (
    click_structured_popup_row,
    open_top_menu_and_capture_popup_state,
)
from winwatt_automation.live_ui.native_menu import enumerate_native_menu
from winwatt_automation.runtime_mapping.context_guard import active_mdi_title, resolve_live_dynamic_context
from winwatt_automation.runtime_mapping.program_mapper import capture_state_snapshot


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "runtime_maps" / "mdi_runtime_states_9_60"
ROOMS_CATALOG_INDEX = 3
ROOMS_TITLE = "Helyis\u00e9gek"
ELEMENT_MENU_TITLE = "Elem"
CREATE_ELEMENT_VISIBLE_CAPTION = "L\u00e9trehoz..."


def _slug(value: str) -> str:
    normalized = value.casefold().replace("\u00e1", "a").replace("\u00e9", "e").replace("\u00ed", "i")
    normalized = normalized.replace("\u00f3", "o").replace("\u00f6", "o").replace("\u0151", "o")
    normalized = normalized.replace("\u00fa", "u").replace("\u00fc", "u").replace("\u0171", "u")
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_") or "unknown"


def _top_menu_structure(menu: dict[str, Any]) -> list[dict[str, Any]]:
    """Preserve order, enabled status and child IDs; captions may be owner-drawn."""
    def project(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "index": item.get("index"),
            "command_id": item.get("command_id"),
            "caption": item.get("caption") if item.get("caption_reliable") else None,
            "caption_reliable": bool(item.get("caption_reliable")),
            "enabled": item.get("enabled"),
            "children": [project(child) for child in item.get("children", [])],
        }
    return [project(item) for item in menu.get("items", [])]


def _structural_signature(menu: dict[str, Any]) -> list[dict[str, Any]]:
    """Exclude ephemeral command IDs so comparisons survive application restarts."""
    def project(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "index": item.get("index"),
            "caption": item.get("caption") if item.get("caption_reliable") else None,
            "caption_reliable": bool(item.get("caption_reliable")),
            "enabled": item.get("enabled"),
            "children": [project(child) for child in item.get("children", [])],
        }
    return [project(item) for item in menu.get("items", [])]


def diff_menu_structures(previous: list[dict[str, Any]] | None, current: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a compact, deterministic structural state diff."""
    if previous is None:
        return {"kind": "initial_state", "changed": True, "previous": None, "current": current}
    return {
        "kind": "menu_structure_diff",
        "changed": previous != current,
        "previous": previous if previous != current else None,
        "current": current if previous != current else None,
    }


def _load_latest_state(output_dir: Path) -> dict[str, Any] | None:
    atlas_path = output_dir / "atlas.json"
    if not atlas_path.exists():
        return None
    try:
        states = json.loads(atlas_path.read_text(encoding="utf-8")).get("states", [])
    except (OSError, json.JSONDecodeError):
        return None
    return states[-1] if states else None


def capture_active_mdi_state(*, output_dir: Path = DEFAULT_OUTPUT_DIR, previous_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Persist the currently active MDI state and its diff to the previous one."""
    output_dir.mkdir(parents=True, exist_ok=True)
    title = active_mdi_title()
    if not title:
        raise RuntimeError("No active WinWatt MDI child is available; refusing to create an ambiguous MDI state.")
    state_id = f"project_open__mdi__{_slug(title)}"
    native_menu = enumerate_native_menu()
    snapshot = asdict(capture_state_snapshot(state_id))
    snapshot["active_mdi_title"] = title
    snapshot["dynamic_context"] = resolve_live_dynamic_context()
    structure = _structural_signature(native_menu)
    previous_state = previous_state if previous_state is not None else _load_latest_state(output_dir)
    previous_structure = previous_state.get("menu_structure") if previous_state else None
    diff = diff_menu_structures(previous_structure, structure)
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    state_dir = output_dir / state_id
    state_dir.mkdir(parents=True, exist_ok=True)
    screenshot = state_dir / "ui.png"
    get_main_window().capture_as_image().save(screenshot)
    record = {
        "state_id": state_id,
        "state_kind": "active_mdi_catalog",
        "active_mdi_title": title,
        "captured_at": timestamp,
        "snapshot": snapshot,
        "menu_structure": structure,
        "native_top_menu": _top_menu_structure(native_menu),
        "ui_snapshot": str(screenshot.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "menu_diff_from_previous": diff,
        "previous_state_id": previous_state.get("state_id") if previous_state else None,
    }
    (state_dir / "state.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (state_dir / "menu_diff.json").write_text(json.dumps(diff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    atlas_path = output_dir / "atlas.json"
    atlas = {"schema_version": 1, "states": []}
    if atlas_path.exists():
        try:
            atlas = json.loads(atlas_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    states = [item for item in atlas.get("states", []) if item.get("state_id") != state_id]
    states.append(record)
    atlas["states"] = states
    atlas_path.write_text(json.dumps(atlas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def activate_rooms_catalog() -> dict[str, Any]:
    """Open the known safe Helyiségek catalog entry, without selecting a room."""
    popup = open_top_menu_and_capture_popup_state("Jegyz\u00e9kek")
    if not popup.get("popup_open"):
        raise RuntimeError(f"Could not open Jegyzékek popup: {popup.get('status')}")
    clicked = click_structured_popup_row(list(popup.get("rows") or []), ROOMS_CATALOG_INDEX)
    time.sleep(0.5)
    title = active_mdi_title()
    if title != ROOMS_TITLE:
        raise RuntimeError(f"Expected active MDI title {ROOMS_TITLE!r}, observed {title!r}")
    return {"catalog_index": ROOMS_CATALOG_INDEX, "active_mdi_title": title, "clicked_rectangle": clicked.get("rectangle")}


def map_rooms_new_element_menu(*, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    """Map Helyiségek -> Elem -> Létrehoz... without activating the item.

    The result is evidence for a future create_room workflow only; it is not a
    creation workflow and does not click the captured row.
    """
    title = active_mdi_title()
    if title != ROOMS_TITLE:
        raise RuntimeError(f"Refusing room menu mapping outside {ROOMS_TITLE!r}; active MDI is {title!r}")
    prepare_main_window_for_menu_interaction()
    main_window = ensure_main_window_foreground_before_click(
        action_label="safe_rooms_element_route_probe", allow_dialog=True
    )
    menu_bar = next(
        control
        for control in main_window.descendants(control_type="MenuBar")
        if control.window_text().strip() == "Alkalmaz\u00e1s"
    )
    element_menu = next(
        control
        for control in menu_bar.children(control_type="MenuItem")
        if control.window_text().strip() == ELEMENT_MENU_TITLE
    )
    # UIA menu opening, screenshot and Escape are observational only.
    element_menu.click_input()
    time.sleep(0.2)
    from pywinauto import Application

    native_window = Application(backend="win32").connect(process=int(main_window.process_id())).window(handle=main_window.handle)
    native_root = next(item for item in native_window.menu().items() if item.text().replace("&", "").strip() == ELEMENT_MENU_TITLE)
    native_rows = [
        {
            "row_index": index,
            "command_id": int(item.item_id()),
            "enabled": bool(item.is_enabled()),
            "caption_reliable": bool(item.text().strip()),
        }
        for index, item in enumerate(native_root.sub_menu().items())
    ]
    target = native_rows[0] if native_rows else None
    try:
        menu_screenshot = output_dir / "project_open__mdi__helyisegek" / "elem_menu.png"
        menu_screenshot.parent.mkdir(parents=True, exist_ok=True)
        main_window.capture_as_image().save(menu_screenshot)
    finally:
        main_window.type_keys("{ESC}")
    output_dir.mkdir(parents=True, exist_ok=True)
    route = {
        "state_id": "project_open__mdi__helyisegek",
        "precondition": {"active_mdi_title": ROOMS_TITLE, "dynamic_context_recognized": bool(resolve_live_dynamic_context().get("recognized"))},
        "route": [
            {"top_menu": ELEMENT_MENU_TITLE},
            {
                "semantic_alias": "new_element",
                "visible_caption": CREATE_ELEMENT_VISIBLE_CAPTION,
                "row_index": 0,
                "native_candidate": target,
            },
        ],
        "row_found": bool(target and target["enabled"]),
        "rows": native_rows,
        "visual_evidence": str(menu_screenshot.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "policy": "mapping_only_do_not_click_new_element_until_create_room_has_explicit_effect_and_recovery_policy",
    }
    route_path = output_dir / "project_open__mdi__helyisegek" / "create_room_route.json"
    route_path.parent.mkdir(parents=True, exist_ok=True)
    route_path.write_text(json.dumps(route, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return route
