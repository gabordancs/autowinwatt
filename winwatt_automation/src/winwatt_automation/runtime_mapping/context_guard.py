"""Fail-closed recognition of dynamic WinWatt MDI menu contexts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONTEXT_DIR = PROJECT_ROOT / "data" / "runtime_maps" / "catalog_contexts_9_60"
_DYNAMIC_ROOTS = ("Szerkesztés", "Csoport", "Elem")


def dynamic_context_signature(menu: dict[str, Any]) -> tuple[int, int, int] | None:
    """Return the context-sensitive root IDs, or None for a non-editable MDI view."""
    roots = {str(item.get("caption")): item.get("command_id") for item in menu.get("items", [])}
    values = tuple(roots.get(name) for name in _DYNAMIC_ROOTS)
    if any(not isinstance(value, int) for value in values):
        return None
    return values  # type: ignore[return-value]


def documented_dynamic_contexts(context_dir: Path = DEFAULT_CONTEXT_DIR) -> dict[tuple[int, int, int], dict[str, Any]]:
    """Load only unambiguous dynamic context signatures from saved runtime evidence."""
    found: dict[tuple[int, int, int], dict[str, Any]] = {}
    duplicates: set[tuple[int, int, int]] = set()
    for path in sorted(context_dir.glob("*.json")):
        if path.name == "manifest.json":
            continue
        try:
            menu = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        signature = dynamic_context_signature(menu)
        if signature is None:
            continue
        prefix, _, caption = path.stem.partition("_")
        evidence = {"index": int(prefix) if prefix.isdigit() else None, "caption": caption, "source": str(path)}
        if signature in found:
            duplicates.add(signature)
        else:
            found[signature] = evidence
    for signature in duplicates:
        found.pop(signature, None)
    return found


def documented_dynamic_context_titles(context_dir: Path = DEFAULT_CONTEXT_DIR) -> dict[str, dict[str, Any]]:
    """Load stable MDI-title identities from documented dynamic menu evidence.

    Command IDs are allocated dynamically by WinWatt and can be reused after a
    restart, so they deliberately do not participate in this identity map.
    """
    found: dict[str, dict[str, Any]] = {}
    for path in sorted(context_dir.glob("*.json")):
        if path.name == "manifest.json":
            continue
        try:
            menu = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if dynamic_context_signature(menu) is None:
            continue
        prefix, _, caption = path.stem.partition("_")
        if not caption:
            continue
        key = caption.casefold()
        if key in found:
            continue
        found[key] = {"index": int(prefix) if prefix.isdigit() else None, "caption": caption, "source": str(path)}
    return found


def active_mdi_title() -> str | None:
    """Read the topmost visible WinWatt MDI child title without clicking it."""
    from winwatt_automation.live_ui.app_connector import get_main_window
    from pywinauto.application import Application

    main_window = get_main_window()
    window = Application(backend="win32").connect(process=int(main_window.process_id())).window(handle=main_window.handle)
    for child in window.descendants():
        try:
            if child.class_name() in {"TChildWinForm", "TErrorMDIForm"} and child.is_visible():
                title = child.window_text().strip()
                if title:
                    return title
        except Exception:
            continue
    return None


def resolve_dynamic_context(menu: dict[str, Any], *, active_title: str | None, context_dir: Path = DEFAULT_CONTEXT_DIR) -> dict[str, Any]:
    """Resolve by stable MDI title while requiring an active dynamic menu shape."""
    signature = dynamic_context_signature(menu)
    if signature is None:
        return {"recognized": False, "reason": "no_dynamic_menu_signature", "signature": None}
    if not active_title:
        return {
            "recognized": False,
            "reason": "active_mdi_title_unavailable",
            "signature": list(signature),
        }
    evidence = documented_dynamic_context_titles(context_dir).get(active_title.casefold())
    if evidence is None:
        return {"recognized": False, "reason": "unknown_active_mdi_title", "signature": list(signature), "active_mdi_title": active_title}
    return {"recognized": True, "signature": list(signature), "active_mdi_title": active_title, "context": evidence}


def resolve_live_dynamic_context(context_dir: Path = DEFAULT_CONTEXT_DIR) -> dict[str, Any]:
    """Recognize the active dynamic MDI context without invoking any menu command.

    Unknown, non-editable, or ambiguous contexts are rejected.  Callers must
    require ``recognized`` before allowing a context-sensitive action.
    """
    from winwatt_automation.live_ui.native_menu import enumerate_native_menu

    live_menu = enumerate_native_menu()
    return resolve_dynamic_context(live_menu, active_title=active_mdi_title(), context_dir=context_dir)
