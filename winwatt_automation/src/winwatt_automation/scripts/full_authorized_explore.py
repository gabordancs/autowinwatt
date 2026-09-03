"""Run the unrestricted WinWatt mapper against a freshly copied sandbox project.

This is the explicit destructive-execution entry point.  The source project is
never used as the mapping target: each run creates a timestamped `.wwp` copy
under the requested sandbox directory, then gives the existing full runtime
mapper permission to invoke every enabled menu leaf and to restart WinWatt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from winwatt_automation.runtime_mapping.mdi_state_model import activate_rooms_catalog, capture_active_mdi_state
from winwatt_automation.runtime_mapping.program_mapper import (
    DEFAULT_TEST_PROJECT_PATH,
    build_full_runtime_program_map,
    prepare_fresh_winwatt_session,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SANDBOX_ROOT = PROJECT_ROOT / "data" / "runtime_maps" / "full_authorized_sandbox"
DEFAULT_RUNS_ROOT = PROJECT_ROOT / "data" / "runtime_maps" / "full_authorized_runs"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_execution_sandbox(*, source_project: Path, sandbox_root: Path, run_id: str) -> dict[str, str]:
    """Copy a validated project to a new, never-overwritten execution target."""
    source = source_project.resolve()
    root = sandbox_root.resolve()
    if source.suffix.casefold() != ".wwp" or not source.is_file():
        raise ValueError(f"Expected an existing .wwp source project, got: {source}")
    try:
        source.relative_to(root)
    except ValueError:
        pass
    else:
        raise ValueError("Refusing to use a previous execution sandbox as the source project")
    target_dir = root / run_id
    target = target_dir / source.name
    if target.exists():
        raise FileExistsError(f"Execution target already exists: {target}")
    target_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source, target)
    return {
        "source_project": str(source),
        "source_sha256": _sha256(source),
        "sandbox_project": str(target),
        "sandbox_sha256_before_execution": _sha256(target),
    }


def run_full_authorized_exploration(*, source_project: Path, sandbox_root: Path = DEFAULT_SANDBOX_ROOT, runs_root: Path = DEFAULT_RUNS_ROOT) -> dict[str, Any]:
    """Map every state reachable by the existing unrestricted runtime mapper."""
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sandbox = create_execution_sandbox(source_project=source_project, sandbox_root=sandbox_root, run_id=run_id)
    run_dir = runs_root.resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "manifest.json"
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "authorization": "unrestricted_menu_execution_on_disposable_sandbox_only",
        "sandbox": sandbox,
        "rooms_seed": None,
        "full_runtime_result": None,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Establish and preserve the requested rooms-first evidence before the
    # unrestricted traversal intentionally changes application state.
    prepare_fresh_winwatt_session(project_path=sandbox["sandbox_project"])
    activate_rooms_catalog()
    rooms_state = capture_active_mdi_state(output_dir=run_dir / "mdi_states")
    manifest["rooms_seed"] = {
        "state_id": rooms_state["state_id"],
        "active_mdi_title": rooms_state["active_mdi_title"],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # `unsafe` admits every safety class.  This is safe only because the
    # target is the fresh sandbox copy created above.
    result = build_full_runtime_program_map(
        project_path=sandbox["sandbox_project"],
        safe_mode="unsafe",
        output_dir=run_dir / "runtime",
        state_id_prefix="full",
        max_submenu_depth=-1,
        include_disabled=True,
        allow_process_restart=True,
    )
    sandbox_path = Path(sandbox["sandbox_project"])
    manifest["sandbox"]["sandbox_sha256_after_execution"] = _sha256(sandbox_path) if sandbox_path.exists() else None
    manifest["full_runtime_result"] = {
        "no_project_state": result["state_no_project"].state_id,
        "project_open_state": result["state_project_open"].state_id,
        "no_project_actions": len(result["state_no_project"].actions),
        "project_open_actions": len(result["state_project_open"].actions),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute a full WinWatt state-space map in a disposable project copy")
    parser.add_argument("--source-project", default=DEFAULT_TEST_PROJECT_PATH)
    parser.add_argument("--sandbox-root", default=str(DEFAULT_SANDBOX_ROOT))
    parser.add_argument("--runs-root", default=str(DEFAULT_RUNS_ROOT))
    parser.add_argument("--execute", action="store_true", help="Required acknowledgement: this invokes all enabled menu leaves in the sandbox")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required because this mode invokes destructive and state-changing menu commands")
    manifest = run_full_authorized_exploration(
        source_project=Path(args.source_project),
        sandbox_root=Path(args.sandbox_root),
        runs_root=Path(args.runs_root),
    )
    print(json.dumps({"run_id": manifest["run_id"], "sandbox": manifest["sandbox"]["sandbox_project"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
