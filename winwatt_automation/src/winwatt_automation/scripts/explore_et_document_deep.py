"""Resume-capable same-session mapping of the ET certification editor."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from winwatt_automation.runtime_mapping.et_document import active_et_window, configure_et_scope, open_et_document
from winwatt_automation.runtime_mapping.room_deep_explorer import explore_room_state_graph
from winwatt_automation.version_profile import require_profile


PROTECTED_EXTERNAL_ACTIONS = {
    "feltölt", "beküld", "küldés", "oény", "hitelesít", "aláír",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument("--building-name")
    parser.add_argument("--zone-name")
    parser.add_argument("--structure-scope", choices=("all", "heated_boundary"), default="all")
    args = parser.parse_args()
    profile = require_profile(args.profile)
    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]

    def open_configured_root(project: str):
        dialog = open_et_document(project_path=project, reuse_session=True)
        configure_et_scope(
            dialog, building_name=args.building_name, zone_name=args.zone_name,
            structure_scope=args.structure_scope,
        )
        return dialog

    graph = explore_room_state_graph(
        project_path=str(args.project.resolve(strict=True)),
        output_dir=args.output_dir.resolve(),
        resume=args.resume,
        retry_failures=args.retry_failures,
        session_islands=True,
        exclude_action_names={"Bezárás", "Elvet", "OK"},
        exclude_action_substrings=PROTECTED_EXTERNAL_ACTIONS,
        root_opener=open_configured_root,
        active_resolver=active_et_window,
    )
    print({"states": len(graph["states"]), "edges": len(graph["edges"]), "complete": graph["complete"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
