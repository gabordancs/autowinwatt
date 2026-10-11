"""Create a complete, searchable index of every file below energetika."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zipfile
from pathlib import Path


TEXT_SUFFIXES = {".md", ".json", ".xml", ".csv", ".yml", ".yaml"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_size(path: Path) -> list[int] | None:
    data = path.read_bytes()[:24]
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return list(struct.unpack(">II", data[16:24]))
    return None


def build(source_root: Path, output_root: Path) -> dict[str, object]:
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError("pymupdf is required for complete PDF extraction") from exc

    output_root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    for path in sorted((p for p in source_root.rglob("*") if p.is_file()), key=lambda p: p.as_posix()):
        rel = path.relative_to(source_root).as_posix()
        item: dict[str, object] = {
            "relative_path": rel,
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
            "suffix": path.suffix.lower(),
        }
        if path.suffix.lower() == ".pdf":
            target = output_root / (hashlib.sha256(rel.encode()).hexdigest()[:16] + ".pages.jsonl")
            doc = pymupdf.open(path)
            with target.open("w", encoding="utf-8") as stream:
                for number, page in enumerate(doc, 1):
                    stream.write(json.dumps({"page": number, "text": page.get_text()}, ensure_ascii=False) + "\n")
            item.update(page_count=len(doc), text_extract=target.name)
        elif path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            item.update(line_count=len(text.splitlines()), character_count=len(text), searchable_source=True)
        elif path.suffix.lower() == ".xlsx":
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                item.update(zip_member_count=len(names), embedded_media=[n for n in names if n.startswith("xl/media/")])
        elif path.suffix.lower() == ".png":
            item["pixel_size"] = png_size(path)
            item["visual_source"] = True
        else:
            item["binary_source"] = True
        entries.append(item)

    payload = {
        "schema_version": 1,
        "source_root": "energetika",
        "file_count": len(entries),
        "total_size_bytes": sum(int(e["size_bytes"]) for e in entries),
        "entries": entries,
    }
    payload["corpus_id"] = "certification_corpus_" + hashlib.sha256(
        json.dumps(entries, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    (output_root / "index.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.source_root.resolve(), args.output_root.resolve())
    print(json.dumps({"corpus_id": result["corpus_id"], "files": result["file_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
