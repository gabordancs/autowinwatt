from __future__ import annotations

from pathlib import Path

from winwatt_automation.exe.exe_signal_extractor import (
    cluster_exe_strings,
    compare_exe_with_ui,
    compare_exe_with_wwp,
    extract_exe_strings,
)


def test_extract_exe_strings_from_dummy_binary(tmp_path: Path) -> None:
    payload = b"\x00\x01RoomName\x00PanelHeight\x00" + "Nappali 1".encode("utf-16le") + b"\x00\x00"
    sample = tmp_path / "dummy.exe"
    sample.write_bytes(payload)

    strings = extract_exe_strings(str(sample), min_len=4, utf16_scan=True)

    joined = " | ".join(strings)
    assert "RoomName" in joined
    assert "PanelHeight" in joined
    assert "Nappali 1" in joined


def test_noise_filtering_drops_repeating_and_hex(tmp_path: Path) -> None:
    payload = b"AAAAAA\x00FFFFFFFFFFFF\x00ValidFieldName\x00"
    sample = tmp_path / "noise.dll"
    sample.write_bytes(payload)

    strings = extract_exe_strings(str(sample), min_len=4, utf16_scan=False)

    assert "ValidFieldName" in strings
    assert not any(value == "AAAAAA" for value in strings)
    assert not any(value == "FFFFFFFFFFFF" for value in strings)


def test_cluster_grouping_groups_related_prefixes() -> None:
    values = ["room_name", "room_temp", "room_type", "panel_height", "panel_width"]

    clusters = cluster_exe_strings(values)

    keys = {cluster.key for cluster in clusters}
    assert any(key.startswith("room") for key in keys)
    assert any(key.startswith("panel") for key in keys)


def test_compare_exe_with_wwp_handles_regular_wwp_json_shape() -> None:
    exe_strings = ["Nappali 1", "Kazán", "RejtettOpcio"]
    wwp_result = {
        "raw_hits": [
            {"text": "Nappali"},
            {"text": "Kazán"},
            {"text": "Ablak"},
        ]
    }

    diff = compare_exe_with_wwp(exe_strings, wwp_result)

    assert "Kazán" in diff["common"]
    assert "RejtettOpcio" in diff["exe_only"]
    assert "Ablak" in diff["wwp_only"]


def test_compare_exe_with_ui_snapshot_labels() -> None:
    exe_strings = ["Nappali 1", "Kazán panel", "Hidden Feature"]
    ui_labels = ["Nappali", "Kazán panel", "Látható címke"]

    diff = compare_exe_with_ui(exe_strings, ui_labels)

    confirmed_ui = {row["ui"] for row in diff["confirmed_labels"]}
    assert "Nappali" in confirmed_ui
    assert "Kazán panel" in confirmed_ui
    assert "Hidden Feature" in diff["hidden_exe_strings"]
    assert "Látható címke" in diff["ui_only"]
