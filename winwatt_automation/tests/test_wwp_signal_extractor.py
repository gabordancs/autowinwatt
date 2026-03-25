from __future__ import annotations

import json
from pathlib import Path

from winwatt_automation.wwp.wwp_signal_extractor import (
    compare_with_ui_labels,
    extract_wwp_signals,
    load_ui_labels_from_snapshot,
)


def test_extract_wwp_signals_mixed_encodings(tmp_path: Path) -> None:
    utf16 = "Nappali 1".encode("utf-16le")
    payload = b"\x00\x01Kaz\xe1n panel\x00" + utf16 + b"\x00Ablak\x00\xff"
    sample = tmp_path / "sample.wwp"
    sample.write_bytes(payload)

    result = extract_wwp_signals(sample)

    texts = {hit.text for hit in result.raw_hits}
    assert any("Kaz" in text for text in texts)
    assert any("Nappali 1" in text for text in texts)
    assert any(entity.kind in {"room", "system", "opening", "label_group"} for entity in result.entities)


def test_compare_with_ui_labels_and_snapshot_loader(tmp_path: Path) -> None:
    sample = tmp_path / "sample.wwp"
    sample.write_bytes(b"Nappali\x00Kaz\xe1n\x00Ablak\x00")

    result = extract_wwp_signals(sample)

    snapshot = tmp_path / "ui_snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "nodes": [
                    {"label": "Nappali"},
                    {"text": "Kazán"},
                    {"caption": "NemTalalt"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    labels = load_ui_labels_from_snapshot(snapshot)
    diff = compare_with_ui_labels(result, labels)

    assert "Nappali" in labels
    assert diff["matched_count"] >= 1
    assert "NemTalalt" in diff["only_in_ui"]
