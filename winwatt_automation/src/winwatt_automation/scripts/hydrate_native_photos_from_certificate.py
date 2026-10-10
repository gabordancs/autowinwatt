"""Restore required native photo paths from an existing certificate XML."""
from __future__ import annotations

import argparse
import base64
import json
import xml.etree.ElementTree as ET
from pathlib import Path


CATEGORY_MAP = {
    "0": "CoverPhoto",
    "1": "Facade",
    "2": "CharacteristicHeatExchanger",
    "3": "CharacteristicOpeningStructure",
    "4": "HeatGeneratorAndHeatStorageSituation",
}


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_text(element: ET.Element, name: str) -> str | None:
    return next(((child.text or "").strip() for child in element if local(child.tag) == name), None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-xml", required=True, type=Path)
    parser.add_argument("--certificate-xml", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    native = args.native_xml.resolve(strict=True)
    certificate = args.certificate_xml.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        parser.error(f"output must be new: {output}")
    output.mkdir(parents=True)

    certificate_root = ET.parse(certificate).getroot()
    content_by_category: dict[str, str] = {}
    for photo in (node for node in certificate_root.iter() if local(node.tag) == "Photo"):
        category = child_text(photo, "Category")
        content = child_text(photo, "Content")
        if category and content and category not in content_by_category:
            content_by_category[category] = content
    missing = sorted(set(CATEGORY_MAP.values()) - content_by_category.keys())
    if missing:
        raise ValueError(f"Certificate lacks required photo categories: {missing!r}")

    photo_paths: dict[str, Path] = {}
    for native_category, certificate_category in CATEGORY_MAP.items():
        path = output / f"{certificate_category}.jpg"
        path.write_bytes(base64.b64decode(content_by_category[certificate_category], validate=True))
        photo_paths[native_category] = path

    tree = ET.parse(native)
    rewritten = 0
    for item in (node for node in tree.getroot().iter() if local(node.tag) == "PhotoAlbumItem"):
        category = item.attrib.get("Category")
        if category in photo_paths:
            item.set("FileName", str(photo_paths[category]))
            rewritten += 1
    if not rewritten:
        raise ValueError("Native XML contains no required PhotoAlbumItem references")
    target = output / "native_with_local_photos.xml"
    ET.indent(tree, space="  ")
    tree.write(target, encoding="utf-8", xml_declaration=True)
    report = {
        "native_xml": str(native), "certificate_xml": str(certificate),
        "target": str(target), "rewritten_photo_references": rewritten,
        "photos": {key: str(value) for key, value in photo_paths.items()},
    }
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
