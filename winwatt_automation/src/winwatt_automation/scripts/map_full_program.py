from __future__ import annotations

import argparse
from dataclasses import asdict

from winwatt_automation.runtime_mapping.program_mapper import build_full_runtime_program_map


def _parse_top_menus(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_bool(raw: str) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "y"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Map full WinWatt runtime structure")
    parser.add_argument("--project-path", default=None)
    parser.add_argument("--safe-mode", default="safe", choices=["safe", "caution", "blocked"])
    parser.add_argument("--output-dir", default="data/runtime_maps")
    parser.add_argument("--state-id-prefix", default="state")
    parser.add_argument("--top-menus", default="Fájl,Jegyzékek,Adatbázis,Beállítások,Ablak,Súgó")
    parser.add_argument("--max-submenu-depth", type=int, default=3)
    parser.add_argument("--include-disabled", default="true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = build_full_runtime_program_map(
        project_path=args.project_path,
        safe_mode=args.safe_mode,
        output_dir=args.output_dir,
        state_id_prefix=args.state_id_prefix,
        top_menus=_parse_top_menus(args.top_menus),
        max_submenu_depth=args.max_submenu_depth,
        include_disabled=_parse_bool(args.include_disabled),
    )

    no_project = result["state_no_project"]
    project_open = result["state_project_open"]
    diff = asdict(result["diff"])

    print("Runtime mapping completed")
    print(f"- no_project top_menus: {len(no_project.top_menus)}")
    print(f"- project_open top_menus: {len(project_open.top_menus)}")
    print(f"- diff summary: {diff.get('summary', {})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
