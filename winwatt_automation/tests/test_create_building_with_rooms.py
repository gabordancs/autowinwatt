from dataclasses import dataclass

from winwatt_automation.scripts.create_building_with_rooms import _wall_x_edit


@dataclass
class Rect:
    left: int
    top: int
    right: int
    bottom: int


class Edit:
    def __init__(self, rect: Rect):
        self._rect = rect

    def class_name(self):
        return "TEdit"

    def rectangle(self):
        return self._rect


class Detail:
    def __init__(self, bounds: Rect, edits: list[Edit]):
        self._bounds = bounds
        self._edits = edits

    def rectangle(self):
        return self._bounds

    def descendants(self, control_type=None):
        assert control_type == "Edit"
        return self._edits


def test_wall_x_edit_uses_dialog_relative_coordinates():
    expected = Edit(Rect(1011, 486, 1080, 507))
    detail = Detail(
        Rect(974, 450, 1300, 800),
        [Edit(Rect(1120, 486, 1180, 507)), expected, Edit(Rect(1120, 650, 1180, 671))],
    )

    assert _wall_x_edit(detail) is expected
