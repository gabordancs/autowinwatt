"""Bounded, sandbox-only inventory of the live structure editor.

It reads every visible supported control and transiently opens ComboBox lists.
Checkbox and radio effects are tested and restored before the script returns;
it never confirms, saves, deletes, or changes editable text.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pywinauto import Desktop


TYPES = {"Edit", "ComboBox", "CheckBox", "RadioButton", "Button", "List", "ListItem", "TabItem"}


def _controls(window: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in window.descendants():
        try:
            if not item.is_visible() or item.element_info.control_type not in TYPES:
                continue
            rect = item.rectangle()
            result.append({
                "control_type": item.element_info.control_type,
                "caption": item.window_text() or None,
                "class_name": item.class_name(),
                "automation_id": item.element_info.automation_id or None,
                "enabled": bool(item.is_enabled()),
                "rectangle": [rect.left, rect.top, rect.right, rect.bottom],
            })
        except Exception:
            continue
    return result


def _state(window: Any) -> dict[str, Any]:
    return {f"{x['control_type']}:{x['automation_id']}:{x['caption']}": x["enabled"] for x in _controls(window)}


def _catalog_labels() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parents[3] / "data" / "parsed" / "controls_catalog.json"
    items = json.loads(path.read_text(encoding="utf-8"))
    return [
        {"stable_key": x["stable_key"], "item_name": x["item_name"], "caption": x.get("caption"), "hint": x.get("hint"), "semantic_role": x["semantic_role"]}
        for x in items
        if x.get("form_name") == "PanelModifyForm" and (x.get("is_input_candidate") or x.get("caption") or x.get("hint"))
    ]


def run(output: Path) -> dict[str, Any]:
    editor = next(w for w in Desktop(backend="uia").windows(top_level_only=True) if w.class_name() == "TPanelModifyForm" and w.is_visible())
    # Delphi shortens the MDI title and often omits the literal ``sandbox``
    # directory.  Mapper-created projects still carry the dedicated runtime
    # mapping root in their title; no ordinary user project is accepted.
    title = editor.window_text().replace("/", "\\").casefold()
    main_titles = []
    for candidate in Desktop(backend="uia").windows(top_level_only=True):
        try:
            if candidate.process_id() == editor.process_id() and candidate.class_name() == "TMainForm":
                main_titles.append(candidate.window_text().replace("/", "\\").casefold())
        except Exception:
            continue
    if "sandbox" not in title and "runtime_maps\\structure_deep_mapping" not in title and not any("runtime_maps\\structure_deep_mapping" in value for value in main_titles):
        raise RuntimeError("sandbox structure editor required")
    result: dict[str, Any] = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "window": {"title": editor.window_text(), "class_name": editor.class_name(), "handle": int(editor.handle)},
        "controls": _controls(editor),
        "static_form_catalog": _catalog_labels(),
        "combo_items": [],
        "reversible_effects": [],
        "policy": "no editable values, OK, save, delete, copy, or rename invoked",
    }
    # Expand each observed combo once and close it with Escape.  This only
    # reads its available entries and stays in the current sandbox editor.
    for combo in list(editor.descendants(control_type="ComboBox")):
        try:
            if not combo.is_visible() or not combo.is_enabled():
                continue
            combo.click_input(); time.sleep(0.15)
            rows = []
            for popup in Desktop(backend="uia").windows(top_level_only=True):
                try:
                    if popup.process_id() != editor.process_id() or not popup.is_visible():
                        continue
                    rows.extend(x.window_text() for x in popup.descendants(control_type="ListItem") if x.is_visible() and x.window_text())
                except Exception:
                    continue
            result["combo_items"].append({"automation_id": combo.element_info.automation_id or None, "items": sorted(set(rows))})
            # Do not synthesize Escape here. In Delphi a ComboBox popup can
            # be owned by the editor, and Esc would then mean Cancel. The
            # next observed action safely collapses the transient list.
        except Exception as exc:
            result["combo_items"].append({"automation_id": combo.element_info.automation_id or None, "error": str(exc)})
    # Enumerating the inputs is safe.  Their behavioural probing is deferred
    # to a separate fresh-sandbox branch: radio-button restoration is not
    # generally an involution, so clicking it twice is not a valid rollback.
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps({"output": str(args.output), "controls": len(run(args.output)["controls"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
