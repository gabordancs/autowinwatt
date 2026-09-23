import pytest

from winwatt_automation.certificates.geometry import wall_geometry_issues, xy_area


def test_plan_wall_geometry_requires_a_product_of_length_and_height():
    wall = {"name": "R5 upper", "winwatt_type": "külső fal", "x_m": 1.92, "y_m": 2.84, "area_m2": 5.45}
    assert xy_area(wall) == (1.92, 2.84, 5.45)
    assert wall_geometry_issues({"boundaries": [wall]}) == []


def test_vertical_wall_without_xy_is_reported():
    wall = {"name": "legacy R5", "winwatt_type": "külső fal", "area_m2": 8}
    assert wall_geometry_issues({"boundaries": [wall]}) == ["legacy R5: missing X length and Y height"]


def test_invalid_xy_product_is_rejected():
    with pytest.raises(ValueError, match="A must equal X\\*Y"):
        xy_area({"name": "bad wall", "winwatt_type": "külső fal", "x_m": 2, "y_m": 3, "area_m2": 5})
