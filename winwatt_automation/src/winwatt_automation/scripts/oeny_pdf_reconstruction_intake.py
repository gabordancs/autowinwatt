"""Create a strict PDF-only WinWatt reconstruction specification."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from winwatt_automation.certificates.oeny_reconstruction import (
    build_pdf_reconstruction_spec,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--certificate-id")
    args = parser.parse_args()

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    spec = build_pdf_reconstruction_spec(
        args.pdf, certificate_id=args.certificate_id
    )
    output.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
