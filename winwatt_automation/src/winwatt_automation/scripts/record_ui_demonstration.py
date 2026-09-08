"""Record human-guided, sandbox-only UI navigation as non-verified evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.research.demonstrations import (
    DemonstrationStep, DemonstrationStore, infer_manual_transition, new_demonstration, semantic_state_fingerprint,
)
from winwatt_automation.research.ui_exploration import SandboxUIExplorer
from winwatt_automation.services.winwatt_service import WinWattService


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _mdi_title(window) -> str | None:
    """Read MDI state through the recorder's already-owned window.

    During manual capture PowerShell deliberately owns the foreground.  This
    avoids the normal foreground-sensitive cached-window resolver entirely.
    """
    try:
        from pywinauto.application import Application
        native = Application(backend="win32").connect(process=int(window.process_id())).window(handle=window.handle)
        for child in native.descendants():
            if child.class_name() in {"TChildWinForm", "TErrorMDIForm"} and child.is_visible() and child.window_text().strip():
                return child.window_text().strip()
    except Exception:
        pass
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a human WinWatt navigation demonstration in a sandbox")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--notes")
    parser.add_argument("--demonstrations-dir", type=Path, default=PROJECT_ROOT / "data" / "knowledge" / "demonstrations")
    args = parser.parse_args()

    source = args.project.resolve()
    sandbox = args.demonstrations_dir.resolve() / "sandboxes" / args.name / "sandbox" / source.name
    service = WinWattService(); service.create_sandbox(source, sandbox); service.open_project(sandbox)
    explorer = SandboxUIExplorer(get_main_window(), sandbox)
    previous = explorer.inspect_window()
    previous_mdi = _mdi_title(explorer.window)
    steps: list[DemonstrationStep] = []
    print("Sandbox WinWatt open. Navigate manually; return here after every meaningful action.")
    print("Press Enter to capture. An optional note is guidance only, never a control locator.")
    print("Type 'done' to save, or 'quit' to discard.")
    while True:
        command = input("capture> ").strip()
        if command.casefold() == "quit":
            print("Discarded."); return 0
        if command.casefold() == "done":
            break
        current = explorer.inspect_window()
        note = input("Optional note (blank = none): ").strip() or None
        before_mdi, after_mdi = previous_mdi, _mdi_title(explorer.window)
        transition_type, confidence, observed, candidates = infer_manual_transition(previous, current)
        step = DemonstrationStep(
            step_index=len(steps) + 1,
            timestamp=datetime.now(timezone.utc).isoformat(),
            raw_state_fingerprint=current.state_fingerprint,
            semantic_state_fingerprint=semantic_state_fingerprint(current),
            active_mdi_title=after_mdi,
            window_identity=current.identity,
            window_class=current.class_name,
            source_state=previous.state_fingerprint,
            target_state=current.state_fingerprint,
            semantic_state_delta=semantic_state_fingerprint(previous) != semantic_state_fingerprint(current),
            action_type=transition_type,
            observed_control=observed,
            candidate_controls=candidates,
            source_raw_fingerprint=previous.state_fingerprint,
            source_semantic_fingerprint=semantic_state_fingerprint(previous),
            target_raw_fingerprint=current.state_fingerprint,
            target_semantic_fingerprint=semantic_state_fingerprint(current),
            transition_type=transition_type,
            confidence=confidence,
            selected_candidate_if_unambiguous=observed,
            active_mdi_before=before_mdi,
            active_mdi_after=after_mdi,
            human_note=note,
        )
        steps.append(step); previous = current; previous_mdi = after_mdi
        print(f"Captured step {step.step_index}: {step.action_type}, target={step.target_state}")

    terminal = {
        "raw_state_fingerprint": previous.state_fingerprint,
        "semantic_state_fingerprint": semantic_state_fingerprint(previous),
        "active_mdi_title": _mdi_title(explorer.window),
        "window_class": previous.class_name,
    }
    demo = new_demonstration(name=args.name, target=args.target, source_project=source, terminal=terminal, steps=steps, notes=args.notes)
    path = DemonstrationStore(args.demonstrations_dir).save(demo)
    print({"saved": str(path), "steps": len(steps), "provenance": demo.provenance})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
