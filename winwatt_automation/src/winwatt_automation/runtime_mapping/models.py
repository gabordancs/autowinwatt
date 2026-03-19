from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RuntimeStateSnapshot:
    state_id: str
    process_id: int | None
    main_window_title: str
    main_window_class: str
    visible_top_windows: list[dict[str, Any]]
    discovered_top_menus: list[str]
    timestamp: str
    main_window_enabled: bool | None = None
    main_window_visible: bool | None = None
    foreground_window: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeMenuRow:
    state_id: str
    top_menu: str
    row_index: int
    menu_path: list[str]
    text: str
    normalized_text: str
    rectangle: dict[str, Any]
    center_x: int
    center_y: int
    is_separator: bool
    source_scope: str
    fragments: list[dict[str, Any]]
    enabled_guess: bool | None
    discovered_in_state: str
    actionable: bool = True
    action_type: str = "click"
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeMenuNode:
    state_id: str
    title_raw: str
    title: str
    normalized_title: str
    path: list[str]
    level: int
    index: int
    enabled: bool | None
    separator: bool
    shortcut: str | None
    opens_submenu: bool
    opens_dialog: bool
    likely_destructive: bool
    likely_state_changing: bool
    action_classification: str
    skipped_by_safety: bool
    children: list[dict[str, Any]] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeActionResult:
    state_id: str
    top_menu: str
    row_index: int
    menu_path: list[str]
    action_key: str
    safety_level: str
    attempted: bool
    result_type: str
    dialog_title: str | None
    dialog_class: str | None
    window_title: str | None
    window_class: str | None
    error_text: str | None
    notes: str | None
    process_id: int | None
    top_menu_click_count: int | None
    event_details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeWindowRecord:
    state_id: str
    top_menu: str
    row_index: int
    menu_path: list[str]
    title: str
    class_name: str
    process_id: int | None
    rectangle: dict[str, Any] = field(default_factory=dict)
    enabled: bool | None = None
    visible: bool | None = None
    controls: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class RuntimeDialogRecord:
    state_id: str
    top_menu: str
    row_index: int
    menu_path: list[str]
    title: str
    class_name: str
    process_id: int | None
    rectangle: dict[str, Any] = field(default_factory=dict)
    enabled: bool | None = None
    visible: bool | None = None
    controls: list[dict[str, Any]] = field(default_factory=list)
    explored_controls: list[dict[str, Any]] = field(default_factory=list)
    interactions_attempted: list[dict[str, Any]] = field(default_factory=list)
    resulting_states: list[str] = field(default_factory=list)
    exploration_depth: int = 0


@dataclass(slots=True)
class RuntimeStateMap:
    state_id: str
    snapshot: dict[str, Any]
    top_menus: list[dict[str, Any]]
    menu_rows: list[dict[str, Any]]
    menu_tree: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    dialogs: list[dict[str, Any]]
    windows: list[dict[str, Any]]
    skipped_actions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class RuntimeStateDiff:
    state_a: str
    state_b: str
    top_menu_diff: dict[str, Any]
    menu_action_diff: dict[str, Any]
    dialog_diff: dict[str, Any]
    window_diff: dict[str, Any]
    summary: dict[str, Any]
    enabled_state_changes: list[dict[str, Any]] = field(default_factory=list)
    project_only_paths: list[list[str]] = field(default_factory=list)
