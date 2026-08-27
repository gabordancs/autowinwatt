from pathlib import Path

import pytest

from winwatt_automation.scripts.full_authorized_explore import create_execution_sandbox


def test_execution_sandbox_copies_project_without_touching_source(tmp_path: Path) -> None:
    source = tmp_path / "source.wwp"
    source.write_bytes(b"project-data")
    result = create_execution_sandbox(source_project=source, sandbox_root=tmp_path / "sandbox", run_id="run-1")
    target = Path(result["sandbox_project"])
    assert target.read_bytes() == b"project-data"
    assert source.read_bytes() == b"project-data"
    assert target != source


def test_execution_sandbox_rejects_non_project_source(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("no", encoding="utf-8")
    with pytest.raises(ValueError, match=".wwp"):
        create_execution_sandbox(source_project=source, sandbox_root=tmp_path / "sandbox", run_id="run-1")
