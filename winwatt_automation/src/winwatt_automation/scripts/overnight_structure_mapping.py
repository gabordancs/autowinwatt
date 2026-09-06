"""Unattended sandbox-only Structure Catalog mapping until a wall-clock deadline.

The runner reuses StructureCatalogDeepMapper and existing verified project/session
operations. It may commit disposable AI_TEST_* structures in sandbox copies, then
closes/reopens WinWatt and requires exact readback before treating creation as
roundtrip verified. The original source project is never modified.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.research.ui_exploration import SandboxUIExplorer
from winwatt_automation.runtime_mapping.mdi_state_model import (
    activate_structures_catalog_native,
    active_mdi_title,
)
from winwatt_automation.runtime_mapping.structure_catalog_deep_mapper import StructureCatalogDeepMapper
from winwatt_automation.services.winwatt_service import WinWattService


def parse_stop_at(value: str) -> datetime:
    try:
        hour, minute = (int(part) for part in value.split(":", 1))
    except Exception as exc:
        raise argparse.ArgumentTypeError("--stop-at must be HH:MM") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise argparse.ArgumentTypeError("--stop-at must be HH:MM")
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def verify_created_structure(run_dir: Path, source_project_name: str) -> dict[str, Any]:
    sandbox = run_dir / "sandbox" / source_project_name
    expected_name = f"AI_TEST_{run_dir.name}"
    service = WinWattService()
    try:
        service.close_project_gracefully()
    except Exception:
        pass
    service.open_project(sandbox)
    if not activate_structures_catalog_native() or active_mdi_title() != "Szerkezetek":
        return {
            "verified": False,
            "expected_name": expected_name,
            "reason": "catalog.structure.open failed after reopen",
        }
    explorer = SandboxUIExplorer(get_main_window(), sandbox)
    state = explorer.inspect_window()
    match = next(
        (
            item
            for item in state.controls
            if item.control_type == "ListItem"
            and item.caption == expected_name
            and item.enabled
        ),
        None,
    )
    return {
        "verified": match is not None,
        "expected_name": expected_name,
        "matched_identity": match.identity if match else None,
        "state_fingerprint": state.state_fingerprint,
        "reason": None if match else "exact AI_TEST structure not found after reopen",
    }


def catalog_references(project: Path) -> list[str]:
    service = WinWattService()
    service.open_project(project)
    if not activate_structures_catalog_native() or active_mdi_title() != "Szerkezetek":
        raise RuntimeError("verified catalog.structure.open did not reach Szerkezetek")
    explorer = SandboxUIExplorer(get_main_window(), project)
    state = explorer.inspect_window()
    return sorted(
        {
            item.caption
            for item in state.controls
            if item.control_type == "ListItem"
            and item.enabled
            and item.caption
            and not item.caption.startswith("AI_TEST_")
        }
    )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Unattended sandbox Structure Catalog mapping")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--stop-at", default="08:00", help="Local wall-clock deadline HH:MM; default 08:00")
    parser.add_argument("--max-actions", type=int, default=100)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--max-rounds", type=int, default=1000000)
    args = parser.parse_args()

    source = args.project.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    stop_at = parse_stop_at(args.stop_at)
    summary: dict[str, Any] = {
        "source_project": str(source),
        "started_at": datetime.now().isoformat(),
        "stop_at": stop_at.isoformat(),
        "rounds": [],
    }
    write_json(output_root / "overnight_summary.json", summary)

    round_no = 0
    while datetime.now() < stop_at and round_no < args.max_rounds:
        round_no += 1
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        round_dir = output_root / f"round_{round_no:03d}_{stamp}"
        creation_dir = round_dir / "creation"
        round_record: dict[str, Any] = {
            "round": round_no,
            "started_at": datetime.now().isoformat(),
            "creation": None,
            "creation_verification": None,
            "existing_items": [],
            "errors": [],
        }
        summary["rounds"].append(round_record)
        write_json(output_root / "overnight_summary.json", summary)

        try:
            creation = StructureCatalogDeepMapper(
                source_project=source,
                output_dir=creation_dir,
                max_actions=args.max_actions,
                import_navigation=True,
                focus_creation=True,
                probe_input=True,
                commit_creation=True,
            ).run()
            round_record["creation"] = creation
            verification = verify_created_structure(creation_dir, source.name)
            round_record["creation_verification"] = verification
            write_json(round_dir / "creation_verification.json", verification)
        except Exception as exc:
            round_record["errors"].append({"stage": "creation", "error": repr(exc)})
            write_json(output_root / "overnight_summary.json", summary)
            time.sleep(max(args.pause_seconds, 1.0))
            continue

        committed_sandbox = creation_dir / "sandbox" / source.name
        try:
            references = catalog_references(committed_sandbox)
        except Exception as exc:
            references = []
            round_record["errors"].append({"stage": "catalog_references", "error": repr(exc)})

        for index, reference in enumerate(references, start=1):
            if datetime.now() >= stop_at:
                break
            safe = "".join(ch if ch.isalnum() else "_" for ch in reference).strip("_") or f"item_{index}"
            item_dir = round_dir / f"existing_{index:03d}_{safe[:60]}"
            try:
                result = StructureCatalogDeepMapper(
                    source_project=committed_sandbox,
                    output_dir=item_dir,
                    max_actions=args.max_actions,
                    import_navigation=True,
                    existing_item=reference,
                ).run()
                round_record["existing_items"].append({"reference": reference, "result": result})
            except Exception as exc:
                round_record["existing_items"].append({"reference": reference, "error": repr(exc)})
            write_json(output_root / "overnight_summary.json", summary)

        round_record["finished_at"] = datetime.now().isoformat()
        write_json(output_root / "overnight_summary.json", summary)
        if datetime.now() < stop_at:
            time.sleep(max(args.pause_seconds, 0.0))

    summary["finished_at"] = datetime.now().isoformat()
    summary["status"] = "deadline_reached" if datetime.now() >= stop_at else "max_rounds_reached"
    write_json(output_root / "overnight_summary.json", summary)
    print(json.dumps({
        "status": summary["status"],
        "rounds": len(summary["rounds"]),
        "output_root": str(output_root),
        "stop_at": stop_at.isoformat(),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
