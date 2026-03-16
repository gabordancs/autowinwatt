from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from winwatt_automation.controller.chat_brief_builder import ChatBriefInput, build_chat_brief, write_chat_brief
from winwatt_automation.controller.config import ControllerConfig
from winwatt_automation.controller.git_ops import CommandResult, GitOps
from winwatt_automation.controller.runlog_reader import RunLogReader
from winwatt_automation.controller.script_runner import ScriptRunResult, ScriptRunner
from winwatt_automation.controller.winwatt_process import ProcessActionResult, WinWattProcessManager


@dataclass(slots=True)
class CycleResult:
    pull_result: CommandResult
    status_result: CommandResult
    script_result: ScriptRunResult
    winwatt_start_result: ProcessActionResult
    chat_brief_path: Path
    chat_brief: str


class DevCycleController:
    def __init__(self, config: ControllerConfig):
        self.config = config
        self.git = GitOps(config.repo_root)
        self.runlogs = RunLogReader(config.repo_root)
        self.runner = ScriptRunner(config.repo_root, config.python_executable)
        self.winwatt = WinWattProcessManager(config.winwatt_exe_path)

    def repo_status(self) -> dict[str, str]:
        status = self.git.status(short=False)
        branch = self.git.current_branch()
        runlog = self.runlogs.read_latest()
        return {
            "branch": branch,
            "git_status": status.stdout or status.stderr or "git status unavailable",
            "runlog_summary": runlog.compact_summary(),
        }

    def prepare_chat(self, goal: str, concrete_request: str) -> Path:
        status = self.git.status(short=False)
        branch = self.git.current_branch()
        snapshot = self.runlogs.read_latest()
        brief = build_chat_brief(
            ChatBriefInput(
                goal=goal,
                branch=branch,
                git_status_summary=status.stdout or status.stderr or "n/a",
                run_snapshot=snapshot,
                concrete_request=concrete_request,
            )
        )
        return write_chat_brief(brief, self.config.chat_brief_output_path)

    def run_script(self, script_name: str, timeout_seconds: int | None = None, safe_mode: str | None = None, passthrough_args: list[str] | None = None) -> ScriptRunResult:
        return self.runner.run(
            script_name=script_name,
            timeout_seconds=timeout_seconds or self.config.default_timeout_seconds,
            safe_mode=safe_mode or self.config.default_safe_mode,
            passthrough_args=passthrough_args,
        )

    def run_cycle(
        self,
        script_name: str,
        goal: str,
        concrete_request: str,
        timeout_seconds: int | None = None,
        safe_mode: str | None = None,
        stop_winwatt_on_timeout: bool = False,
    ) -> CycleResult:
        pull = self.git.pull()
        status = self.git.status(short=False)
        winwatt_start = self.winwatt.start()
        script_result = self.run_script(script_name, timeout_seconds=timeout_seconds, safe_mode=safe_mode)
        if script_result.timed_out and stop_winwatt_on_timeout:
            self.winwatt.stop(force=False)

        snapshot = self.runlogs.read_latest()
        brief = build_chat_brief(
            ChatBriefInput(
                goal=goal,
                branch=self.git.current_branch(),
                git_status_summary=status.stdout or status.stderr or "n/a",
                run_snapshot=snapshot,
                concrete_request=concrete_request,
            )
        )
        output = write_chat_brief(brief, self.config.chat_brief_output_path)

        return CycleResult(
            pull_result=pull,
            status_result=status,
            script_result=script_result,
            winwatt_start_result=winwatt_start,
            chat_brief_path=output,
            chat_brief=brief,
        )
