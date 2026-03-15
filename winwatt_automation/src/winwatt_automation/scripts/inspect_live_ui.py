from __future__ import annotations

import json
from pathlib import Path

from winwatt_automation.live_ui.app_connector import (
    WinWattMultipleWindowsError,
    WinWattNotRunningError,
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


def main() -> int:
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
