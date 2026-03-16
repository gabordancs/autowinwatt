from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys


@dataclass(slots=True)
class ControllerConfig:
    repo_root: Path
    python_executable: str
    winwatt_exe_path: str | None
    default_timeout_seconds: int
    default_safe_mode: str
    chat_brief_output_path: Path

    @classmethod
    def from_env(cls, repo_root: Path | None = None) -> "ControllerConfig":
        resolved_repo = (repo_root or Path(__file__).resolve().parents[3]).resolve()
        timeout_raw = os.getenv("WWA_CONTROLLER_TIMEOUT_SECONDS", "300")
        try:
            timeout_seconds = max(1, int(timeout_raw))
        except ValueError:
            timeout_seconds = 300

        safe_mode = os.getenv("WWA_CONTROLLER_SAFE_MODE", "safe").strip().lower() or "safe"
        if safe_mode not in {"safe", "caution", "blocked"}:
            safe_mode = "safe"

        chat_path_raw = os.getenv("WWA_CHAT_BRIEF_OUTPUT", "data/chat_prep/latest_chat_brief.txt")
        chat_path = (resolved_repo / chat_path_raw).resolve() if not Path(chat_path_raw).is_absolute() else Path(chat_path_raw)

        return cls(
            repo_root=resolved_repo,
            python_executable=os.getenv("WWA_CONTROLLER_PYTHON", sys.executable),
            winwatt_exe_path=os.getenv("WWA_WINWATT_EXE_PATH") or None,
            default_timeout_seconds=timeout_seconds,
            default_safe_mode=safe_mode,
            chat_brief_output_path=chat_path,
        )
