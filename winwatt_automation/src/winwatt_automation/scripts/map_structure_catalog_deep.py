"""CLI for deterministic, sandbox-only Structure Catalog Deep Mapper v0."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from winwatt_automation.runtime_mapping.structure_catalog_deep_mapper import StructureCatalogDeepMapper

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-actions", type=int, default=30)
    parser.add_argument("--no-import-navigation", action="store_true")
    parser.add_argument("--focus-creation", action="store_true")
    parser.add_argument("--probe-input", action="store_true", help="Write AI_TEST_<run-id> to one observed enabled Edit.")
    parser.add_argument("--commit-creation", action="store_true", help="Explicitly click an observed enabled commit button and save the sandbox project; requires --probe-input.")
    parser.add_argument("--existing-item", help="Select this persisted sandbox structure first, then map its visible safe controls.")
    args = parser.parse_args()
    if args.commit_creation and not args.probe_input:
        parser.error("--commit-creation requires --probe-input")
    result = StructureCatalogDeepMapper(source_project=args.project, output_dir=args.output_dir, max_actions=args.max_actions, import_navigation=not args.no_import_navigation, focus_creation=args.focus_creation, probe_input=args.probe_input, commit_creation=args.commit_creation, existing_item=args.existing_item).run()
    print(json.dumps(result, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
