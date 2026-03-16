from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RunLogSnapshot:
    latest_json_path: Path
    latest_txt_path: Path
    index_json_path: Path
    latest_json: dict[str, Any] | None
    latest_txt: str | None
    index_json: dict[str, Any] | None

    def compact_summary(self) -> str:
        if not self.latest_json:
            return "No structured latest run metadata found."

        run_id = self.latest_json.get("run_id", "unknown")
        success = self.latest_json.get("success", "unknown")
        command = self.latest_json.get("command", "unknown")
        short_summary = (self.latest_json.get("summary") or {}).get("diff_summary") or (self.latest_json.get("summary") or {})
        return f"run_id={run_id} success={success} command={command} summary={short_summary}"


class RunLogReader:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.logs_dir = repo_root / "data" / "run_logs"

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return loaded if isinstance(loaded, dict) else None

    def _read_text(self, path: Path) -> str | None:
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8").strip()

    def read_latest(self) -> RunLogSnapshot:
        latest_json_path = self.logs_dir / "latest.json"
        latest_txt_path = self.logs_dir / "latest.txt"
        index_json_path = self.logs_dir / "index.json"
        return RunLogSnapshot(
            latest_json_path=latest_json_path,
            latest_txt_path=latest_txt_path,
            index_json_path=index_json_path,
            latest_json=self._read_json(latest_json_path),
            latest_txt=self._read_text(latest_txt_path),
            index_json=self._read_json(index_json_path),
        )
