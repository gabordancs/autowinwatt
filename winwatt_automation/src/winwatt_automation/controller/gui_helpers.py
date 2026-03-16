from __future__ import annotations

from shlex import join


def build_map_command(
    python_executable: str,
    safe_mode: str,
    extra_args: str | None = None,
) -> list[str]:
    command = [
        python_executable,
        "-m",
        "winwatt_automation.scripts.map_full_program",
        "--safe-mode",
        safe_mode,
    ]
    if extra_args:
        command.extend(extra_args.split())
    return command


def command_preview(command: list[str]) -> str:
    return join(command)
