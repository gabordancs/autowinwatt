"""Open catalog views one at a time and preserve visual evidence only.

The script deliberately clicks no controls inside the opened view and never
confirms, edits, saves, or deletes anything.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.live_ui.menu_helpers import (
    click_structured_popup_row,
    open_top_menu_and_capture_popup_state,
)
from winwatt_automation.live_ui.window_tree import save_window_tree_snapshot


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CATALOG_CAPTIONS = (
    "Anyagok",
    "Globális szerkezetek adatbázis",
    "Szerkezetek",
    "Helyiségek",
    "Épületek",
    "Egycsöves körök",
    "Felületfűtés-hűtés körök",
    "Ismert teljesítményű fogyasztók",
    "Hőcserélők, keverőszelepek",
    "Szakaszok",
    "Túláramszelepek",
    "Nyomáskülönbség szabályozók",
    "Csomópontok",
    "Hibalista",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely document WinWatt catalog MDI views")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "data" / "snapshots" / "catalog_view_probes"))
    parser.add_argument("--indices", default="0-13", help="Comma-separated popup row indexes or ranges")
    parser.add_argument("--no-tree", action="store_true", help="Capture the view screenshot and metadata without a full UI tree")
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    selected: list[int] = []
    for part in args.indices.split(","):
        start, separator, end = part.strip().partition("-")
        selected.extend(range(int(start), int(end) + 1) if separator else [int(start)])

    manifest: list[dict[str, object]] = []
    for index in selected:
        caption = CATALOG_CAPTIONS[index]
        popup = open_top_menu_and_capture_popup_state("Jegyzékek")
        clicked = click_structured_popup_row(popup["rows"], index)
        time.sleep(0.5)
        main_window = get_main_window()
        image = output_dir / f"{index:02d}_{caption}.png"
        tree = output_dir / f"{index:02d}_{caption}.json"
        main_window.capture_as_image().save(image)
        if not args.no_tree:
            save_window_tree_snapshot(tree)
        manifest.append({"index": index, "caption": caption, "clicked_rectangle": clicked["rectangle"], "screenshot": str(image), "tree": None if args.no_tree else str(tree)})

    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
