"""Write local architectural dimension-chain evidence to JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from winwatt_automation.certificates.dimension_chains import extract_pdf_dimension_chains


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    evidence = extract_pdf_dimension_chains(args.pdf)
    payload = {"source_pdf": str(args.pdf), "dimension_chains": [item.json() for item in evidence]}
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(evidence)} dimension chains to {args.output}")


if __name__ == "__main__":
    main()
