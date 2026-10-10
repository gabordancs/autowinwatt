"""Remove empty native PhotoAlbumItem placeholders before WinWatt import."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--all", action="store_true", help="Remove every PhotoAlbumItem before an importer that clears filenames")
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    if args.output.exists() or args.report.exists():
        parser.error("output and report must be new")
    tree = ET.parse(source)
    removed = 0
    for parent in tree.getroot().iter():
        for child in list(parent):
            if local(child.tag) == "PhotoAlbumItem" and (args.all or not child.attrib.get("FileName", "").strip()):
                parent.remove(child); removed += 1
    if not removed:
        raise ValueError("No matching PhotoAlbumItem records found")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="  ")
    tree.write(args.output, encoding="utf-8", xml_declaration=True)
    result = {
        "source": str(source), "output": str(args.output.resolve()),
        "removed_photo_items": removed, "all_items_requested": args.all,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
