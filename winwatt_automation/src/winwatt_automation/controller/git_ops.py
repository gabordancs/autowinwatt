from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class GitOps:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def run(self, *args: str) -> CommandResult:
        cmd = ["git", *args]
        completed = subprocess.run(
            cmd,
            cwd=self.repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        return CommandResult(command=cmd, returncode=completed.returncode, stdout=completed.stdout.strip(), stderr=completed.stderr.strip())

    def pull(self) -> CommandResult:
        return self.run("pull")

    def status(self, short: bool = True) -> CommandResult:
        if short:
            return self.run("status", "--short", "--branch")
        return self.run("status", "--branch")

    def add(self, target: str = ".") -> CommandResult:
        return self.run("add", target)

    def commit(self, message: str) -> CommandResult:
        return self.run("commit", "-m", message)

    def push(self) -> CommandResult:
        return self.run("push")

    def current_branch(self) -> str:
        result = self.run("rev-parse", "--abbrev-ref", "HEAD")
        if not result.ok:
            return "unknown"
        return result.stdout.strip() or "unknown"
