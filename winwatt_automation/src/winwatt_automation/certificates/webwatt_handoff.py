"""Strict consumer for human-approved WebWatt layer handoff packages."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .materials import load_catalog


class HandoffEvidence(BaseModel):
    source_file: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    page: int | None = Field(default=None, ge=1)
    bbox: list[float] | None = None

    @model_validator(mode="after")
    def valid_bbox(self):
        if self.bbox is not None:
            if len(self.bbox) != 4 or any(value < 0 or value > 1 for value in self.bbox):
                raise ValueError("bbox must contain four normalized coordinates")
            if self.bbox[0] > self.bbox[2] or self.bbox[1] > self.bbox[3]:
                raise ValueError("bbox coordinates are not ordered")
        return self


class HandoffReview(BaseModel):
    status: Literal["accepted", "edited"]
    reviewer_id: str = Field(min_length=1)
    reviewed_at: str = Field(min_length=1)


class ApprovedLayer(BaseModel):
    candidate_id: str
    layer_reference: str
    structure_name: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    catalog_material_id: str = Field(min_length=1)
    catalog_material_name: str = Field(min_length=1)
    catalog_material_path: str | None = None
    thickness_mm: float = Field(gt=0)
    thermal_conductivity: float | None = Field(default=None, gt=0)
    density: float | None = Field(default=None, gt=0)
    heat_capacity: float | None = Field(default=None, gt=0)
    review: HandoffReview
    evidence: HandoffEvidence


class WebwattWinwattHandoff(BaseModel):
    schema_version: Literal["webwatt-winwatt-handoff/v1"]
    project_id: str = Field(min_length=1)
    generated_at: str = Field(min_length=1)
    ready: Literal[True]
    layers: list[ApprovedLayer] = Field(min_length=1)
    blockers: list[Any] = Field(max_length=0)


def load_webwatt_handoff(path: Path, catalog_path: Path) -> tuple[WebwattWinwattHandoff, dict[str, Any]]:
    package = WebwattWinwattHandoff.model_validate_json(path.read_text(encoding="utf-8"))
    catalog = {item.material_id: item for item in load_catalog(catalog_path) if item.material_id}
    errors: list[str] = []
    for layer in package.layers:
        material = catalog.get(layer.catalog_material_id)
        if material is None:
            errors.append(f"{layer.candidate_id}: unknown catalog material {layer.catalog_material_id}")
        elif material.name != layer.catalog_material_name:
            errors.append(f"{layer.candidate_id}: catalog name mismatch")
    if errors:
        raise ValueError("Invalid reviewed catalog references:\n" + "\n".join(errors))
    model_fragment = {
        "project": {"id": package.project_id, "source": str(path)},
        "structures": [{"name": name, "type": "külső fal"} for name in sorted({layer.structure_name for layer in package.layers})],
        "layers": [{
            "structure": layer.structure_name,
            "sequence": layer.sequence,
            "name": layer.catalog_material_name,
            "catalog_material_id": layer.catalog_material_id,
            "thickness_cm": layer.thickness_mm / 10.0,
            "lambda_wmk": layer.thermal_conductivity,
            "density_kgm3": layer.density,
            "heat_capacity_kjkgk": layer.heat_capacity,
            "review": layer.review.model_dump(mode="json"),
            "evidence": layer.evidence.model_dump(mode="json"),
        } for layer in sorted(package.layers, key=lambda item: (item.structure_name, item.sequence))],
    }
    return package, model_fragment


def write_reviewed_model_fragment(handoff_path: Path, catalog_path: Path, target: Path) -> dict[str, Any]:
    package, fragment = load_webwatt_handoff(handoff_path, catalog_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(fragment, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"schema_version": package.schema_version, "project_id": package.project_id, "layer_count": len(package.layers), "target": str(target)}
