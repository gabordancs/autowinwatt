from __future__ import annotations

from pathlib import Path

from winwatt_automation.exe.exe_signal_extractor import (
    compare_exe_with_ui,
    compare_exe_with_wwp,
    extract_exe_strings,
    load_json,
)
from winwatt_automation.wwp.wwp_signal_extractor import load_ui_labels_from_snapshot


def enrich_with_exe_signals(
    exe_path: str,
    wwp_json_path: str | None = None,
    ui_snapshot_path: str | None = None,
) -> dict:
    exe_strings = extract_exe_strings(exe_path)

    wwp_diff = {"wwp_only": [], "common": [], "exe_only": []}
    if wwp_json_path:
        wwp_data = load_json(Path(wwp_json_path))
        wwp_diff = compare_exe_with_wwp(exe_strings, wwp_data)

    ui_diff = {"confirmed_labels": [], "hidden_exe_strings": [], "ui_only": []}
    if ui_snapshot_path:
        labels = load_ui_labels_from_snapshot(Path(ui_snapshot_path))
        ui_diff = compare_exe_with_ui(exe_strings, labels)

    return {
        "confirmed_labels": ui_diff.get("confirmed_labels", []),
        "hidden_candidates": sorted(
            set(ui_diff.get("hidden_exe_strings", [])) | set(wwp_diff.get("exe_only", [])),
            key=str.casefold,
        ),
        "wwp_only": sorted(set(wwp_diff.get("wwp_only", [])), key=str.casefold),
        "ui_only": sorted(set(ui_diff.get("ui_only", [])), key=str.casefold),
    }


__all__ = ["enrich_with_exe_signals"]
