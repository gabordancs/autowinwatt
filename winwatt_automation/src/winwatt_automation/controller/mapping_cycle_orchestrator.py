from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from winwatt_automation.controller.chat_brief_builder import ChatBriefInput, build_chat_brief
from winwatt_automation.controller.config import ControllerConfig
from winwatt_automation.controller.git_ops import GitOps
from winwatt_automation.controller.runlog_reader import RunLogReader, RunLogSnapshot

DEFAULT_LOG_PATTERNS = [
    "PLACEHOLDER_ACTION_OUTCOME",
    "MODAL_CLOSE_RESULT",
    "ROOT_MENU_REOPEN_EXECUTED",
    "FRESH_ROOT_SNAPSHOT_CAPTURED",
    "ACTION_CHANGED_MENU_STATE",
    "PROJECT_OPEN_STATE_TRANSITION",
    "DBG_PHASE_TIMING phase=subtree_traversal",
]

DEFAULT_MILESTONES = [
    "top_menu_stability",
    "placeholder_traversal",
    "modal_handling",
    "recent_projects_policy",
    "project_open_transition",
    "full_state_mapping",
]

STANDARD_RESULT_TEMPLATE: dict[str, Any] = {
    "diagnosis": "",
    "changes": [],
    "files": [],
    "tests_run": [],
    "test_results": [],
    "manual_run_command": "",
    "expected_logs": [],
    "open_risks": [],
    "next_step": "",
    "commit": "",
}


@dataclass(slots=True)
class CommandExecution:
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass(slots=True)
class MappingCyclePaths:
    base_dir: Path
    status_path: Path
    prompt_path: Path
    result_path: Path
    handoff_path: Path
    log_extract_path: Path


@dataclass(slots=True)
class MappingCycleStatus:
    cycle_id: str
    milestone: str
    state: str
    goal: str
    request: str
    run_log_json: str | None = None
    run_log_txt: str | None = None
    run_log_path: str | None = None
    latest_prompt_path: str | None = None
    latest_result_path: str | None = None
    latest_handoff_path: str | None = None
    latest_log_extract_path: str | None = None
    log_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_LOG_PATTERNS))
    milestones: dict[str, str] = field(default_factory=lambda: {item: "pending" for item in DEFAULT_MILESTONES})
    last_codex_result: dict[str, Any] = field(default_factory=dict)
    last_test_runs: list[dict[str, Any]] = field(default_factory=list)
    last_manual_run: dict[str, Any] | None = None
    last_log_extract: list[dict[str, Any]] = field(default_factory=list)
    commit: str | None = None
    recommended_next_step: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["updated_at"] = _utc_now_iso()
        return payload


@dataclass(slots=True)
class IngestResult:
    status: MappingCycleStatus
    codex_result: dict[str, Any]


@dataclass(slots=True)
class TestStepResult:
    tests: list[CommandExecution]
    manual_run: CommandExecution | None
    log_extract: list[dict[str, Any]]


class MappingCycleOrchestrator:
    def __init__(self, config: ControllerConfig, workspace_dir: str = "data/mapping_cycle"):
        self.config = config
        self.repo_root = config.repo_root
        self.git = GitOps(config.repo_root)
        self.runlogs = RunLogReader(config.repo_root)
        self.paths = self._build_paths(workspace_dir)

    def _build_paths(self, workspace_dir: str) -> MappingCyclePaths:
        base_dir = self.repo_root / workspace_dir
        return MappingCyclePaths(
            base_dir=base_dir,
            status_path=base_dir / "status.json",
            prompt_path=base_dir / "codex_prompt.txt",
            result_path=base_dir / "codex_result.json",
            handoff_path=base_dir / "chatgpt_handoff.md",
            log_extract_path=base_dir / "log_extract.json",
        )

    def ensure_workspace(self) -> MappingCyclePaths:
        self.paths.base_dir.mkdir(parents=True, exist_ok=True)
        return self.paths

    def load_status(self) -> MappingCycleStatus:
        self.ensure_workspace()
        if not self.paths.status_path.exists():
            snapshot = self.runlogs.read_latest()
            status = MappingCycleStatus(
                cycle_id=_cycle_id(),
                milestone="top_menu_stability",
                state="discovery",
                goal="Stabilize WinWatt runtime mapping cycle.",
                request="Prepare the next smallest Codex step for mapping reliability.",
                run_log_json=_rel_or_none(snapshot.latest_json_path if snapshot.latest_json_path.exists() else None, self.repo_root),
                run_log_txt=_rel_or_none(snapshot.latest_txt_path if snapshot.latest_txt_path.exists() else None, self.repo_root),
                run_log_path=_guess_latest_log_path(snapshot, self.repo_root),
            )
            self.save_status(status)
            return status

        payload = json.loads(self.paths.status_path.read_text(encoding="utf-8"))
        return MappingCycleStatus(**payload)

    def save_status(self, status: MappingCycleStatus) -> Path:
        self.ensure_workspace()
        self.paths.status_path.write_text(json.dumps(status.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return self.paths.status_path

    def prepare(self, goal: str | None = None, request: str | None = None, milestone: str | None = None, state: str | None = None) -> Path:
        status = self.load_status()
        snapshot = self.runlogs.read_latest()
        if goal:
            status.goal = goal
        if request:
            status.request = request
        if milestone:
            status.milestone = milestone
        if state:
            status.state = state
        status.run_log_json = _rel_or_none(snapshot.latest_json_path if snapshot.latest_json_path.exists() else None, self.repo_root)
        status.run_log_txt = _rel_or_none(snapshot.latest_txt_path if snapshot.latest_txt_path.exists() else None, self.repo_root)
        status.run_log_path = _guess_latest_log_path(snapshot, self.repo_root)

        chat_brief = build_chat_brief(
            ChatBriefInput(
                goal=status.goal,
                branch=self.git.current_branch(),
                git_status_summary=(self.git.status(short=False).stdout or "n/a"),
                run_snapshot=snapshot,
                concrete_request=status.request,
            )
        )

        prompt = "\n".join(
            [
                "# WinWatt Mapping Cycle - Next Codex Task",
                "",
                f"Milestone: {status.milestone}",
                f"State: {status.state}",
                f"Goal: {status.goal}",
                f"Request: {status.request}",
                f"Status file: {self.paths.status_path.relative_to(self.repo_root)}",
                f"Expected result file: {self.paths.result_path.relative_to(self.repo_root)}",
                "",
                "## Current developer brief",
                chat_brief,
                "",
                "## Required Codex result schema",
                json.dumps(STANDARD_RESULT_TEMPLATE, ensure_ascii=False, indent=2),
                "",
                "## Notes",
                f"- Preferred milestones: {', '.join(DEFAULT_MILESTONES)}",
                f"- Important log patterns: {', '.join(status.log_patterns)}",
                "- Keep the result machine-readable JSON.",
            ]
        )
        self.paths.prompt_path.write_text(prompt, encoding="utf-8")
        status.latest_prompt_path = str(self.paths.prompt_path.relative_to(self.repo_root))
        self.save_status(status)
        return self.paths.prompt_path

    def ingest(self, result_path: Path | None = None) -> IngestResult:
        status = self.load_status()
        path = result_path or self.paths.result_path
        payload = json.loads(path.read_text(encoding="utf-8"))
        codex_result = dict(STANDARD_RESULT_TEMPLATE)
        codex_result.update(payload)
        status.last_codex_result = codex_result
        status.latest_result_path = str(path.relative_to(self.repo_root)) if path.is_absolute() else str(path)
        status.recommended_next_step = _string_or_none(codex_result.get("next_step"))
        status.commit = _string_or_none(codex_result.get("commit"))
        self.save_status(status)
        return IngestResult(status=status, codex_result=codex_result)

    def run_tests(self, result_path: Path | None = None, run_manual: bool = True) -> TestStepResult:
        ingest = self.ingest(result_path=result_path)
        codex_result = ingest.codex_result
        test_runs: list[CommandExecution] = []
        for command in list(codex_result.get("tests_run") or []):
            if not str(command).strip():
                continue
            test_runs.append(self._run_shell_command(str(command)))

        manual_run: CommandExecution | None = None
        manual_command = _string_or_none(codex_result.get("manual_run_command"))
        if run_manual and manual_command:
            manual_run = self._run_shell_command(manual_command)

        expected_logs = [str(item) for item in (codex_result.get("expected_logs") or []) if str(item).strip()]
        log_extract = self.extract_logs(expected_logs or ingest.status.log_patterns)

        status = self.load_status()
        status.last_test_runs = [_execution_to_dict(item) for item in test_runs]
        status.last_manual_run = _execution_to_dict(manual_run) if manual_run else None
        status.last_log_extract = log_extract
        status.latest_log_extract_path = str(self.paths.log_extract_path.relative_to(self.repo_root))
        self.save_status(status)
        return TestStepResult(tests=test_runs, manual_run=manual_run, log_extract=log_extract)

    def handoff(self, result_path: Path | None = None) -> Path:
        ingest = self.ingest(result_path=result_path)
        status = self.load_status()
        result = ingest.codex_result
        lines = [
            "# WinWatt Mapping Cycle Handoff",
            "",
            "## Rövid diagnózis",
            _bullet_or_placeholder(_string_or_none(result.get("diagnosis")), "Nincs megadva diagnózis."),
            "",
            "## Codex módosításai",
            *_bullets(result.get("changes") or [], placeholder="Nincs rögzített módosítás."),
            "",
            "## Érintett fájlok",
            *_bullets(result.get("files") or [], placeholder="Nincs megadott fájllista."),
            "",
            "## Tesztek és eredmények",
            *_format_test_section(status.last_test_runs, status.last_manual_run, result.get("test_results") or []),
            "",
            "## Releváns logminták",
            *_format_log_extract(status.last_log_extract),
            "",
            "## Aktuális milestone / state",
            f"- milestone: {status.milestone}",
            f"- state: {status.state}",
            "",
            "## Nyitott kockázatok",
            *_bullets(result.get("open_risks") or [], placeholder="Nincs nyitott kockázat megadva."),
            "",
            "## Következő ajánlott lépés",
            _bullet_or_placeholder(status.recommended_next_step, "Nincs ajánlott következő lépés."),
            "",
            "## Commit hash",
            f"- {status.commit or _current_commit(self.git)}",
        ]
        self.paths.handoff_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        status.latest_handoff_path = str(self.paths.handoff_path.relative_to(self.repo_root))
        self.save_status(status)
        return self.paths.handoff_path

    def cycle(self, result_path: Path | None = None, run_manual: bool = True) -> dict[str, Path]:
        prompt_path = self.prepare()
        result_file = result_path or self.paths.result_path
        if result_file.exists():
            self.run_tests(result_file, run_manual=run_manual)
            handoff_path = self.handoff(result_file)
        else:
            handoff_path = self.handoff_path
        return {
            "status": self.paths.status_path,
            "prompt": prompt_path,
            "result": result_file,
            "handoff": handoff_path,
            "log_extract": self.paths.log_extract_path,
        }

    def extract_logs(self, patterns: list[str]) -> list[dict[str, Any]]:
        snapshot = self.runlogs.read_latest()
        log_path = _resolve_latest_log_path(snapshot, self.repo_root)
        matches: list[dict[str, Any]] = []
        if log_path and log_path.exists():
            for line_number, line in enumerate(log_path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                for pattern in patterns:
                    if pattern in line:
                        matches.append({"pattern": pattern, "line_number": line_number, "line": line})
        self.paths.log_extract_path.write_text(json.dumps(matches, ensure_ascii=False, indent=2), encoding="utf-8")
        return matches

    def _run_shell_command(self, command: str) -> CommandExecution:
        completed = subprocess.run(
            command,
            cwd=self.repo_root,
            shell=True,
            text=True,
            capture_output=True,
            check=False,
        )
        return CommandExecution(command=command, returncode=completed.returncode, stdout=completed.stdout.strip(), stderr=completed.stderr.strip())


def _format_test_section(test_runs: list[dict[str, Any]], manual_run: dict[str, Any] | None, declared_results: list[Any]) -> list[str]:
    lines: list[str] = []
    if test_runs:
        for item in test_runs:
            lines.append(f"- test: `{item['command']}` => rc={item['returncode']}")
    else:
        lines.append("- Nincs futtatott automata teszt rögzítve.")
    if declared_results:
        for item in declared_results:
            lines.append(f"- declared: {item}")
    if manual_run:
        lines.append(f"- manual: `{manual_run['command']}` => rc={manual_run['returncode']}")
    return lines


def _format_log_extract(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- Nem találtam illeszkedő logmintát."]
    return [f"- {item['pattern']} @ line {item['line_number']}: {item['line']}" for item in items[:20]]


def _bullets(items: list[Any], placeholder: str) -> list[str]:
    if not items:
        return [f"- {placeholder}"]
    return [f"- {item}" for item in items]


def _bullet_or_placeholder(value: str | None, placeholder: str) -> str:
    return f"- {value}" if value else f"- {placeholder}"


def _execution_to_dict(execution: CommandExecution) -> dict[str, Any]:
    return {
        "command": execution.command,
        "returncode": execution.returncode,
        "stdout": execution.stdout,
        "stderr": execution.stderr,
    }


def _string_or_none(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cycle_id() -> str:
    return datetime.now(timezone.utc).strftime("mapping-cycle-%Y%m%dT%H%M%SZ")


def _rel_or_none(path: Path | None, repo_root: Path) -> str | None:
    if not path:
        return None
    return str(path.relative_to(repo_root)) if path.is_absolute() else str(path)


def _resolve_latest_log_path(snapshot: RunLogSnapshot, repo_root: Path) -> Path | None:
    payload = snapshot.latest_json or {}
    output_paths = payload.get("output_paths") or {}
    log_rel = output_paths.get("log_path")
    if log_rel:
        return (repo_root / log_rel).resolve()
    return None


def _guess_latest_log_path(snapshot: RunLogSnapshot, repo_root: Path) -> str | None:
    resolved = _resolve_latest_log_path(snapshot, repo_root)
    return _rel_or_none(resolved, repo_root) if resolved else None


def _current_commit(git: GitOps) -> str:
    result = git.run("rev-parse", "HEAD")
    return result.stdout if result.ok else "unknown"
