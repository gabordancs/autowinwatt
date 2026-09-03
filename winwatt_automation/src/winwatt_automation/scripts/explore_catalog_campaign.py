"""Run the reusable deep state explorer over all remaining WinWatt catalogs.

Each catalog is isolated in its own disposable project copy.  This prevents
one catalog's creation/edit branches from changing the root state of another
catalog and makes the resulting subgraphs independently transferable to a
second worker later.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pywinauto import Application, Desktop

from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.runtime_mapping.context_guard import active_mdi_title
from winwatt_automation.runtime_mapping.program_mapper import prepare_fresh_winwatt_session
from winwatt_automation.runtime_mapping.room_deep_explorer import explore_room_state_graph
from winwatt_automation.scripts.probe_catalog_views import CATALOG_CAPTIONS


PROJECT_ROOT = Path(__file__).resolve().parents[3]
# Helyiségek has their own established deep runner.  The other entries are
# the missing campaign roots; Buildings are intentionally included because
# their dedicated editor route is still being stabilized separately.
DEFAULT_INDICES = tuple(index for index in range(len(CATALOG_CAPTIONS)) if index != 3)


def _slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _open_catalog(project_path: str, index: int) -> Any:
    prepare_fresh_winwatt_session(project_path=project_path)
    main = get_main_window()
    native = Application(backend="win32").connect(process=int(main.process_id())).window(handle=int(main.handle))
    catalog_menu = next(item for item in native.menu().items() if item.text().replace("&", "").strip() == "Jegyzékek")
    catalog_menu.click()
    time.sleep(0.15)
    catalog_menu.sub_menu().items()[index].click()
    time.sleep(0.5)
    return _active_catalog_window(int(main.process_id()), CATALOG_CAPTIONS[index])


def _active_catalog_window(process_id: int, expected_title: str) -> Any:
    dialogs = [
        window for window in Desktop(backend="uia").windows(top_level_only=True)
        if window.process_id() == process_id and window.class_name() != "TMainForm"
        and window.is_visible() and window.is_enabled()
    ]
    if dialogs:
        dialogs.sort(key=lambda item: item.rectangle().width() * item.rectangle().height(), reverse=True)
        return dialogs[0]
    main = get_main_window()
    observed = active_mdi_title() or expected_title
    candidates = [
        item for item in main.descendants()
        if item.class_name() == "TChildWinForm" and item.window_text().strip() == observed
        and item.is_visible() and item.is_enabled()
    ]
    if not candidates:
        raise RuntimeError(f"Catalog MDI child is not active: expected={expected_title!r}, observed={observed!r}")
    return candidates[0]


def _parse_indices(value: str) -> list[int]:
    result: list[int] = []
    for piece in value.split(","):
        start, separator, end = piece.strip().partition("-")
        result.extend(range(int(start), int(end) + 1) if separator else [int(start)])
    if any(index < 0 or index >= len(CATALOG_CAPTIONS) for index in result):
        raise ValueError("catalog index out of range")
    return list(dict.fromkeys(result))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--indices", default=",".join(map(str, DEFAULT_INDICES)))
    parser.add_argument("--source-project", default=str(PROJECT_ROOT / "tests" / "testwwp.wwp"))
    parser.add_argument("--session-islands", action="store_true")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = Path(args.source_project).resolve()
    selected = _parse_indices(args.indices)
    manifest: dict[str, Any] = {
        "schema_version": 1, "started_at": datetime.now(timezone.utc).isoformat(),
        "source_project": str(source), "selected_indices": selected, "catalogs": [],
        "reuse_sources": ["room_deep_runs", "catalog_contexts_9_60", "mdi_runtime_states_9_60"],
    }
    _write(output / "manifest.json", manifest)
    for position, index in enumerate(selected, start=1):
        caption = CATALOG_CAPTIONS[index]
        slug = f"{index:02d}_{_slug(caption)}"
        catalog_dir = output / slug
        project = output / "sandboxes" / slug / source.name
        project.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, project)
        entry: dict[str, Any] = {"index": index, "caption": caption, "project": str(project), "output": str(catalog_dir), "status": "running"}
        manifest["catalogs"].append(entry)
        _write(output / "manifest.json", manifest)
        _write(output / "progress.json", {"states": 0, "edges": 0, "failures": 0,
                                             "queue": len(selected) - position + 1, "complete": False,
                                             "catalog": caption, "catalog_completed": position - 1,
                                             "catalog_total": len(selected), "updated_at": datetime.now(timezone.utc).isoformat()})
        try:
            graph = explore_room_state_graph(
                project_path=str(project), output_dir=catalog_dir, session_islands=args.session_islands,
                root_opener=lambda path, catalog_index=index: _open_catalog(path, catalog_index),
                active_resolver=lambda process_id, title=caption: _active_catalog_window(process_id, title),
            )
            entry.update({"status": "completed", "states": len(graph["states"]), "edges": len(graph["edges"]), "failures": len(graph["failures"])})
        except Exception as exc:
            entry.update({"status": "failed", "error": str(exc)})
        _write(output / "manifest.json", manifest)
    _write(output / "progress.json", {"states": sum(int(item.get("states", 0)) for item in manifest["catalogs"]),
                                         "edges": sum(int(item.get("edges", 0)) for item in manifest["catalogs"]),
                                         "failures": sum(int(item.get("failures", 1 if item["status"] == "failed" else 0)) for item in manifest["catalogs"]),
                                         "queue": 0, "complete": True, "catalog_completed": len(selected),
                                         "catalog_total": len(selected), "updated_at": datetime.now(timezone.utc).isoformat()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
