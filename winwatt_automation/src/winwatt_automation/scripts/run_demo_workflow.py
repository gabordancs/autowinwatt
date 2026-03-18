from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from loguru import logger

from winwatt_automation.live_ui import menu_helpers
from winwatt_automation.runtime_logging.progress_display import launch_progress_overlay, write_progress_status
from winwatt_automation.runtime_mapping.menu_text import normalize_menu_title
from winwatt_automation.runtime_mapping.program_mapper import (
    _detect_child_rows,
    _find_popup_row_by_title,
    _hover_row,
    build_full_runtime_program_map,
    close_transient_dialog_or_window,
    restore_clean_menu_baseline,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a visible WinWatt menu walkthrough")
    parser.add_argument("--project-path", default=None)
    parser.add_argument("--safe-mode", default="off", choices=["safe", "hybrid", "caution", "blocked", "off", "unsafe"])
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "data/runtime_maps"))
    parser.add_argument("--pause-ms", type=int, default=800)
    parser.add_argument("--max-submenu-depth", type=int, default=-1, help="Use -1 for unlimited menu traversal depth")
    parser.add_argument("--skip-remap", action="store_true", help="Replay the existing saved menu tree instead of remapping first")
    parser.add_argument("--progress-overlay", action="store_true", help="Show a non-activating status HUD while the walkthrough runs")
    return parser


def _iter_menu_paths(nodes: list[dict], prefix: list[str] | None = None) -> list[list[str]]:
    prefix = list(prefix or [])
    paths: list[list[str]] = []
    for node in nodes:
        path = prefix + [str(node.get("title") or "")]
        paths.append(path)
        children = list(node.get("children") or [])
        if children:
            paths.extend(_iter_menu_paths(children, path))
    return paths


def _load_walkthrough_paths(output_dir: Path) -> list[list[str]]:
    paths: list[list[str]] = []
    for state_name in ("state_no_project", "state_project_open"):
        menu_tree_path = output_dir / state_name / "menu_tree.json"
        if not menu_tree_path.exists():
            continue
        payload = json.loads(menu_tree_path.read_text(encoding="utf-8"))
        for top_menu in payload:
            root = [str(top_menu.get("title") or "")]
            paths.append(root)
            paths.extend(_iter_menu_paths(list(top_menu.get("children") or []), root))
    deduped: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for path in paths:
        normalized = tuple(normalize_menu_title(part) for part in path if part)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(path)
    return deduped


def _pause(pause_ms: int) -> None:
    time.sleep(max(0.0, pause_ms / 1000.0))


def _replay_menu_path(path: list[str], *, pause_ms: int) -> None:
    if not path:
        return

    restore_clean_menu_baseline(state_id="walkthrough", stage="before_path")
    top_menu = path[0]
    menu_helpers.click_top_menu_item(top_menu)
    _pause(pause_ms)

    rows = menu_helpers.capture_menu_popup_snapshot()
    if len(path) == 1:
        return

    for index, title in enumerate(path[1:], start=1):
        row = _find_popup_row_by_title(rows, title)
        if row is None:
            raise RuntimeError(f"Could not find walkthrough row: {' > '.join(path[: index + 1])}")

        is_last = index == len(path) - 1
        if is_last:
            row_index = next(i for i, candidate in enumerate(rows) if candidate is row)
            menu_helpers.click_structured_popup_row(rows, row_index)
            _pause(pause_ms)
            close_transient_dialog_or_window(None, action_label=f"walkthrough:{' > '.join(path)}")
            return

        _hover_row(row)
        _pause(pause_ms)
        snapshot_rows = menu_helpers.capture_menu_popup_snapshot()
        rows = _detect_child_rows(row, snapshot_rows)
        if not rows:
            raise RuntimeError(f"Submenu did not open for walkthrough path: {' > '.join(path[: index + 1])}")


def main() -> int:
    args = _build_parser().parse_args()
    output_dir = Path(args.output_dir)
    status_path = output_dir / "walkthrough_status.json"

    write_progress_status(status_path, run_id="walkthrough", state="starting", message="A walkthrough indul…")
    if args.progress_overlay:
        launch_progress_overlay(status_path)

    if not args.skip_remap:
        write_progress_status(status_path, run_id="walkthrough", state="running", message="Menüstruktúra újramappelése folyamatban…")
        build_full_runtime_program_map(
            project_path=args.project_path,
            safe_mode=args.safe_mode,
            output_dir=output_dir,
            max_submenu_depth=None if args.max_submenu_depth < 0 else args.max_submenu_depth,
        )

    paths = _load_walkthrough_paths(output_dir)
    if not paths:
        write_progress_status(status_path, run_id="walkthrough", state="failed", message="Nem található visszajátszható menüútvonal.")
        print(f"No walkthrough paths found under: {output_dir}")
        return 1

    print(f"Walkthrough path count: {len(paths)}")
    failures: list[str] = []
    for path in paths:
        printable = " > ".join(path)
        print(f"[walkthrough] {printable}")
        write_progress_status(status_path, run_id="walkthrough", state="running", message=f"Épp ezt játssza vissza: {printable}")
        try:
            _replay_menu_path(path, pause_ms=args.pause_ms)
        except Exception as exc:
            logger.warning("walkthrough_failed path={} error={}", printable, exc)
            failures.append(f"{printable}: {exc}")
        finally:
            restore_clean_menu_baseline(state_id="walkthrough", stage="after_path")
            _pause(args.pause_ms)

    if failures:
        write_progress_status(status_path, run_id="walkthrough", state="failed", message="A walkthrough hibákkal fejeződött be.", details={"failures": failures})
        print("Walkthrough finished with failures:")
        for item in failures:
            print(f"- {item}")
        return 1

    write_progress_status(status_path, run_id="walkthrough", state="finished", message="A walkthrough sikeresen befejeződött.")
    print("Walkthrough finished successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
