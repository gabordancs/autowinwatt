"""Audit whether every R5 boundary is a real plan wall segment.

This is deliberately a stop-the-line check: one aggregated R5 record does
not prove that a room has one exterior wall. The output distinguishes known
separate segments from rooms that need contour-to-dimension-chain matching.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


# Visual review seeds from E02 / E02B. They are *not* auto-import authority;
# the subsequent contour matcher must attach each to dimension-chain evidence.
VISUAL_MULTI_WALL_CANDIDATES = {
    "B03 - Nappali": "földszinti külső kontúr: alsó és bal oldali falszakasz",
    "B04 - Konyha": "földszinti külső kontúr: alsó és jobb oldali falszakasz",
    "B08 - Pihenő / télikert": "földszinti külső kontúr: felső és bal oldali falszakasz",
    "B13 - Tetőtéri szoba 2": "tetőtéri külső kontúr: felső és jobb oldali falszakasz",
    "B16 - Tetőtéri szoba 5": "tetőtéri külső kontúr: alsó és bal oldali falszakasz",
}


def audit(model: dict) -> dict:
    r5_by_room: dict[str, list[dict]] = defaultdict(list)
    for boundary in model.get("boundaries", []):
        if boundary.get("structure") == "B R5 új külső fal - tervrétegrend":
            r5_by_room[boundary["room"]].append(boundary)
    records = []
    for room in model.get("rooms", []):
        name = room["name"]
        if not name.startswith("B"):
            continue
        boundaries = r5_by_room[name]
        if name == "B10a - Földszinti gardrób":
            status = "separate_segments_present"
            reason = "Két külön tervi méretláncból felvett R5 falszakasz."
        elif name in VISUAL_MULTI_WALL_CANDIDATES:
            status = "multiple_wall_candidate_requires_measurement"
            reason = VISUAL_MULTI_WALL_CANDIDATES[name]
        elif len(boundaries) == 1:
            status = "single_aggregate_requires_contour_check"
            reason = "Egy R5 rekord nem igazolja, hogy csak egy külső falszakasz van."
        elif not boundaries:
            status = "no_r5_boundary"
            reason = "A helyiséghez jelenleg nincs R5; csak tervi kontúrillesztés után dönthető el, kell-e."
        else:
            status = "multiple_segments_review_required"
            reason = "Több R5 falszakasz van, de a méretlánc-bizonyítékot még csatolni kell."
        records.append({
            "room": name,
            "r5_count": len(boundaries),
            "r5_segments": [{"name": item["name"], "area_m2": item["area_m2"], "azimuth_deg": item["azimuth_deg"]} for item in boundaries],
            "status": status,
            "reason": reason,
            "winwatt_xy_ready": all("x_m" in item and "y_m" in item for item in boundaries),
        })
    return {
        "rule": "R5 only becomes importable when a room-contour edge, a dimension chain and an exterior contour edge agree.",
        "counts": {
            "rooms": len(records),
            "single_r5": sum(item["r5_count"] == 1 for item in records),
            "separate_r5": sum(item["r5_count"] >= 2 for item in records),
            "multi_wall_candidates": sum(item["status"] == "multiple_wall_candidate_requires_measurement" for item in records),
        },
        "rooms": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = audit(json.loads(args.model.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
