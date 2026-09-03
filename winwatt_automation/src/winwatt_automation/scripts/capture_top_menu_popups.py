"""Capture each visible top-level WinWatt menu without invoking its commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from winwatt_automation.live_ui.app_connector import get_main_window


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture top-level WinWatt menu popups safely")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "data" / "snapshots" / "top_menu_popups"))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    main_window = get_main_window()
    menu_bar = next(
        control
        for control in main_window.descendants(control_type="MenuBar")
        if control.window_text().strip() == "Alkalmazás"
    )
    captured = []
    for index, item in enumerate(menu_bar.children(control_type="MenuItem")):
        caption = item.window_text().strip() or f"menu_{index}"
        safe_name = "".join(character if character.isalnum() else "_" for character in caption).strip("_")
        item.click_input()
        image_path = output_dir / f"{index:02d}_{safe_name}.png"
        main_window.capture_as_image().save(image_path)
        main_window.type_keys("{ESC}")
        captured.append(str(image_path))
    print("\n".join(captured))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
