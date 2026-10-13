"""Export one WinWatt project to native XML without modifying the source."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
from pathlib import Path

from winwatt_automation.services.winwatt_service import WinWattService
from winwatt_automation.services.xml_native_service import NativeXmlService
from winwatt_automation.version_profile import require_profile


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if struct.calcsize("P") * 8 != 32:
        parser.error("requires 32-bit Python")

    profile = require_profile(args.profile.resolve(strict=True))
    os.environ["WWA_WINWATT_EXE_PATH"] = profile["exe_path"]
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    before = digest(source)
    target = output / "native_export.xml"
    report = {
        "schema_version": 1,
        "profile_id": profile["profile_id"],
        "source": str(source),
        "source_sha256": before,
        "output": str(target),
        "status": "failed",
        "llm_used": False,
    }
    winwatt = WinWattService()
    try:
        winwatt.open_project(source)
        evidence = NativeXmlService().export_xml(target)
        report["export_evidence"] = evidence.model_dump(mode="json")
    except Exception as exc:
        report["error"] = repr(exc)
    finally:
        try:
            winwatt.close_project_gracefully()
        except Exception:
            pass
    report["source_unchanged"] = digest(source) == before
    report["status"] = "passed" if target.exists() and report["source_unchanged"] else "failed"
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
