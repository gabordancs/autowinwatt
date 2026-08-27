"""Unbounded, sandbox-only state graph exploration for WinWatt rooms.

Every queued path is replayed from a fresh project session.  This makes
destructive room actions recoverable and allows the graph to explore child
dialogs such as ``Szerkezetek...`` without depending on a fragile UI history.
There is intentionally no depth limit; termination is when no replay produces
a new structural UI state.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pywinauto import Application, Desktop, keyboard

from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.live_ui.native_menu import enumerate_native_menu
from winwatt_automation.runtime_mapping.mdi_state_model import ROOMS_CATALOG_INDEX, activate_rooms_catalog
from winwatt_automation.runtime_mapping.program_mapper import prepare_fresh_winwatt_session


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SANDBOX_ROOM = "Room graph explorer"
ACTION_TYPES = {"Button", "TabItem", "ComboBox", "TreeItem", "ListItem", "CheckBox", "RadioButton"}
MAX_FAILURE_RETRIES = 3
CHECKPOINT_COMPACTION_INTERVAL = 50
EVENT_LOG_NAME = "exploration.events.jsonl"
PROGRESS_NAME = "progress.json"


@dataclass(frozen=True)
class ControlAction:
    control_type: str
    name: str
    automation_id: str
    rect: tuple[int, int, int, int]
    operation: str = "activate"


def _rect(control: Any) -> tuple[int, int, int, int]:
    value = control.rectangle()
    return (int(value.left), int(value.top), int(value.right), int(value.bottom))


def _control_payload(control: Any) -> dict[str, Any]:
    info = control.element_info
    try:
        enabled = bool(control.is_enabled())
    except Exception:
        enabled = False
    try:
        visible = bool(control.is_visible())
    except Exception:
        visible = False
    control_type = str(getattr(info, "control_type", "") or "")
    value: Any = None
    try:
        if control_type == "ComboBox":
            selected_text = getattr(control, "selected_text", None)
            value = selected_text() if callable(selected_text) else control.window_text()
        elif control_type == "Edit":
            get_value = getattr(control, "get_value", None)
            value = get_value() if callable(get_value) else control.window_text()
        elif control_type in {"CheckBox", "RadioButton"}:
            get_toggle_state = getattr(control, "get_toggle_state", None)
            value = get_toggle_state() if callable(get_toggle_state) else None
    except Exception:
        value = None
    return {
        "control_type": control_type,
        "class_name": str(getattr(info, "class_name", "") or ""),
        "name": str(getattr(info, "name", "") or ""),
        "automation_id": str(getattr(info, "automation_id", "") or ""),
        "enabled": enabled,
        "visible": visible,
        "rect": _rect(control),
        "value": value,
    }


def state_signature(window: Any) -> dict[str, Any]:
    """UI signature including selectable values, suitable for state deduplication."""
    controls = []
    for control in window.descendants():
        payload = _control_payload(control)
        if payload["visible"]:
            controls.append(payload)
    controls.sort(key=lambda item: (item["control_type"], item["name"], item["rect"]))
    return {"title": window.window_text(), "class_name": window.class_name(), "controls": controls}


def state_hash(signature: dict[str, Any]) -> str:
    # Delphi/UIA control automation ids are handles, recreated whenever the
    # room dialog is reopened.  They are essential for an action trace, but
    # not part of the logical UI state.
    normalized_controls = [
        {key: value for key, value in control.items() if key != "automation_id"}
        for control in signature["controls"]
    ]
    encoded = json.dumps(
        {"title": signature["title"], "class_name": signature["class_name"], "controls": normalized_controls},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def state_diff(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """Compact structural and value diff used as evidence for each transition."""
    if previous is None:
        return {"kind": "initial_state", "changed": True, "added_controls": list(current["controls"]), "removed_controls": [], "value_changes": []}
    def key(item: dict[str, Any]) -> tuple[Any, ...]:
        return (item["control_type"], item["class_name"], item["name"], tuple(item["rect"]), item["enabled"], item["visible"])
    old = {key(item): item for item in previous["controls"]}
    new = {key(item): item for item in current["controls"]}
    value_changes = [
        {"control": new[item], "previous_value": old[item].get("value"), "current_value": new[item].get("value")}
        for item in sorted(old.keys() & new.keys())
        if old[item].get("value") != new[item].get("value")
    ]
    return {
        "kind": "structural_ui_diff",
        "changed": bool(value_changes) or old.keys() != new.keys() or previous["title"] != current["title"] or previous["class_name"] != current["class_name"],
        "added_controls": [new[item] for item in sorted(new.keys() - old.keys())],
        "removed_controls": [old[item] for item in sorted(old.keys() - new.keys())],
        "value_changes": value_changes,
    }


def actionable_controls(window: Any) -> list[ControlAction]:
    actions: list[ControlAction] = []
    seen: set[tuple[str, str, tuple[int, int, int, int], str]] = set()
    for control in window.descendants():
        payload = _control_payload(control)
        if not payload["visible"] or not payload["enabled"] or payload["control_type"] not in ACTION_TYPES:
            continue
        operation = "expand" if payload["control_type"] == "ComboBox" else "activate"
        key = (payload["control_type"], payload["name"], payload["rect"], operation)
        if key in seen:
            continue
        seen.add(key)
        actions.append(ControlAction(
            control_type=payload["control_type"], name=payload["name"],
            automation_id=payload["automation_id"], rect=payload["rect"], operation=operation,
        ))
    return actions


def action_priority(action: ControlAction) -> tuple[int, str, str]:
    """Prefer controls that open the next configuration layer.

    The explorer uses a stack.  Keeping destructive/terminal window buttons at
    the bottom means it documents them eventually, without spending its early
    budget repeatedly closing the room before entering its nested selectors.
    """
    label = action.name.casefold()
    if action.control_type == "TreeItem":
        # The tree is the gateway to the actual boundary-construction
        # catalog; explore it before the many parameter dropdowns.
        rank = 95
    elif action.control_type == "ListItem":
        rank = 85
    elif action.control_type == "ComboBox":
        rank = 80
    elif action.control_type == "TabItem":
        rank = 70
    elif any(token in label for token in ("szerkezet", "felvesz", "m\u00f3dos", "v\u00e1laszt")):
        rank = 90
    elif label in {"bez\u00e1r\u00e1s", "elvet", "ok", "kis m\u00e9ret", "el\u0151z\u0151 m\u00e9ret"}:
        rank = 0
    else:
        rank = 40
    return rank, action.control_type, label


def action_identity(action: ControlAction | dict[str, Any]) -> tuple[str, str, tuple[int, int, int, int], str]:
    """Stable action identity that deliberately excludes recreated handles."""
    if isinstance(action, ControlAction):
        return action.control_type, action.name, action.rect, action.operation
    return (
        str(action["control_type"]), str(action["name"]),
        tuple(int(value) for value in action["rect"]), str(action.get("operation", "activate")),
    )


def path_identity(path: list[ControlAction]) -> str:
    return json.dumps([action_identity(action) for action in path], ensure_ascii=False, separators=(",", ":"))


def _deduplicate_queue(queue: deque[tuple[list[ControlAction], str | None]]) -> deque[tuple[list[ControlAction], str | None]]:
    seen: set[str] = set()
    unique: deque[tuple[list[ControlAction], str | None]] = deque()
    for path, parent_state in queue:
        key = path_identity(path)
        if key not in seen:
            seen.add(key)
            unique.append((path, parent_state))
    return unique


def _write_progress(output_dir: Path, states: list[dict[str, Any]], edges: list[dict[str, Any]], failures: list[dict[str, Any]], queue: deque[tuple[list[ControlAction], str | None]]) -> None:
    """Cheap, current progress for the status popup (not a resume artifact)."""
    _atomic_json_write(output_dir / PROGRESS_NAME, {
        "states": len(states), "edges": len(edges), "failures": len(failures),
        "queue": len(queue), "complete": not queue,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


def _append_event(output_dir: Path, payload: dict[str, Any]) -> None:
    """Durably record one transition without reserializing the whole graph."""
    path = output_dir / EVENT_LOG_NAME
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _remove_queued_path(queue: deque[tuple[list[ControlAction], str | None]], path: list[ControlAction]) -> bool:
    target = path_identity(path)
    for index, (candidate, _) in enumerate(queue):
        if path_identity(candidate) == target:
            del queue[index]
            return True
    return False


def _replay_event_log(output_dir: Path, states: list[dict[str, Any]], edges: list[dict[str, Any]], failures: list[dict[str, Any]], queue: deque[tuple[list[ControlAction], str | None]]) -> int:
    """Apply transitions saved after the last compact checkpoint."""
    journal = output_dir / EVENT_LOG_NAME
    if not journal.exists():
        return 0
    state_ids = {item["state_id"] for item in states}
    applied = 0
    for line in journal.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        path = [ControlAction(**item) for item in event["path"]]
        # A compact checkpoint already processed this event if its path is no
        # longer pending. This makes a crash during compaction harmless.
        if not _remove_queued_path(queue, path):
            continue
        parent_state = event.get("parent_state")
        outcome = event["outcome"]
        _set_edge_status(edges, parent_state, path, outcome, event.get("state_id"))
        if outcome == "discovered":
            state_id = str(event["state_id"])
            if state_id not in state_ids:
                record_path = output_dir / "states" / state_id / "state.json"
                states.append(json.loads(record_path.read_text(encoding="utf-8")))
                state_ids.add(state_id)
            edges.extend(event.get("new_edges") or [])
            for item in event.get("queued") or []:
                queue.append(([ControlAction(**action) for action in item], state_id))
        elif outcome == "failed" and event.get("failure") is not None:
            failures.append(event["failure"])
        applied += 1
    return applied


def _prune_queue(queue: deque[tuple[list[ControlAction], str | None]], states: list[dict[str, Any]], edges: list[dict[str, Any]], failures: list[dict[str, Any]]) -> tuple[deque[tuple[list[ControlAction], str | None]], int]:
    """Drop duplicate and permanently exhausted paths before expensive replay."""
    attempt_count: dict[str, int] = {}
    for item in failures:
        key = json.dumps(item.get("path") or [], ensure_ascii=False, sort_keys=True)
        attempt_count[key] = attempt_count.get(key, 0) + 1
    exhausted = {key for key, count in attempt_count.items() if count >= MAX_FAILURE_RETRIES}
    by_id = {item["state_id"]: item for item in states}
    terminal: set[str] = set()
    for edge in edges:
        if edge.get("status") != "revisited" or edge.get("from") not in by_id:
            continue
        parent_path = [ControlAction(**item) for item in by_id[edge["from"]]["path"]]
        terminal.add(path_identity([*parent_path, ControlAction(**edge["action"])]))
    kept: deque[tuple[list[ControlAction], str | None]] = deque()
    removed = 0
    for path, parent_state in _deduplicate_queue(queue):
        serialized = json.dumps([asdict(item) for item in path], ensure_ascii=False, sort_keys=True)
        prefixes = {path_identity(path[:index]) for index in range(1, len(path) + 1)}
        if serialized in exhausted or prefixes & terminal:
            removed += 1
            continue
        kept.append((path, parent_state))
    return kept, removed


def _set_edge_status(edges: list[dict[str, Any]], parent_state: str | None, path: list[ControlAction], status: str, target: str | None = None) -> None:
    if parent_state is None or not path:
        return
    identity = action_identity(path[-1])
    for edge in reversed(edges):
        if edge.get("from") == parent_state and action_identity(edge["action"]) == identity:
            edge["status"] = status
            if target is not None:
                edge["to"] = target
            return


def _find_control(window: Any, action: ControlAction) -> Any:
    exact = []
    fallback = []
    for control in window.descendants():
        payload = _control_payload(control)
        if not payload["visible"] or not payload["enabled"] or payload["control_type"] != action.control_type:
            continue
        if payload["name"] == action.name:
            fallback.append(control)
            if payload["rect"] == action.rect:
                exact.append(control)
    if exact:
        return exact[0]
    if fallback:
        return fallback[0]
    raise LookupError(f"Control disappeared while replaying: {action}")


def _active_window(process_id: int) -> Any:
    candidates = []
    for window in Desktop(backend="uia").windows(top_level_only=True):
        try:
            if window.process_id() == process_id and window.is_visible() and window.is_enabled():
                candidates.append(window)
        except Exception:
            continue
    if not candidates:
        raise RuntimeError("No enabled WinWatt top-level window is active")
    # Modal dialogs have priority over the main frame and are the meaningful
    # continuation after a button/menu action.
    candidates.sort(key=lambda item: (item.class_name() != "TMainForm", item.rectangle().width() * item.rectangle().height()), reverse=True)
    return candidates[0]


def _invoke(control: Any, action: ControlAction) -> None:
    if action.operation == "expand":
        expand = getattr(control, "expand", None)
        if callable(expand):
            expand()
        else:
            control.click_input()
        return
    control.click_input()


def _find_replay_control(window: Any, action: ControlAction, process_id: int) -> Any:
    """Resolve a target after closing an incidental ComboBox popup if needed."""
    try:
        return _find_control(window, action)
    except LookupError:
        # A list popup can temporarily own the UIA subtree and hide the tree
        # behind it.  Closing that transient view is not a destructive action;
        # it restores the exact dialog that the next replay step targets.
        keyboard.send_keys("{ESC}")
        time.sleep(0.15)
        return _find_control(_active_window(process_id), action)


def _room_list_item(main: Any, room_name: str) -> Any | None:
    for item in main.descendants(control_type="ListItem"):
        try:
            if item.window_text().strip() == room_name:
                return item
        except Exception:
            continue
    return None


def _create_sandbox_room(main: Any, room_name: str) -> None:
    """Create and commit the dedicated room, waiting for Delphi form swaps.

    On slower/remote desktops the first ``OK`` opens ``TRoomModifyForm``
    after more than the old fixed 0.5 seconds.  Clicking the stale creation
    dialog a second time leaves the workflow waiting for a manual room-save
    confirmation.  Bind the second confirmation to the actual detail form.
    """
    native = Application(backend="win32").connect(process=int(main.process_id())).window(handle=int(main.handle))
    element_menu = next(item for item in native.menu().items() if item.text().replace("&", "").strip() == "Elem")
    element_menu.click()
    time.sleep(0.2)
    element_menu.sub_menu().items()[0].click()
    time.sleep(0.4)
    dialog = _active_window(int(main.process_id()))
    edit = next(item for item in dialog.descendants(control_type="Edit") if item.is_visible())
    edit.set_edit_text(room_name)
    next(item for item in dialog.descendants(control_type="Button") if item.window_text() == "OK").click_input()
    process_id = int(main.process_id())
    deadline = time.monotonic() + 8.0
    detail = None
    while time.monotonic() < deadline:
        candidate = _active_window(process_id)
        if candidate.class_name() == "TRoomModifyForm":
            detail = candidate
            break
        time.sleep(0.15)
    if detail is None:
        observed = _active_window(process_id)
        raise RuntimeError(
            "Room creation did not open TRoomModifyForm for automatic save; "
            f"observed {observed.class_name()!r} ({observed.window_text()!r})"
        )
    ok = next(item for item in detail.descendants(control_type="Button") if item.window_text().strip() == "OK")
    ok.click_input()
    # Saving the detail form is asynchronous too.  Wait until the newly
    # created row is observable instead of requiring an operator to confirm.
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if _room_list_item(get_main_window(), room_name) is not None:
            return
        time.sleep(0.15)
    raise RuntimeError("Room detail OK was sent, but the created room did not appear in the Helyiségek list")


def _project_session_is_ready(project_path: str) -> bool:
    try:
        title = get_main_window().window_text().casefold()
    except Exception:
        return False
    return Path(project_path).name.casefold() in title and "winwatt" in title


def _dismiss_secondary_windows(process_id: int, *, attempts: int = 5) -> None:
    """Return from a previous branch without paying for a process restart."""
    for _ in range(attempts):
        active = _active_window(process_id)
        if active.class_name() == "TMainForm":
            return
        keyboard.send_keys("{ESC}")
        time.sleep(0.2)


def _activate_rooms_catalog_fast(main: Any) -> None:
    """Use the already verified native menu index during path replay.

    The complete, diagnostic menu snapshot remains part of every *new state*.
    Replaying hundreds of paths does not need to recapture the same catalog
    popup just to return to the known Helyiségek list.
    """
    native = Application(backend="win32").connect(process=int(main.process_id())).window(handle=int(main.handle))
    catalog_menu = next(item for item in native.menu().items() if item.text().replace("&", "").strip() == "Jegyzékek")
    catalog_menu.click()
    time.sleep(0.1)
    catalog_menu.sub_menu().items()[ROOMS_CATALOG_INDEX].click()
    time.sleep(0.35)


def open_sandbox_room(*, project_path: str, room_name: str) -> Any:
    """Restart into the sandbox project and return a room detail form."""
    if not _project_session_is_ready(project_path):
        prepare_fresh_winwatt_session(project_path=project_path)
    else:
        _dismiss_secondary_windows(int(get_main_window().process_id()))
    main = get_main_window()
    try:
        _activate_rooms_catalog_fast(main)
    except Exception:
        # Keep the extensively validated UIA route as a recovery path.
        activate_rooms_catalog()
    main = get_main_window()
    item = _room_list_item(main, room_name)
    if item is None:
        _create_sandbox_room(main, room_name)
        main = get_main_window()
        item = _room_list_item(main, room_name)
    if item is None:
        raise RuntimeError("Sandbox room could not be created or located")
    item.click_input()
    native = Application(backend="win32").connect(process=int(main.process_id())).window(handle=int(main.handle))
    element_menu = next(menu for menu in native.menu().items() if menu.text().replace("&", "").strip() == "Elem")
    element_menu.click()
    time.sleep(0.15)
    element_menu.sub_menu().items()[1].click()
    time.sleep(0.5)
    window = _active_window(int(main.process_id()))
    if window.class_name() != "TRoomModifyForm":
        raise RuntimeError(f"Expected TRoomModifyForm, got {window.class_name()!r}")
    return window


def _write_state(*, output_dir: Path, state_id: str, window: Any, parent_state: str | None, parent_signature: dict[str, Any] | None, path: list[ControlAction]) -> tuple[dict[str, Any], list[ControlAction]]:
    state_dir = output_dir / "states" / state_id
    state_dir.mkdir(parents=True, exist_ok=True)
    signature = state_signature(window)
    actions = actionable_controls(window)
    image = state_dir / "ui.png"
    window.capture_as_image().save(image)
    menu = None
    try:
        menu = enumerate_native_menu()
    except Exception:
        pass
    record = {
        "state_id": state_id, "parent_state": parent_state,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "window": {"title": window.window_text(), "class_name": window.class_name(), "handle": int(window.handle)},
        "signature": signature, "signature_hash": state_hash(signature), "diff_from_parent": state_diff(parent_signature, signature),
        "path": [asdict(item) for item in path], "controls": signature["controls"],
        "actions": [asdict(item) for item in actions], "native_menu": menu,
        "screenshot": str(image.relative_to(PROJECT_ROOT)).replace("\\", "/"),
    }
    (state_dir / "state.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record, actions


def _atomic_json_write(path: Path, payload: Any) -> None:
    """Durably replace a JSON artifact, tolerating transient Windows locks."""
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    last_error: OSError | None = None
    for _ in range(5):
        try:
            temporary.write_text(rendered, encoding="utf-8")
            os.replace(temporary, path)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.25)
    temporary.unlink(missing_ok=True)
    assert last_error is not None
    raise last_error


def _write_checkpoint(output_dir: Path, states: list[dict[str, Any]], edges: list[dict[str, Any]], failures: list[dict[str, Any]], queue: deque[tuple[list[ControlAction], str | None]]) -> None:
    graph = {"states": states, "edges": edges, "failures": failures, "queue_size": len(queue), "complete": not queue}
    # Keep the replay queue outside the human-readable graph.  This makes an
    # interrupted run resumable without bloating each graph snapshot.
    queue_payload = [
        {"path": [asdict(action) for action in path], "parent_state": parent_state}
        for path, parent_state in queue
    ]
    _atomic_json_write(output_dir / "graph.checkpoint.json", graph)
    _atomic_json_write(output_dir / "queue.checkpoint.json", queue_payload)
    _write_progress(output_dir, states, edges, failures, queue)
    # The checkpoint and queue now contain every earlier event.  Removing the
    # journal only after both atomic writes preserves exact resumability.
    (output_dir / EVENT_LOG_NAME).unlink(missing_ok=True)


def _path_uses_excluded_tab(path: list[ControlAction], excluded_tab_names: set[str]) -> bool:
    """Return whether a replay path enters a tab deliberately out of scope."""
    return any(
        action.control_type == "TabItem" and action.name.casefold() in excluded_tab_names
        for action in path
    )


def explore_room_state_graph(*, project_path: str, output_dir: Path, room_name: str = DEFAULT_SANDBOX_ROOM, resume: bool = False, retry_failures: bool = False, exclude_tab_names: set[str] | None = None, session_islands: bool = False) -> dict[str, Any]:
    """Explore until no action replay yields a new structural state."""
    project = Path(project_path).resolve()
    excluded_tab_names = {name.casefold() for name in (exclude_tab_names or set())}
    if "full_authorized_sandbox" not in {part.casefold() for part in project.parts}:
        raise ValueError("Deep room exploration requires a project under full_authorized_sandbox")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    queue: deque[tuple[list[ControlAction], str | None]] = deque([([], None)])
    states: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    if resume and (output_dir / "graph.checkpoint.json").exists():
        previous = json.loads((output_dir / "graph.checkpoint.json").read_text(encoding="utf-8"))
        states = list(previous.get("states") or [])
        edges = list(previous.get("edges") or [])
        for edge in edges:
            edge.setdefault("status", "pending")
        failures = list(previous.get("failures") or [])
        queue_path = output_dir / "queue.checkpoint.json"
        if queue_path.exists():
            queue = deque(
                ([ControlAction(**action) for action in item["path"]], item.get("parent_state"))
                for item in json.loads(queue_path.read_text(encoding="utf-8"))
            )
        else:
            by_id = {record["state_id"]: record for record in states}
            queue = deque(
                ([*(ControlAction(**action) for action in by_id[edge["from"]]["path"]), ControlAction(**edge["action"])], edge["from"])
                for edge in edges if edge.get("from") in by_id and edge.get("status", "pending") == "pending"
            )
        if retry_failures:
            retry_count: dict[str, int] = {}
            for item in failures:
                key = json.dumps(item.get("path") or [], ensure_ascii=False, sort_keys=True)
                retry_count[key] = retry_count.get(key, 0) + 1
            queue.extend(
                ([ControlAction(**action) for action in item["path"]], None)
                for item in failures
                if item.get("path") and retry_count[json.dumps(item["path"], ensure_ascii=False, sort_keys=True)] < MAX_FAILURE_RETRIES
            )
    recovered_events = _replay_event_log(output_dir, states, edges, failures, queue)
    # A resumed historical queue can already contain paths below tabs that are
    # now intentionally out of scope.  Remove their whole subtrees before any
    # replay, rather than merely suppressing newly discovered children.
    if excluded_tab_names:
        queue = deque(
            (path, parent_state) for path, parent_state in queue
            if not _path_uses_excluded_tab(path, excluded_tab_names)
        )
    queue, pruned_paths = _prune_queue(queue, states, edges, failures)
    _write_progress(output_dir, states, edges, failures, queue)
    scheduled_paths = {path_identity(path) for path, _ in queue}
    processed_since_compaction = 0
    visited: set[str] = {str(record["signature_hash"]) for record in states}
    # A verified modal return point.  It is deliberately only an optimisation:
    # if the dialog cannot be restored exactly, the next path falls back to
    # fresh root replay.
    island: dict[str, Any] | None = None
    while queue:
        # Depth-first traversal reaches nested selectors and their creation/
        # modification dialogs before the large number of superficial sibling
        # controls.  Every queued path is still processed; the order only
        # changes when evidence becomes available.
        path, parent_state = queue.pop()
        scheduled_paths.discard(path_identity(path))
        _set_edge_status(edges, parent_state, path, "running")
        try:
            parent_record = next((item for item in states if item["state_id"] == parent_state), None)
            use_island = (
                session_islands and island is not None and parent_record is not None
                and island["state_id"] == parent_state and island["path"] == path_identity(path[:-1])
            )
            if use_island:
                window = _active_window(int(island["process_id"]))
                if state_hash(state_signature(window)) != parent_record["signature_hash"]:
                    island = None
                    use_island = False
            if use_island:
                _invoke(_find_replay_control(window, path[-1], int(window.process_id())), path[-1])
                time.sleep(0.25)
            else:
                window = open_sandbox_room(project_path=str(project), room_name=room_name)
                for action in path:
                    current = _active_window(int(window.process_id()))
                    _invoke(_find_replay_control(current, action, int(window.process_id())), action)
                    time.sleep(0.25)
            window = _active_window(int(window.process_id()))
            signature = state_signature(window)
            digest = state_hash(signature)
            if digest in visited:
                _set_edge_status(edges, parent_state, path, "revisited")
                _append_event(output_dir, {
                    "path": [asdict(item) for item in path], "parent_state": parent_state,
                    "outcome": "revisited",
                })
            else:
                visited.add(digest)
                state_id = f"state_{len(states):04d}_{digest[:10]}"
                record, actions = _write_state(
                    output_dir=output_dir, state_id=state_id, window=window, parent_state=parent_state,
                    parent_signature=parent_record["signature"] if parent_record else None, path=path,
                )
                states.append(record)
                _set_edge_status(edges, parent_state, path, "discovered", state_id)
                # A selected ComboBox value is a real, captured runtime state,
                # but only newly exposed actions deserve further traversal.
                if record["diff_from_parent"]["value_changes"] and parent_record is not None:
                    parent_action_ids = {action_identity(item) for item in parent_record["actions"]}
                    actions = [item for item in actions if action_identity(item) not in parent_action_ids]
                queued_actions: list[list[dict[str, Any]]] = []
                new_edges: list[dict[str, Any]] = []
                for action in sorted(actions, key=action_priority):
                    candidate = [*path, action]
                    if _path_uses_excluded_tab(candidate, excluded_tab_names):
                        continue
                    candidate_id = path_identity(candidate)
                    if candidate_id in scheduled_paths:
                        continue
                    scheduled_paths.add(candidate_id)
                    queue.append((candidate, state_id))
                    queued_actions.append([asdict(item) for item in candidate])
                    edge = {"from": state_id, "action": asdict(action), "to": "pending", "status": "pending"}
                    edges.append(edge)
                    new_edges.append(edge)
                _append_event(output_dir, {
                    "path": [asdict(item) for item in path], "parent_state": parent_state,
                    "outcome": "discovered", "state_id": state_id,
                    "new_edges": new_edges, "queued": queued_actions,
                })
            # Child forms opened by buttons are the common expensive case.
            # Try returning to the exact parent once, then reuse that live
            # dialog for all its queued sibling actions.  Escape is only
            # accepted after an exact structural signature check.  This also
            # applies to already-known child states in a resumed graph.
            island = None
            if (
                session_islands and parent_record is not None and path
                and path[-1].control_type == "Button"
                and digest != parent_record["signature_hash"]
            ):
                try:
                    keyboard.send_keys("{ESC}")
                    time.sleep(0.3)
                    restored = _active_window(int(window.process_id()))
                    if state_hash(state_signature(restored)) == parent_record["signature_hash"]:
                        island = {
                            "state_id": parent_state,
                            "path": path_identity(path[:-1]),
                            "process_id": int(window.process_id()),
                        }
                except Exception:
                    island = None
        except Exception as exc:
            _set_edge_status(edges, parent_state, path, "failed")
            serialized_path = [asdict(item) for item in path]
            key = json.dumps(serialized_path, ensure_ascii=False, sort_keys=True)
            matching = [item for item in failures if json.dumps(item.get("path") or [], ensure_ascii=False, sort_keys=True) == key]
            if len(matching) < MAX_FAILURE_RETRIES:
                failure = {"path": serialized_path, "error": str(exc), "attempt": len(matching) + 1}
                failures.append(failure)
                _append_event(output_dir, {
                    "path": serialized_path, "parent_state": parent_state,
                    "outcome": "failed", "failure": failure,
                })
            else:
                _append_event(output_dir, {
                    "path": serialized_path, "parent_state": parent_state, "outcome": "failed",
                })
        processed_since_compaction += 1
        _write_progress(output_dir, states, edges, failures, queue)
        if processed_since_compaction >= CHECKPOINT_COMPACTION_INTERVAL:
            _write_checkpoint(output_dir, states, edges, failures, queue)
            processed_since_compaction = 0
    path_to_state = {
        json.dumps(record["path"], ensure_ascii=False, sort_keys=True): record["state_id"]
        for record in states
    }
    for edge in edges:
        parent = next((record for record in states if record["state_id"] == edge["from"]), None)
        if parent is None:
            edge["to"] = "unresolved_parent"
            continue
        child_path = [*parent["path"], edge["action"]]
        edge["to"] = path_to_state.get(
            json.dumps(child_path, ensure_ascii=False, sort_keys=True),
            "revisited_or_blocked",
        )
    _write_checkpoint(output_dir, states, edges, failures, deque())
    graph = {"states": states, "edges": edges, "failures": failures, "queue_size": 0, "complete": True}
    _atomic_json_write(output_dir / "graph.json", graph)
    return graph
