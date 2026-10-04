from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ArtifactSpec:
    key: str
    extensions: tuple[str, ...]
    required: bool = True
    xml: bool = False
    multiple: bool = False


DEFAULT_SPECS = (
    ArtifactSpec("wwp", (".wwp",)),
    ArtifactSpec("native_xml", (".xml",), xml=True),
    ArtifactSpec("calculation_pdf", (".pdf",)),
    ArtifactSpec("certificate_xml", (".xml",), xml=True),
    ArtifactSpec("photos", (".jpg", ".jpeg", ".png", ".webp"), multiple=True),
)


class ExportPackageError(ValueError):
    pass


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _xml_root(path: Path) -> str:
    try:
        return ET.parse(path).getroot().tag
    except (ET.ParseError, OSError) as exc:
        raise ExportPackageError(f"Hibás XML: {path}: {exc}") from exc


def _entry(path: Path, package_dir: Path, *, xml: bool = False) -> dict:
    stat = path.stat()
    result = {
        "path": path.relative_to(package_dir).as_posix(),
        "size": stat.st_size,
        "sha256": sha256_file(path),
    }
    if xml:
        result["xml_root"] = _xml_root(path)
    return result


def build_export_manifest(
    package_dir: str | Path,
    artifacts: dict[str, str | Path | Iterable[str | Path]],
    *,
    source_project_sha256: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Validate a Q7 export package and return a deterministic evidence manifest.

    Artifact paths must be inside ``package_dir``. XML files are parsed, every
    artifact is hashed, empty files are rejected, and the five Q7 artifact
    classes are required by default. The caller explicitly identifies the two
    XML roles because both use the same extension.
    """
    root = Path(package_dir).resolve()
    if not root.is_dir():
        raise ExportPackageError(f"Nem létező exportkönyvtár: {root}")

    specs = {spec.key: spec for spec in DEFAULT_SPECS}
    unknown = sorted(set(artifacts) - set(specs))
    if unknown:
        raise ExportPackageError(f"Ismeretlen artefaktumtípus: {', '.join(unknown)}")

    missing = [spec.key for spec in DEFAULT_SPECS if spec.required and spec.key not in artifacts]
    if missing:
        raise ExportPackageError(f"Hiányzó kötelező artefaktum: {', '.join(missing)}")

    manifest_artifacts: dict[str, list[dict]] = {}
    for key, value in artifacts.items():
        spec = specs[key]
        values = list(value) if spec.multiple and not isinstance(value, (str, Path)) else [value]
        if spec.required and not values:
            raise ExportPackageError(f"Üres kötelező artefaktumlista: {key}")
        entries = []
        for raw in values:
            path = Path(raw)
            if not path.is_absolute():
                path = root / path
            path = path.resolve()
            try:
                path.relative_to(root)
            except ValueError as exc:
                raise ExportPackageError(f"Az artefaktum az exportkönyvtáron kívül van: {path}") from exc
            if not path.is_file():
                raise ExportPackageError(f"Hiányzó fájl ({key}): {path}")
            if path.stat().st_size == 0:
                raise ExportPackageError(f"Üres fájl ({key}): {path}")
            if path.suffix.casefold() not in spec.extensions:
                raise ExportPackageError(f"Hibás kiterjesztés ({key}): {path.name}")
            entries.append(_entry(path, root, xml=spec.xml))
        manifest_artifacts[key] = sorted(entries, key=lambda item: item["path"])

    return {
        "schema": "autowinwatt.q7-export-package/v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "package_dir": root.name,
        "source_project_sha256": source_project_sha256,
        "metadata": metadata or {},
        "artifacts": manifest_artifacts,
        "checks": {
            "required_artifacts_present": True,
            "all_files_nonempty": True,
            "xml_well_formed": True,
            "all_files_sha256": True,
        },
    }


def write_export_manifest(manifest: dict, output: str | Path) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path
