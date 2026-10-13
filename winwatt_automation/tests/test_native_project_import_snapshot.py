from winwatt_automation.scripts.probe_native_project_import_roundtrip import (
    semantic_zone_snapshot,
    zone_references_resolved,
)


def test_semantic_zone_snapshot_ignores_import_ids() -> None:
    before = {
        "zone": "A.0.02", "room_ids": ["176"],
        "rooms": [{"id": "176", "name": "A.0.02.01", "area": "4.13", "boundaries": []}],
    }
    after = {
        "zone": "A.0.02", "room_ids": ["10"],
        "rooms": [{"id": "10", "name": "A.0.02.01", "area": "4.13", "boundaries": []}],
    }
    assert semantic_zone_snapshot(before) == semantic_zone_snapshot(after)


def test_zone_resolution_rejects_an_empty_readback() -> None:
    expected = {"room_ids": ["8"], "rooms": [{"id": "8"}]}
    assert not zone_references_resolved(expected, {"room_ids": [], "rooms": []})
    assert zone_references_resolved(expected, {"room_ids": ["4"], "rooms": [{"id": "4"}]})
