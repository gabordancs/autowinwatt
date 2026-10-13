"""Build a one-zone OENY reconstruction candidate from explicit decisions."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from winwatt_automation.certificates.oeny_reconstruction import build_one_zone_candidate


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--decisions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    spec_path = args.spec.resolve(strict=True)
    decisions_path = args.decisions.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"output must be new: {output}")
    output.mkdir(parents=True)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    model = build_one_zone_candidate(spec, decisions)
    model_path = output / "model.reviewed_candidate.json"
    model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "status": "review_required",
        "certificate_id": spec["certificate_id"],
        "spec": str(spec_path),
        "spec_sha256": _sha256(spec_path),
        "decisions": str(decisions_path),
        "decisions_sha256": _sha256(decisions_path),
        "model": str(model_path),
        "model_sha256": _sha256(model_path),
        "room_count": len(model["rooms"]),
        "boundary_count": len(model["boundaries"]),
        "layer_count": len(model["layers"]),
        "system_count": len(model["systems"]),
        "llm_used": False,
        "winwatt_started": False,
    }
    (output / "candidate_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
