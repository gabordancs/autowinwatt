"""CLI wrapper for heuristic signal extraction from WinWatt .wwp files."""

from __future__ import annotations

import argparse
import json

from winwatt_automation.wwp.wwp_signal_extractor import (
    ASCII_MIN_LEN,
    UTF16_MIN_LEN,
    compare_with_ui_labels,
    extract_wwp_signals,
    load_ui_labels_from_snapshot,
    print_console_summary,
    save_result_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="WinWatt WWP heuristic signal extractor")
    parser.add_argument("wwp_file", help="Input .wwp file")
    parser.add_argument("--json-out", help="Output JSON path")
    parser.add_argument("--ui-snapshot", help="Optional UI snapshot JSON for comparison")
    parser.add_argument("--ascii-min-len", type=int, default=ASCII_MIN_LEN)
    parser.add_argument("--utf16-min-len", type=int, default=UTF16_MIN_LEN)
    parser.add_argument("--cluster-gap", type=int, default=192)
    args = parser.parse_args()

    result = extract_wwp_signals(
        args.wwp_file,
        ascii_min_len=args.ascii_min_len,
        utf16_min_len=args.utf16_min_len,
        cluster_gap=args.cluster_gap,
    )

    print_console_summary(result)

    if args.json_out:
        save_result_json(result, args.json_out)
        print()
        print(f"JSON mentve ide: {args.json_out}")

    if args.ui_snapshot:
        ui_labels = load_ui_labels_from_snapshot(args.ui_snapshot)
        diff = compare_with_ui_labels(result, ui_labels)
        print()
        print("UI összevetés:")
        print(json.dumps(diff, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
