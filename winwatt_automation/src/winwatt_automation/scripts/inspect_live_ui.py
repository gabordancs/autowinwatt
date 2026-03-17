from __future__ import annotations

import argparse
import json
from pathlib import Path

from winwatt_automation.live_ui.app_connector import (
    WinWattMultipleWindowsError,
    WinWattNotRunningError,
    get_main_window,
    list_candidate_windows,
)
from winwatt_automation.live_ui.window_tree import save_window_tree_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _print_tree(node: dict, depth: int = 0) -> None:
    indent = "  " * depth
    name = node.get("name") or "<unnamed>"
    control_type = node.get("control_type") or "<unknown>"
    class_name = node.get("class_name") or "<unknown>"
    automation_id = node.get("automation_id") or "<none>"
    print(f"{indent}- {name} [{control_type}] class={class_name} automation_id={automation_id}")

    for child in node.get("children", []):
        _print_tree(child, depth + 1)


def _collect_control_names(node: dict, output: list[str]) -> None:
    name = str(node.get("name") or "").strip()
    if name:
        output.append(name)
    for child in node.get("children", []):
        _collect_control_names(child, output)


def _save_control_names(snapshot: dict, output_path: Path) -> Path:
    names: list[str] = []
    _collect_control_names(snapshot, names)
    unique_names = sorted(set(names), key=str.casefold)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(unique_names) + ("\n" if unique_names else ""), encoding="utf-8")
    return output_path


def _save_main_window_screenshot(output_path: Path) -> Path:
    main_window = get_main_window()
    image = main_window.capture_as_image()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return output_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect live WinWatt UI tree and optional artifacts")
    parser.add_argument("--controls-output", default=str(PROJECT_ROOT / "data/snapshots/control_names.txt"))
    parser.add_argument("--screenshot-output", default=str(PROJECT_ROOT / "data/snapshots/main_window.png"))
    parser.add_argument("--no-controls-export", action="store_true", help="Skip exporting unique control names")
    parser.add_argument("--screenshot", action="store_true", help="Capture a screenshot of the main WinWatt window")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    output_path = PROJECT_ROOT / "data/snapshots/ui_tree.json"
    candidates_path = PROJECT_ROOT / "data/snapshots/window_candidates.json"
    try:
        snapshot = save_window_tree_snapshot(output_path)
    except WinWattMultipleWindowsError as error:
        candidates = error.candidates
        if not candidates:
            candidates = list_candidate_windows(backend=error.backend)

        print("Connection failed due to multiple matching WinWatt windows.")
        print(f"Backend: {error.backend}")
        print("Candidate windows:")
        print(json.dumps(candidates, indent=2, ensure_ascii=False))

        candidates_path.parent.mkdir(parents=True, exist_ok=True)
        candidates_path.write_text(json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved candidate window dump to {candidates_path}")
        return 1
    except WinWattNotRunningError as error:
        print(f"Could not inspect WinWatt UI: {error}")
        return 1

    _print_tree(snapshot)
    print(f"\nSaved UI tree snapshot to {output_path}")

    if not args.no_controls_export:
        controls_output = _save_control_names(snapshot, Path(args.controls_output))
        print(f"Saved unique control names to {controls_output}")

    if args.screenshot:
        try:
            screenshot_output = _save_main_window_screenshot(Path(args.screenshot_output))
            print(f"Saved main window screenshot to {screenshot_output}")
        except Exception as error:  # runtime-only dependency / Win desktop state
            print(f"Could not capture screenshot: {error}")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
