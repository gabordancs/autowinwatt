"""CLI wrapper for weak EXE/DLL signal extraction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from winwatt_automation.exe.exe_signal_extractor import (
    ASCII_MIN_LEN,
    UTF16_MIN_LEN,
    cluster_exe_strings,
    collect_top_tokens,
    compare_exe_with_ui,
    compare_exe_with_wwp,
    extract_exe_strings,
    infer_exe_entities,
    load_json,
    result_to_json,
)
from winwatt_automation.wwp.wwp_signal_extractor import load_ui_labels_from_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="WinWatt EXE/DLL weak signal extractor")
    parser.add_argument("exe_path", help="Input EXE/DLL file path")
    parser.add_argument("--json-out", help="Output JSON path")
    parser.add_argument("--wwp-json", help="Optional extract_wwp_signals JSON")
    parser.add_argument("--ui-snapshot", help="Optional UI snapshot JSON")
    parser.add_argument("--ascii-min-len", type=int, default=ASCII_MIN_LEN)
    parser.add_argument("--utf16-min-len", type=int, default=UTF16_MIN_LEN)
    parser.add_argument("--no-utf16", action="store_true", help="Disable UTF-16LE scan")
    args = parser.parse_args()

    strings = extract_exe_strings(
        args.exe_path,
        min_len=args.ascii_min_len,
        utf16_scan=not args.no_utf16,
        utf16_min_len=args.utf16_min_len,
    )
    clusters = cluster_exe_strings(strings)
    entities = infer_exe_entities(strings)
    tokens = collect_top_tokens(strings)

    comparisons: dict[str, dict] = {}

    if args.wwp_json:
        comparisons["wwp"] = compare_exe_with_wwp(strings, load_json(args.wwp_json))

    if args.ui_snapshot:
        labels = load_ui_labels_from_snapshot(args.ui_snapshot)
        comparisons["ui"] = compare_exe_with_ui(strings, labels)

    print(f"Fájl: {args.exe_path}")
    print(f"Total strings: {len(strings)}")
    print(f"Filtered strings: {len(strings)}")
    print(f"Clusters: {len(clusters)}")
    print(f"Inferred entities: {len(entities)}")

    print("\nTop frequent tokens:")
    for token, count in tokens[:15]:
        print(f"  {count:>3}x {token}")

    print("\nInferred entity groups:")
    for entity in entities[:15]:
        print(f"  [{entity.kind:<13}] conf={entity.confidence:.2f} anchor={entity.anchor_text!r}")

    if comparisons:
        print("\nComparisons:")
        print(json.dumps(comparisons, ensure_ascii=False, indent=2))

    if args.json_out:
        out_payload = result_to_json(
            strings=strings,
            clusters=clusters,
            entities=entities,
            comparisons=comparisons,
        )
        output_path = Path(args.json_out)
        output_path.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON mentve: {output_path}")


if __name__ == "__main__":
    main()
