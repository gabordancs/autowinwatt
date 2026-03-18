from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def write_progress_status(
    status_path: str | Path,
    *,
    run_id: str,
    state: str,
    message: str,
    command: str | None = None,
    details: dict[str, Any] | None = None,
) -> Path:
    path = Path(status_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "state": state,
        "message": message,
        "command": command,
        "details": details or {},
        "updated_at": _utc_now_iso(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def launch_progress_overlay(status_path: str | Path) -> subprocess.Popen[str] | None:
    command = [sys.executable, "-m", "winwatt_automation.scripts.progress_overlay", "--status-file", str(status_path)]
    kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
        "start_new_session": True,
        "text": True,
    }
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    try:
        return subprocess.Popen(command, **kwargs)
    except Exception:
        return None
