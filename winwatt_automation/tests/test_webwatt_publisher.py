from pathlib import Path

from winwatt_automation.workflows.webwatt_publisher import publish_review_artifacts


class FakeApi:
    def __init__(self) -> None:
        self.objects: set[str] = set()
        self.documents: dict[tuple[str, str], str] = {}
        self.upload_calls = 0
        self.insert_calls = 0

    def upload_if_missing(self, storage_path: str, source: Path) -> bool:
        if storage_path in self.objects:
            return False
        self.objects.add(storage_path)
        self.upload_calls += 1
        return True

    def ensure_document(
        self, *, project_id: str, user_id: str, doc_type: str, storage_path: str,
    ) -> tuple[str, bool]:
        existing = self.documents.get((project_id, storage_path))
        if existing is not None:
            return existing, False
        self.insert_calls += 1
        identifier = f"document-{self.insert_calls}"
        self.documents[(project_id, storage_path)] = identifier
        return identifier, True


def test_publication_reuses_storage_objects_and_document_rows(tmp_path: Path) -> None:
    output = tmp_path / "result"
    output.mkdir()
    (output / "a.json").write_text("{}", encoding="utf-8")
    (output / "b.json").write_text("{}", encoding="utf-8")
    api = FakeApi()

    first = publish_review_artifacts(
        api=api, output_dir=output, project_id="project", user_id="user", job_id="job",
    )
    second = publish_review_artifacts(
        api=api, output_dir=output, project_id="project", user_id="user", job_id="job",
    )

    assert api.upload_calls == 2
    assert api.insert_calls == 2
    assert all(item["uploaded"] and item["document_created"] for item in first)
    assert all(not item["uploaded"] and not item["document_created"] for item in second)
    assert [item["document_id"] for item in first] == [item["document_id"] for item in second]
