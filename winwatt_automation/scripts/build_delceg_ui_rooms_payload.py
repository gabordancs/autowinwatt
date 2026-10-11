"""Build the 29-room Délceg payload with WinWatt-safe native names."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    model = json.loads(a.model.read_text(encoding="utf-8"))
    rooms = []
    used: set[str] = set()
    for source in model["rooms"]:
        name = source["name"][:30].rstrip()
        if name.casefold() in used:
            raise ValueError(f"Truncated room name is not unique: {name!r}")
        used.add(name.casefold())
        rooms.append({
            "name": name,
            "area_m2": source["area_m2"],
            "height_m": source["height_m"],
            "temperature_c": source.get("temperature_c", 20),
        })
    payload = {"rooms": rooms, "expected_area_m2": round(sum(float(x["area_m2"]) for x in rooms), 2)}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rooms": len(rooms), "area_m2": payload["expected_area_m2"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
