"""Capture native menu context for each safe-to-open WinWatt catalog view.

This deliberately uses only the existing Jegyzekek popup rows.  It does not
select records or invoke any context-sensitive command inside the opened MDI
views.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.live_ui.menu_helpers import click_structured_popup_row, open_top_menu_and_capture_popup_state
from winwatt_automation.live_ui.native_menu import enumerate_native_menu
from winwatt_automation.scripts.probe_catalog_views import CATALOG_CAPTIONS


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _parse_indices(value: str) -> list[int]:
    values: list[int] = []
    for part in value.split(","):
        start, separator, end = part.strip().partition("-")
        values.extend(range(int(start), int(end) + 1) if separator else [int(start)])
    if not values or any(index < 0 or index >= len(CATALOG_CAPTIONS) for index in values):
        raise ValueError("indices must refer to known catalog rows")
    return values


def _capture_dynamic_menu_popups(index: int, output_dir: Path) -> list[str]:
    """Save the three context-sensitive menu popups without invoking commands."""
    main_window = get_main_window()
    menu_bar = next(
        control
        for control in main_window.descendants(control_type="MenuBar")
        if control.window_text().strip() == "Alkalmaz\u00e1s"
    )
    menu_items = menu_bar.children(control_type="MenuItem")
    popup_dir = output_dir / "dynamic_menu_popups" / f"{index:02d}_{CATALOG_CAPTIONS[index]}"
    popup_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for name in ("Szerkeszt\u00e9s", "Csoport", "Elem"):
        item = next((candidate for candidate in menu_items if candidate.window_text().strip() == name), None)
        if item is None:
            raise RuntimeError(f"Missing expected dynamic menu {name!r} for catalog index {index}")
        item.click_input()
        safe_name = "".join(character if character.isalnum() else "_" for character in name)
        path = popup_dir / f"{safe_name}.png"
        main_window.capture_as_image().save(path)
        main_window.type_keys("{ESC}")
        paths.append(str(path))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely snapshot catalog-specific native menu contexts")
    parser.add_argument("--indices", default="0-13")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "data" / "runtime_maps" / "catalog_contexts_9_60"))
    parser.add_argument("--capture-dynamic-popups", action="store_true")
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    for index in _parse_indices(args.indices):
        popup = open_top_menu_and_capture_popup_state("Jegyz\u00e9kek")
        click_structured_popup_row(popup["rows"], index)
        time.sleep(0.5)
        caption = CATALOG_CAPTIONS[index]
        menu_path = output_dir / f"{index:02d}_{caption}.json"
        screenshot_path = output_dir / f"{index:02d}_{caption}.png"
        menu_path.write_text(json.dumps(enumerate_native_menu(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        get_main_window().capture_as_image().save(screenshot_path)
        dynamic_popups = _capture_dynamic_menu_popups(index, output_dir) if args.capture_dynamic_popups else []
        manifest.append({"index": index, "caption": caption, "native_menu": str(menu_path), "screenshot": str(screenshot_path), "dynamic_menu_popups": dynamic_popups})
    # Preserve evidence from prior partial invocations.  This makes a timeout
    # recoverable: the manifest is rebuilt from actual JSON snapshots instead
    # of claiming only the rows from the latest process invocation.
    all_entries: list[dict[str, object]] = []
    for menu_path in sorted(output_dir.glob("*.json")):
        if menu_path.name == "manifest.json":
            continue
        prefix, _, caption = menu_path.stem.partition("_")
        if not prefix.isdigit():
            continue
        screenshot_path = menu_path.with_suffix(".png")
        popup_dir = output_dir / "dynamic_menu_popups" / menu_path.stem
        all_entries.append({
            "index": int(prefix),
            "caption": caption,
            "native_menu": str(menu_path),
            "screenshot": str(screenshot_path) if screenshot_path.exists() else None,
            "dynamic_menu_popups": [str(path) for path in sorted(popup_dir.glob("*.png"))],
        })
    all_entries.sort(key=lambda entry: int(entry["index"]))
    (output_dir / "manifest.json").write_text(json.dumps(all_entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output_dir), "mapped_context_count": len(all_entries)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
