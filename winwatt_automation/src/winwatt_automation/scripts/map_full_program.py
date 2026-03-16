from __future__ import annotations

import argparse
from dataclasses import asdict

from winwatt_automation.runtime_mapping.program_mapper import build_full_runtime_program_map


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Map full WinWatt runtime structure")
    parser.add_argument("--project-path", default=None)
    parser.add_argument("--safe-mode", default="safe", choices=["safe", "caution", "blocked"])
    parser.add_argument("--output-dir", default="data/runtime_maps")
    parser.add_argument("--state-id-prefix", default="state")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = build_full_runtime_program_map(
        project_path=args.project_path,
        safe_mode=args.safe_mode,
        output_dir=args.output_dir,
        state_id_prefix=args.state_id_prefix,
    )

    no_project = result["state_no_project"]
    project_open = result["state_project_open"]
    diff = asdict(result["diff"])

    print("Runtime mapping completed")
    print(f"- no_project top_menus: {len(no_project.top_menus)}")
    print(f"- no_project menu_rows: {len(no_project.menu_rows)}")
    print(f"- no_project actions attempted: {sum(1 for action in no_project.actions if action.get('attempted'))}")
    print(f"- no_project dialogs found: {len(no_project.dialogs)}")
    print(f"- no_project windows found: {len(no_project.windows)}")
    print(f"- no_project skipped actions: {len(no_project.skipped_actions)}")
    print(f"- project_open top_menus: {len(project_open.top_menus)}")
    print(f"- project_open menu_rows: {len(project_open.menu_rows)}")
    print(f"- project_open actions attempted: {sum(1 for action in project_open.actions if action.get('attempted'))}")
    print(f"- project_open dialogs found: {len(project_open.dialogs)}")
    print(f"- project_open windows found: {len(project_open.windows)}")
    print(f"- project_open skipped actions: {len(project_open.skipped_actions)}")
    print(f"- diff summary: {diff.get('summary', {})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
