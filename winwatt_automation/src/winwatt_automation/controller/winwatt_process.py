from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import signal
import subprocess
import time


@dataclass(slots=True)
class ProcessActionResult:
    ok: bool
    message: str


class WinWattProcessManager:
    def __init__(self, exe_path: str | None):
        self.exe_path = exe_path
        self._process: subprocess.Popen[str] | None = None

    def _process_name(self) -> str | None:
        if not self.exe_path:
            return None
        return Path(self.exe_path).name

    def is_running(self) -> bool:
        if self._process and self._process.poll() is None:
            return True

        name = self._process_name()
        if not name:
            return False

        if Path("/proc").exists():
            ps = subprocess.run(["ps", "-eo", "comm"], text=True, capture_output=True, check=False)
            return any(line.strip() == name for line in ps.stdout.splitlines())

        tasklist = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}"], text=True, capture_output=True, check=False)
        return name.lower() in tasklist.stdout.lower()

    def start(self) -> ProcessActionResult:
        if self.is_running():
            return ProcessActionResult(ok=True, message="WinWatt already running.")
        if not self.exe_path:
            return ProcessActionResult(ok=False, message="WinWatt executable path is not configured.")

        exe = Path(self.exe_path)
        if not exe.exists():
            return ProcessActionResult(ok=False, message=f"Configured WinWatt executable does not exist: {exe}")

        self._process = subprocess.Popen([str(exe)], text=True)
        return ProcessActionResult(ok=True, message=f"WinWatt started (pid={self._process.pid}).")

    def stop(self, force: bool = False, wait_seconds: int = 8) -> ProcessActionResult:
        name = self._process_name()

        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=wait_seconds)
                return ProcessActionResult(ok=True, message="WinWatt process terminated gracefully.")
            except subprocess.TimeoutExpired:
                if not force:
                    return ProcessActionResult(ok=False, message="Graceful stop timed out; rerun with --force.")
                self._process.kill()
                return ProcessActionResult(ok=True, message="WinWatt process force-killed.")

        if not name:
            return ProcessActionResult(ok=False, message="WinWatt executable path is not configured.")

        if Path("/proc").exists():
            pkill_cmd = ["pkill", "-f", name] if force else ["pkill", "-TERM", "-f", name]
            result = subprocess.run(pkill_cmd, text=True, capture_output=True, check=False)
            if result.returncode in {0, 1}:
                return ProcessActionResult(ok=True, message="WinWatt stop command sent (or process not running).")
            return ProcessActionResult(ok=False, message=result.stderr.strip() or "Failed to stop WinWatt")

        if not force:
            close = subprocess.run(["taskkill", "/IM", name], text=True, capture_output=True, check=False)
            if close.returncode == 0:
                return ProcessActionResult(ok=True, message="WinWatt close signal sent.")
            return ProcessActionResult(ok=False, message=close.stderr.strip() or close.stdout.strip())

        kill = subprocess.run(["taskkill", "/F", "/IM", name], text=True, capture_output=True, check=False)
        return ProcessActionResult(ok=kill.returncode == 0, message=kill.stderr.strip() or kill.stdout.strip() or "taskkill finished")
