from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))
    package_dir = str(SRC_DIR / "winwatt_automation")
    package = sys.modules.get("winwatt_automation")
    if package is not None and hasattr(package, "__path__") and package_dir not in package.__path__:
        package.__path__.append(package_dir)

from winwatt_automation.live_ui.app_connector import WinWattNotRunningError
from winwatt_automation.live_ui.window_tree import save_window_tree_snapshot


def _print_tree(node: dict, depth: int = 0) -> None:
    indent = "  " * depth
    name = node.get("name") or "<unnamed>"
    control_type = node.get("control_type") or "<unknown>"
    class_name = node.get("class_name") or "<unknown>"
    automation_id = node.get("automation_id") or "<none>"
    print(f"{indent}- {name} [{control_type}] class={class_name} automation_id={automation_id}")

    for child in node.get("children", []):
        _print_tree(child, depth + 1)


def main() -> int:
    output_path = PROJECT_ROOT / "data/snapshots/ui_tree.json"
    try:
        snapshot = save_window_tree_snapshot(output_path)
    except WinWattNotRunningError as error:
        print(f"Could not inspect WinWatt UI: {error}")
        return 1

    _print_tree(snapshot)
    print(f"\nSaved UI tree snapshot to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
