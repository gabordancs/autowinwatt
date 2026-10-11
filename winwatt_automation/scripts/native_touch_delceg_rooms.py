"""Re-save imported Délceg rooms through native editors without replacing boundaries."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from winwatt_automation.domain.room import RoomInput
from winwatt_automation.version_profile import require_profile, sha256


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", required=True, type=Path)
    p.add_argument("--source", required=True, type=Path)
    p.add_argument("--payload", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    profile = require_profile(a.profile)
    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    source = a.source.resolve(strict=True)
    payload = json.loads(a.payload.read_text(encoding="utf-8"))
    output = a.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    project = output / "delceg_native_touched_envelope.wwp"
    shutil.copy2(source, project)
    from winwatt_automation.runtime_mapping.room_deep_explorer import _activate_rooms_catalog_fast, open_sandbox_buildings
    from winwatt_automation.live_ui.app_connector import get_main_window
    from winwatt_automation.services.room_service import RoomService
    from winwatt_automation.services.winwatt_service import WinWattService

    report = {"schema_version": 1, "source": str(source), "source_sha256": sha256(source),
              "project": str(project), "rooms_requested": len(payload["rooms"]), "rooms_touched": [],
              "status": "running"}
    try:
        open_sandbox_buildings(project_path=str(project))
        _activate_rooms_catalog_fast(get_main_window())
        service = RoomService()
        for spec in payload["rooms"]:
            room = RoomInput(**spec)
            service._apply_proven_fields(room, project)
            report["rooms_touched"].append(room.name)
        service._ensure_saveable_main_window()
        WinWattService().save_project()
        report["saved_sha256"] = sha256(project)
        WinWattService().close_project_gracefully()
        open_sandbox_buildings(project_path=str(project))
        report["reopened"] = True
        WinWattService().close_project_gracefully()
        report["source_unchanged"] = sha256(source) == report["source_sha256"]
        report["copy_changed"] = report["saved_sha256"] != report["source_sha256"]
        report["status"] = "passed" if len(report["rooms_touched"]) == len(payload["rooms"]) and report["source_unchanged"] and report["copy_changed"] else "failed"
    except Exception as exc:
        report["status"] = "failed"; report["error"] = repr(exc)
        try: WinWattService().close_project_gracefully()
        except Exception: pass
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
