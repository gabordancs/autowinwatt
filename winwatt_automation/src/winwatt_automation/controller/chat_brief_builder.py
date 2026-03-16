from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from winwatt_automation.controller.runlog_reader import RunLogSnapshot


@dataclass(slots=True)
class ChatBriefInput:
    goal: str
    branch: str
    git_status_summary: str
    run_snapshot: RunLogSnapshot
    concrete_request: str


def build_chat_brief(payload: ChatBriefInput) -> str:
    latest_json = payload.run_snapshot.latest_json or {}
    run_id = latest_json.get("run_id", "n/a")
    success = latest_json.get("success", "n/a")
    summary = latest_json.get("summary", {})

    latest_summary_lines: list[str] = []
    if summary:
        for key, value in summary.items():
            latest_summary_lines.append(f"- {key}: {value}")
    elif payload.run_snapshot.latest_txt:
        latest_summary_lines.append(f"- latest.txt: {payload.run_snapshot.latest_txt}")
    else:
        latest_summary_lines.append("- Nincs elérhető run log summary (latest.json/latest.txt hiányzik).")

    return "\n".join(
        [
            "Cél:",
            f"- {payload.goal}",
            "",
            "Jelenlegi állapot:",
            f"- branch: {payload.branch}",
            f"- git status röviden: {payload.git_status_summary}",
            f"- latest run id: {run_id}",
            f"- latest success: {success}",
            f"- latest summary röviden: {payload.run_snapshot.compact_summary()}",
            "",
            "Legfrissebb futás summary:",
            *latest_summary_lines,
            "",
            "Konkrét kérés:",
            f"- {payload.concrete_request}",
            "- elemezd a legfrissebb állapotot",
            "- mondd meg a következő legkisebb lépést",
            "- írj Codex promptot a következő körre",
            "",
        ]
    )


def write_chat_brief(content: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path
