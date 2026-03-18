from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import time
from typing import Any

from loguru import logger

SKIPPED_CONTROL_TYPES = {"Static", "Group", "Pane", "TitleBar"}
DESTRUCTIVE_KEYWORDS = ("delete", "törlés", "remove", "reset", "clear")


@dataclass(slots=True)
class DialogControl:
    control_type: str
    friendly_class_name: str
    name: str
    automation_id: str
    enabled: bool
    visible: bool
    rectangle: dict[str, int]


@dataclass(slots=True)
class DialogInteraction:
    control_name: str
    control_type: str
    classification: str
    attempted: bool
    success: bool
    skipped_reason: str | None = None
    error: str | None = None


def _safe_call(obj: Any, method: str, default: Any = None) -> Any:
    attr = getattr(obj, method, None)
    if not callable(attr):
        return default
    try:
        return attr()
    except Exception:
        return default


def _control_text(control: Any) -> str:
    return str(_safe_call(control, "window_text", "") or "")


def _rectangle_to_dict(control: Any) -> dict[str, int]:
    rect = _safe_call(control, "rectangle", None)
    if rect is None:
        return {}
    return {
        "left": int(getattr(rect, "left", 0)),
        "top": int(getattr(rect, "top", 0)),
        "right": int(getattr(rect, "right", 0)),
        "bottom": int(getattr(rect, "bottom", 0)),
    }


def _get_control_type(control: Any) -> str:
    return str(_safe_call(control, "control_type", "") or getattr(getattr(control, "element_info", None), "control_type", "") or "")


def _get_friendly_class_name(control: Any) -> str:
    return str(_safe_call(control, "friendly_class_name", "") or "")


def enumerate_dialog_controls(dialog: Any) -> list[dict[str, Any]]:
    descendants = _safe_call(dialog, "descendants", []) or []
    controls: list[dict[str, Any]] = []
    for control in descendants:
        control_type = _get_control_type(control)
        if control_type in SKIPPED_CONTROL_TYPES:
            continue
        model = DialogControl(
            control_type=control_type,
            friendly_class_name=_get_friendly_class_name(control),
            name=_control_text(control),
            automation_id=str(getattr(getattr(control, "element_info", None), "automation_id", "") or ""),
            enabled=bool(_safe_call(control, "is_enabled", False)),
            visible=bool(_safe_call(control, "is_visible", False)),
            rectangle=_rectangle_to_dict(control),
        )
        controls.append(asdict(model))
    logger.info("dialog_controls_enumerated count={}", len(controls))
    return controls


def classify_control(control: Any) -> str:
    if isinstance(control, dict):
        friendly = str(control.get("friendly_class_name") or "").lower()
        control_type = str(control.get("control_type") or "").lower()
    else:
        friendly = _get_friendly_class_name(control).lower()
        control_type = _get_control_type(control).lower()

    checks = [friendly, control_type]
    if any("button" in value for value in checks):
        if any("check" in value for value in checks):
            return "checkbox"
        if any("radio" in value for value in checks):
            return "radio"
        return "button"
    if any("check" in value for value in checks):
        return "checkbox"
    if any("radio" in value for value in checks):
        return "radio"
    if any("combo" in value for value in checks):
        return "combobox"
    if any(value in {"edit", "text box"} or "edit" in value for value in checks):
        return "edit"
    if any("list" in value for value in checks):
        return "list"
    if any("tab" in value for value in checks):
        return "tab"
    if any("tree" in value for value in checks):
        return "tree"
    if any("slider" in value for value in checks):
        return "slider"
    return "unknown"


def _is_destructive(control: Any) -> bool:
    text = _control_text(control).lower()
    return any(keyword in text for keyword in DESTRUCTIVE_KEYWORDS)


def try_control_interaction(control: Any, *, safe_mode: bool = True, timeout_s: float = 1.0) -> dict[str, Any]:
    classification = classify_control(control)
    name = _control_text(control)
    if not bool(_safe_call(control, "is_enabled", False)):
        return asdict(DialogInteraction(name, _get_control_type(control), classification, False, False, skipped_reason="disabled"))
    if not bool(_safe_call(control, "is_visible", False)):
        return asdict(DialogInteraction(name, _get_control_type(control), classification, False, False, skipped_reason="hidden"))
    if safe_mode and _is_destructive(control):
        return asdict(DialogInteraction(name, _get_control_type(control), classification, False, False, skipped_reason="destructive_filtered"))

    logger.info("dialog_interaction_attempt control={} class={}", name, classification)
    started = time.monotonic()
    try:
        if classification == "button":
            _safe_call(control, "click_input", None)
        elif classification == "checkbox":
            _safe_call(control, "toggle", None)
        elif classification == "radio":
            if _safe_call(control, "is_selected", False) is not True:
                _safe_call(control, "select", None)
        elif classification == "combobox":
            _safe_call(control, "expand", None)
            items = _safe_call(control, "item_texts", []) or []
            if len(items) > 1:
                _safe_call(control, "select", items[1])
            elif items:
                _safe_call(control, "select", items[0])
        elif classification == "list":
            items = _safe_call(control, "item_texts", []) or []
            if items:
                _safe_call(control, "select", items[0])
        elif classification == "tab":
            tabs = _safe_call(control, "tab_count", 0) or 0
            current = _safe_call(control, "get_selected_tab", 0) or 0
            if tabs > 1:
                _safe_call(control, "select", (current + 1) % tabs)
        elif classification == "slider":
            current = _safe_call(control, "get_value", None)
            if isinstance(current, (int, float)):
                _safe_call(control, "set_value", current + 1)
        elif classification in {"edit", "tree", "unknown"}:
            return asdict(DialogInteraction(name, _get_control_type(control), classification, False, True, skipped_reason="safe_noop"))

        if time.monotonic() - started > timeout_s:
            raise TimeoutError(f"interaction exceeded timeout ({timeout_s}s)")

        logger.info("dialog_interaction_success control={} class={}", name, classification)
        return asdict(DialogInteraction(name, _get_control_type(control), classification, True, True))
    except Exception as exc:
        logger.warning("dialog_interaction_failed control={} class={} error={}", name, classification, exc)
        return asdict(DialogInteraction(name, _get_control_type(control), classification, True, False, error=str(exc)))


def _control_state_signature(control: Any) -> dict[str, Any]:
    signature = {
        "name": _control_text(control),
        "automation_id": str(getattr(getattr(control, "element_info", None), "automation_id", "") or ""),
        "control_type": _get_control_type(control),
        "classification": classify_control(control),
    }
    signature["selected"] = _safe_call(control, "is_selected", None)
    signature["toggle_state"] = _safe_call(control, "get_toggle_state", None)
    selected_text = _safe_call(control, "selected_text", None)
    if selected_text is None:
        selected_text = _safe_call(control, "window_text", "")
    signature["selected_text"] = selected_text
    return signature


def compute_dialog_state_hash(dialog: Any) -> str:
    title = str(_safe_call(dialog, "window_text", "") or "")
    descendants = _safe_call(dialog, "descendants", []) or []
    payload = {
        "dialog_title": title,
        "controls": sorted([_control_state_signature(control) for control in descendants], key=lambda item: (item["automation_id"], item["name"], item["control_type"])),
    }
    stable_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(stable_json.encode("utf-8")).hexdigest()
    logger.info("dialog_state_hash title={} hash={}", title, digest)
    return digest


def explore_dialog(
    dialog: Any,
    *,
    depth: int = 0,
    max_depth: int | None = None,
    visited_states: set[str] | None = None,
    safe_mode: bool = True,
) -> dict[str, Any]:
    logger.info("dialog_explorer_start depth={} max_depth={}", depth, max_depth)
    visited = visited_states if visited_states is not None else set()
    if max_depth is not None and max_depth >= 0 and depth >= max_depth:
        logger.info("dialog_explorer_depth_limit depth={} max_depth={}", depth, max_depth)
        return {
            "dialog_title": str(_safe_call(dialog, "window_text", "") or ""),
            "controls": [],
            "interactions": [],
            "states": [],
            "exploration_depth": depth,
            "explored_controls": [],
            "interactions_attempted": [],
            "resulting_states": [],
        }

    state_hash = compute_dialog_state_hash(dialog)
    if state_hash in visited:
        logger.info("dialog_state_visited_skip hash={}", state_hash)
        return {
            "dialog_title": str(_safe_call(dialog, "window_text", "") or ""),
            "controls": [],
            "interactions": [],
            "states": [state_hash],
            "exploration_depth": depth,
            "explored_controls": [],
            "interactions_attempted": [],
            "resulting_states": [state_hash],
        }
    visited.add(state_hash)

    controls = enumerate_dialog_controls(dialog)
    interactions: list[dict[str, Any]] = []
    states = [state_hash]

    for control in _safe_call(dialog, "descendants", []) or []:
        classification = classify_control(control)
        logger.info("dialog_control_classified name={} class={}", _control_text(control), classification)
        interaction = try_control_interaction(control, safe_mode=safe_mode)
        interactions.append(interaction)
        if interaction.get("attempted") and interaction.get("success"):
            next_hash = compute_dialog_state_hash(dialog)
            if next_hash not in states:
                states.append(next_hash)
            if next_hash not in visited and (max_depth is None or max_depth < 0 or depth + 1 < max_depth):
                nested = explore_dialog(dialog, depth=depth + 1, max_depth=max_depth, visited_states=visited, safe_mode=safe_mode)
                states.extend([item for item in nested.get("states", []) if item not in states])

    return {
        "dialog_title": str(_safe_call(dialog, "window_text", "") or ""),
        "controls": controls,
        "interactions": interactions,
        "states": states,
        "exploration_depth": depth,
        "explored_controls": controls,
        "interactions_attempted": interactions,
        "resulting_states": states,
    }
