"""Learn a deep-exploration root for arbitrary WinWatt catalogs.

Unlike the original room runner this does not assume a tabbed editor, a known
record type, or a fixed ``Elem`` command index.  It explores the catalog's
tree/list selection context first, then probes enabled element-menu commands
in a disposable project until a real top-level editor/dialog is observed.
The successful route is stored as a reusable profile for a later graph run.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pywinauto import Application, Desktop, keyboard

from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.runtime_mapping.program_mapper import prepare_fresh_winwatt_session
from winwatt_automation.scripts.probe_catalog_views import CATALOG_CAPTIONS


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _visible_secondary(process_id: int) -> Any | None:
    windows = [
        item for item in Desktop(backend="uia").windows(top_level_only=True)
        if item.process_id() == process_id and item.class_name() != "TMainForm" and item.is_visible()
    ]
    if not windows:
        return None
    windows.sort(key=lambda item: item.rectangle().width() * item.rectangle().height(), reverse=True)
    return windows[0]


def _open_catalog(project: Path, index: int) -> tuple[Any, Any]:
    prepare_fresh_winwatt_session(project_path=str(project))
    main = get_main_window()
    native = Application(backend="win32").connect(process=int(main.process_id())).window(handle=int(main.handle))
    catalog = next(item for item in native.menu().items() if item.text().replace("&", "").strip() == "Jegyzékek")
    catalog.click(); time.sleep(0.15)
    catalog.sub_menu().items()[index].click(); time.sleep(0.5)
    child = next(item for item in main.descendants() if item.class_name() == "TChildWinForm" and item.is_visible())
    return main, child


def _menu_commands(main: Any) -> list[dict[str, Any]]:
    native = Application(backend="win32").connect(process=int(main.process_id())).window(handle=int(main.handle))
    menu = next(item for item in native.menu().items() if item.text().replace("&", "").strip() == "Elem")
    menu.click(); time.sleep(0.1)
    result = [{"index": index, "enabled": bool(item.is_enabled()), "caption": item.text()}
              for index, item in enumerate(menu.sub_menu().items())]
    main.type_keys("{ESC}")
    return result


def _select_context(child: Any) -> list[dict[str, Any]]:
    """Return small, deterministic context attempts without hardcoded labels."""
    attempts: list[dict[str, Any]] = [{"tree": None, "list": None}]
    trees = [item for item in child.descendants(control_type="TreeItem") if item.is_visible() and item.is_enabled()]
    for tree in trees[:12]:
        attempts.append({"tree": tree.window_text(), "list": None})
    return attempts


def _apply_context(child: Any, attempt: dict[str, Any]) -> None:
    label = attempt.get("tree")
    if label:
        tree = next(item for item in child.descendants(control_type="TreeItem") if item.window_text() == label and item.is_visible())
        tree.click_input(); time.sleep(0.25)
    items = [item for item in child.descendants(control_type="ListItem") if item.is_visible() and item.is_enabled()]
    if items:
        items[0].click_input(); time.sleep(0.15)
        attempt["list"] = items[0].window_text()


def _submit_new_group(dialog: Any, name: str) -> bool:
    edits = [item for item in dialog.descendants(control_type="Edit") if item.is_visible()]
    if not edits:
        return False
    edits[0].set_edit_text(name)
    dialog.set_focus(); keyboard.send_keys("{ENTER}")
    return True


def discover(*, project: Path, catalog_index: int, output: Path, probe_name: str) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    attempts: list[dict[str, Any]] = []
    # Every probe restarts from an untouched copy, so an attempted creation or
    # confirmation cannot affect the next branch or the user's project.
    template = PROJECT_ROOT / "tests" / "testwwp.wwp"
    for round_no in range(1, 30):
        shutil.copy2(template, project)
        main, child = _open_catalog(project, catalog_index)
        process_id = int(main.process_id())
        contexts = _select_context(child)
        for context in contexts:
            try:
                _apply_context(child, context)
                commands = _menu_commands(main)
                for command in commands:
                    if not command["enabled"]:
                        continue
                    # Reload the clean catalog state for every command.
                    shutil.copy2(template, project)
                    main, child = _open_catalog(project, catalog_index)
                    process_id = int(main.process_id())
                    _apply_context(child, dict(context))
                    native = Application(backend="win32").connect(process=process_id).window(handle=int(main.handle))
                    element = next(item for item in native.menu().items() if item.text().replace("&", "").strip() == "Elem")
                    element.click(); time.sleep(0.1)
                    element.sub_menu().items()[int(command["index"])].click(); time.sleep(0.45)
                    dialog = _visible_secondary(process_id)
                    attempt = {"round": round_no, "context": context, "command": command,
                               "dialog_before_submit": None if dialog is None else {"class": dialog.class_name(), "title": dialog.window_text()}}
                    if dialog is not None and dialog.class_name() == "TNewGroupForm":
                        _submit_new_group(dialog, probe_name)
                        time.sleep(0.6)
                        dialog = _visible_secondary(process_id)
                        attempt["dialog_after_submit"] = None if dialog is None else {"class": dialog.class_name(), "title": dialog.window_text()}
                    attempts.append(attempt)
                    if dialog is not None and dialog.class_name() not in {"TNewGroupForm", "TMainForm"}:
                        profile = {"schema_version": 1, "catalog_index": catalog_index, "catalog_caption": CATALOG_CAPTIONS[catalog_index],
                                   "discovered_at": datetime.now(timezone.utc).isoformat(), "context": context,
                                   "element_command": command, "root_window": {"class": dialog.class_name(), "title": dialog.window_text()},
                                   "probe_name": probe_name, "attempts": attempts}
                        (output / "root_profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                        dialog.capture_as_image().save(output / "root.png")
                        return profile
            except Exception as exc:
                attempts.append({"round": round_no, "context": context, "error": str(exc)})
    result = {"schema_version": 1, "catalog_index": catalog_index, "catalog_caption": CATALOG_CAPTIONS[catalog_index],
              "status": "root_not_found", "attempts": attempts}
    (output / "root_profile.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-index", required=True, type=int)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--probe-name", default="Auto exploration probe")
    args = parser.parse_args()
    if args.catalog_index < 0 or args.catalog_index >= len(CATALOG_CAPTIONS):
        parser.error("unknown catalog index")
    profile = discover(project=args.project.resolve(), catalog_index=args.catalog_index, output=args.output_dir.resolve(), probe_name=args.probe_name)
    print(json.dumps({"catalog": profile["catalog_caption"], "root": profile.get("root_window"), "status": profile.get("status", "found")}, ensure_ascii=False))
    return 0 if profile.get("root_window") else 1


if __name__ == "__main__":
    raise SystemExit(main())
