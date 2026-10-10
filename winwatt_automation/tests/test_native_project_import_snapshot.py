from winwatt_automation.scripts.probe_native_project_import_roundtrip import semantic_zone_snapshot


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
