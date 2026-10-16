"""Policy helpers for large runtime artifacts stored outside Git."""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath


EXTERNAL_ARTIFACT_PREFIXES = (
    ".codex-remote-attachments/",
    "data/delceg56/",
    "data/webwatt_jobs/",
    "output/",
    "outputs/",
    "tmp/",
    "winwatt_automation/data/certificate_builds/",
    "winwatt_automation/data/knowledge/certification_corpus/",
    "winwatt_automation/data/knowledge/global_mapping/",
    "winwatt_automation/data/oeny_reconstruction/",
    "winwatt_automation/data/run_logs/",
    "winwatt_automation/data/runtime_maps/",
    "winwatt_automation/data/snapshots/",
    "winwatt_automation/x/",
)

EXTERNAL_ARTIFACT_PATHS = frozenset({
    "winwatt_automation/data/knowledge/knowledge_store.json",
    "winwatt_automation/data/knowledge/navigation_knowledge.json",
    "winwatt_automation/tests/test.xml",
    "winwatt_automation/tests/testwwp.wwp",
})

EXTERNAL_ARTIFACT_SUFFIXES = (
    ".bak",
    ".checkpoint.json",
    ".jpeg",
    ".jpg",
    ".log",
    ".pdf",
    ".png",
    ".wwp",
)


def normalize_repository_path(path: str | Path) -> str:
    """Return a stable forward-slash path without resolving the filesystem."""
    normalized = PurePosixPath(str(path).replace("\\", "/")).as_posix()
    return normalized[2:] if normalized.startswith("./") else normalized


def is_external_artifact_path(path: str | Path) -> bool:
    """Whether ``path`` is intentionally restored from the artifact archive."""
    normalized = normalize_repository_path(path)
    lowered = normalized.casefold()
    if normalized in EXTERNAL_ARTIFACT_PATHS:
        return True
    if any(lowered.startswith(prefix.casefold()) for prefix in EXTERNAL_ARTIFACT_PREFIXES):
        return True
    name = PurePosixPath(normalized).name.casefold()
    if any(name.endswith(suffix) for suffix in EXTERNAL_ARTIFACT_SUFFIXES):
        return True
    return ".wwp." in name or bool(re.search(r"\.tmp\d*$", name))
