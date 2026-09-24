"""Reusable wall-candidate overlay data and render-ready labels.

Coordinates are normalized to the source raster/canvas reference. The renderer
scales them to the actual PDF image, so zooming and scrolling never detach a
label from its source plan.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WallOverlayLabel:
    x_ratio: float
    y_ratio: float
    lines: tuple[str, ...]
    room_code: str


def _boundary_code(boundary: dict[str, Any]) -> str:
    name=str(boundary.get("structure") or "")
    for code in ("R1B","R14","R15","R16","R7","R6","R5"):
        if f" {code} " in f" {name} ": return code
    return "A"


def _room_lines(room_code: str, model: dict[str, Any]) -> tuple[str, ...]:
    room=next((item for item in model.get("rooms",[]) if str(item.get("name","")).split(" - ",1)[0]==room_code),None)
    if room is None: return (f"{room_code} | NINCS MODELLADAT",)
    boundaries=[item for item in model.get("boundaries",[]) if item.get("room")==room.get("name")]
    priority={"R14":0,"R6":0,"R1B":1,"R7":1,"R5":2,"R15":2,"R16":2}
    boundaries.sort(key=lambda item:(priority.get(_boundary_code(item),9),_boundary_code(item)))
    lines=[f"{room_code} | A={float(room.get('area_m2',0)):.2f} m² | h={float(room.get('height_m',0)):.2f} m"]
    for boundary in boundaries:
        code=_boundary_code(boundary)
        if boundary.get("slope")=="függőleges" and "x_m" not in boundary:
            lines.append(f"{code}: X×Y=ELLENŐRZENDŐ")
        else:
            x=float(boundary.get("x_m",boundary.get("area_m2",0))); y=float(boundary.get("y_m",1)); lines.append(f"{code}: X×Y={x:.2f}×{y:.2f}")
    return tuple(lines)


class WallOverlay:
    def __init__(self, payload: dict[str, Any], source: Path):
        self.payload=payload; self.source=source
        model_path=Path(str(payload["model_path"])); self.model_path=(source.parent/model_path).resolve() if not model_path.is_absolute() else model_path
        self.model=json.loads(self.model_path.read_text(encoding="utf-8"))

    @classmethod
    def load(cls, path: Path) -> "WallOverlay": return cls(json.loads(path.read_text(encoding="utf-8")),path)

    def labels_for_pdf(self, filename: str) -> list[WallOverlayLabel]:
        normalized=filename.replace("É","E").replace("-","").replace(" ","").casefold()
        for item in self.payload.get("plans",[]):
            if str(item["match"]).replace("-","").casefold() not in normalized: continue
            canvas=item["canvas"]; width=float(canvas["width"]); height=float(canvas["height"])
            return [WallOverlayLabel(float(entry["x"])/width,float(entry["y"])/height,_room_lines(str(entry["room"]),self.model),str(entry["room"])) for entry in item.get("labels",[])]
        return []
