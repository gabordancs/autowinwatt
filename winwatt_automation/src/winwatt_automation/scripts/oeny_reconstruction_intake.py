"""Build restartable local OENY reconstruction intake jobs."""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from winwatt_automation.certificates.oeny_reconstruction import write_reconstruction_intake


def _run_one(xml_path: str, output: str) -> dict[str, Any]:
    result = write_reconstruction_intake(Path(xml_path), Path(output))
    return {
        "certificate_id": result.certificate_id,
        "output_dir": str(result.output_dir),
        "status": result.status,
        "cache_hit": result.cache_hit,
        "complexity_score": result.complexity_score,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--xml", type=Path, help="One OENY UploadRequest XML")
    source.add_argument("--input-dir", type=Path, help="Directory of numeric-name OENY XML files")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--id", action="append", dest="ids")
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")

    if args.xml:
        paths = [args.xml.resolve(strict=True)]
    else:
        directory = args.input_dir.resolve(strict=True)
        paths = sorted(
            (path for path in directory.glob("*.xml") if path.stem.isdigit()),
            reverse=True,
        )
    if args.ids:
        requested = set(args.ids)
        invalid = sorted(value for value in requested if not value.isdigit() or len(value) != 8)
        if invalid:
            parser.error(f"invalid certificate id(s): {', '.join(invalid)}")
        paths = [path for path in paths if path.stem in requested]
    if args.limit is not None:
        paths = paths[: max(0, args.limit)]
    if not paths:
        parser.error("no matching OENY XML files")

    args.output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    with ProcessPoolExecutor(max_workers=min(args.workers, len(paths))) as executor:
        jobs = {executor.submit(_run_one, str(path), str(args.output)): path for path in paths}
        for future in as_completed(jobs):
            path = jobs[future]
            try:
                row = future.result()
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
            except Exception as exc:
                error = {"certificate_id": path.stem, "error": repr(exc)}
                errors.append(error)
                print(json.dumps(error, ensure_ascii=False), flush=True)

    report = {
        "schema": "autowinwatt-oeny-reconstruction-batch/v1",
        "source_count": len(paths),
        "completed": len(rows),
        "errors": errors,
        "workers": min(args.workers, len(paths)),
        "results": sorted(rows, key=lambda item: item["certificate_id"], reverse=True),
        "llm_used": False,
        "winwatt_started": False,
    }
    report_path = args.output / "batch_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"batch_report": str(report_path), "completed": len(rows), "errors": len(errors)}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
