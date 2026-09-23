"""One geometry contract shared by PDF extraction, XML compilation and QA."""
from __future__ import annotations

import math
from typing import Any


VERTICAL_TYPES = {"külső fal", "lábazati fal"}


def is_vertical_wall(boundary: dict[str, Any]) -> bool:
    # Windows and doors may also be vertical but use their own product
    # geometry. This contract governs opaque exterior and basement walls.
    return boundary.get("winwatt_type") in VERTICAL_TYPES


def xy_area(boundary: dict[str, Any]) -> tuple[float, float, float] | None:
    """Return X length, Y height and A, or None when a wall is unresolved."""
    if "x_m" not in boundary and "y_m" not in boundary:
        return None
    if "x_m" not in boundary or "y_m" not in boundary:
        raise ValueError(f"Boundary {boundary.get('name')!r}: X and Y must be supplied together")
    x, y, area = float(boundary["x_m"]), float(boundary["y_m"]), float(boundary["area_m2"])
    if x <= 0 or y <= 0 or not math.isclose(x * y, area, abs_tol=.011):
        raise ValueError(f"Boundary {boundary.get('name')!r}: A must equal X*Y")
    return x, y, area


def wall_geometry_issues(model: dict[str, Any]) -> list[str]:
    """Report every unresolved or inconsistent vertical-wall record."""
    issues = []
    for boundary in model.get("boundaries", []):
        if not is_vertical_wall(boundary):
            continue
        try:
            if xy_area(boundary) is None:
                issues.append(f"{boundary.get('name')}: missing X length and Y height")
        except ValueError as exc:
            issues.append(str(exc))
    return issues
