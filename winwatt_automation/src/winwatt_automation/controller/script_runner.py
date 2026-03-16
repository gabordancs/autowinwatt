from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import time


SCRIPT_REGISTRY: dict[str, str] = {
    "map_full_program": "winwatt_automation.scripts.map_full_program",
    "explore_file_menu": "winwatt_automation.scripts.explore_file_menu",
    "explore_file_menu_popup": "winwatt_automation.scripts.explore_file_menu_popup",
    "dialog_explorer": "winwatt_automation.scripts.inspect_live_ui",
}


@dataclass(slots=True)
class ScriptRunResult:
    status: str
    exit_code: int | None
    elapsed_seconds: float
    command: list[str]
    timed_out: bool
    message: str


class ScriptRunner:
    def __init__(self, repo_root: Path, python_executable: str):
        self.repo_root = repo_root
        self.python_executable = python_executable

    def resolve_target(self, script_name: str) -> str:
        return SCRIPT_REGISTRY.get(script_name, script_name)

    def build_command(self, script_name: str, safe_mode: str | None = None, passthrough_args: list[str] | None = None) -> list[str]:
        if script_name == "python":
            return [self.python_executable, *(passthrough_args or [])]

        module_or_target = self.resolve_target(script_name)
        command = [self.python_executable, "-m", module_or_target]
        if safe_mode:
            command.extend(["--safe-mode", safe_mode])
        if passthrough_args:
            command.extend(passthrough_args)
        return command

    def run(
        self,
        script_name: str,
        timeout_seconds: int,
        safe_mode: str | None = None,
        passthrough_args: list[str] | None = None,
    ) -> ScriptRunResult:
        command = self.build_command(script_name, safe_mode=safe_mode, passthrough_args=passthrough_args)
        started = time.monotonic()
        process = subprocess.Popen(command, cwd=self.repo_root)
        try:
            exit_code = process.wait(timeout=timeout_seconds)
            elapsed = time.monotonic() - started
            return ScriptRunResult(
                status="success" if exit_code == 0 else "error",
                exit_code=exit_code,
                elapsed_seconds=elapsed,
                command=command,
                timed_out=False,
                message="Script finished." if exit_code == 0 else "Script failed.",
            )
        except subprocess.TimeoutExpired:
            process.terminate()
            elapsed = time.monotonic() - started
            return ScriptRunResult(
                status="timeout",
                exit_code=None,
                elapsed_seconds=elapsed,
                command=command,
                timed_out=True,
                message="Script timed out and terminate signal was sent.",
            )
