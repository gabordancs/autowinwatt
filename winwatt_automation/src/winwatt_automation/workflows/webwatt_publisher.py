"""Idempotent publication of local certificate review artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class ReviewArtifactApi(Protocol):
    def upload_if_missing(self, storage_path: str, source: Path) -> bool: ...
    def ensure_document(
        self, *, project_id: str, user_id: str, doc_type: str, storage_path: str,
    ) -> tuple[str, bool]: ...


def publish_review_artifacts(
    *, api: ReviewArtifactApi, output_dir: Path, project_id: str,
    user_id: str, job_id: str,
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for artifact in sorted(output_dir.glob("*.json")):
        storage_path = f"{project_id}/certification-result/{job_id}/{artifact.name}"
        uploaded = api.upload_if_missing(storage_path, artifact)
        document_id, document_created = api.ensure_document(
            project_id=project_id, user_id=user_id,
            doc_type=f"Gépi előfeldolgozás · {artifact.name}", storage_path=storage_path,
        )
        artifacts.append({
            "document_id": document_id,
            "storage_path": storage_path,
            "name": artifact.name,
            "uploaded": uploaded,
            "document_created": document_created,
        })
    if not artifacts:
        raise RuntimeError("Processing ended without a review artifact.")
    return artifacts
