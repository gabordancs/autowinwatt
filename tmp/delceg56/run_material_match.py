from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from winwatt_automation.certificates.materials import load_catalog, match_material


ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "data/delceg56/delceg56_winwatt_model.json"
CATALOG_DIR = ROOT / "data/delceg56/material_catalogs"
OUTPUT = ROOT / "data/delceg56/layer_audit_catalog_matched.json"


def main() -> None:
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    candidates = []
    origins: dict[tuple, list[str]] = {}
    for path in sorted(CATALOG_DIR.glob("*.xml")):
        for candidate in load_catalog(path):
            key = (candidate.name, candidate.material_id, candidate.path, candidate.lambda_wmk,
                   candidate.density_kgm3, candidate.heat_capacity_kjkgk)
            origins.setdefault(key, []).append(path.name)
            candidates.append(candidate)
    rows = []
    for layer in model["layers"]:
        decision = match_material(
            layer["name"], candidates,
            lambda_wmk=layer.get("lambda_wmk"),
            density_kgm3=layer.get("density_kgm3"),
            heat_capacity_kjkgk=layer.get("heat_capacity_kjkgk"),
            family=layer.get("type"),
        )
        data = decision.model_dump(mode="json")
        key = None
        if decision.candidate:
            c = decision.candidate
            key = (c.name, c.material_id, c.path, c.lambda_wmk, c.density_kgm3, c.heat_capacity_kjkgk)
        rows.append({
            "structure": layer["structure"], "sequence": layer["sequence"],
            "source_name": layer["name"], "thickness_cm": layer["thickness_cm"],
            "decision": data, "catalog_files": origins.get(key, []) if key else [],
        })
    payload = {
        "model": str(MODEL), "catalog_directory": str(CATALOG_DIR),
        "catalog_file_count": len(list(CATALOG_DIR.glob("*.xml"))),
        "catalog_material_records": len(candidates),
        "summary": dict(Counter(row["decision"]["status"] for row in rows)),
        "layers": rows,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("catalog_file_count", "catalog_material_records", "summary")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
