"""Manual smoke diagnostic for the WinWatt project-open accelerator path.

Focuses only on whether the configured project-open accelerator sequence triggers
an Open File dialog in a real UI session.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "winwatt_automation" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from winwatt_automation.live_ui.app_connector import (
    connect_to_winwatt,
    describe_foreground_window,
    ensure_main_window_foreground_before_click,
    get_cached_main_window,
    prepare_main_window_for_menu_interaction,
)
from winwatt_automation.live_ui.project_open_accelerator import (
    PROJECT_OPEN_ACCELERATOR_MODE,
    send_project_open_accelerator,
)

DEFAULT_LOG_PATH = ROOT / "logs" / "winwatt_open_project_accelerator_smoke.json"
POLL_INTERVAL_S = 0.1


def _safe_call(obj: Any, method_name: str, default: Any = None) -> Any:
    method = getattr(obj, method_name, None)
    if not callable(method):
        return default
    try:
        return method()
    except Exception:
        return default



def _window_snapshot(window: Any) -> dict[str, Any]:
    rectangle = _safe_call(window, "rectangle", None)
    rect_payload = None
    if rectangle is not None:
        try:
            rect_payload = {
                "left": int(rectangle.left),
                "top": int(rectangle.top),
                "right": int(rectangle.right),
                "bottom": int(rectangle.bottom),
            }
        except Exception:
            rect_payload = None

    handle = _safe_call(window, "handle", None)
    process_id = _safe_call(window, "process_id", None)
    return {
        "title": (_safe_call(window, "window_text", "") or "").strip(),
        "class_name": (_safe_call(window, "class_name", "") or "").strip(),
        "handle": int(handle) if handle is not None else None,
        "process_id": int(process_id) if process_id is not None else None,
        "is_visible": bool(_safe_call(window, "is_visible", False)),
        "is_enabled": bool(_safe_call(window, "is_enabled", False)),
        "rectangle": rect_payload,
    }



def _looks_like_open_dialog(candidate: dict[str, Any]) -> bool:
    title = str(candidate.get("title") or "").lower()
    class_name = str(candidate.get("class_name") or "").lower()
    title_keywords = (
        "open",
        "open file",
        "file name",
        "megnyit",
        "megnyitás",
        "fájlnév",
        "fájl",
    )
    class_keywords = ("#32770", "dialog", "dlg")
    return any(keyword in title for keyword in title_keywords) or any(keyword in class_name for keyword in class_keywords)



def _visible_top_level_windows() -> list[Any]:
    from pywinauto import Desktop

    desktop = Desktop(backend="uia")
    return [window for window in desktop.windows(top_level_only=True) if bool(_safe_call(window, "is_visible", False))]



def _detect_dialog(process_id: int | None, baseline_handles: set[int], timeout_s: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    candidates_seen: list[dict[str, Any]] = []

    while time.monotonic() < deadline:
        for window in _visible_top_level_windows():
            snapshot = _window_snapshot(window)
            candidates_seen.append(snapshot)

            handle = snapshot.get("handle")
            pid_match = process_id is not None and snapshot.get("process_id") == process_id
            newly_appeared = handle is not None and handle not in baseline_handles
            if not _looks_like_open_dialog(snapshot):
                continue
            if process_id is not None and not (pid_match or newly_appeared):
                continue

            return {
                "dialog_detected": True,
                "dialog": snapshot,
                "candidate_count": len(candidates_seen),
            }
        time.sleep(POLL_INTERVAL_S)

    return {
        "dialog_detected": False,
        "dialog": None,
        "candidate_count": len(candidates_seen),
    }



def run_smoke(
    *,
    timeout_s: float,
    step_delay_s: float,
    log_path: Path,
    accelerator_mode: str = PROJECT_OPEN_ACCELERATOR_MODE,
) -> int:
    started_monotonic = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()

    connect_to_winwatt()
    prepare_main_window_for_menu_interaction()
    ensure_main_window_foreground_before_click(action_label="open_project_accelerator_smoke", allow_dialog=True)

    main_window = get_cached_main_window()
    process_id = _safe_call(main_window, "process_id", None)
    baseline_handles = {
        snapshot.get("handle")
        for snapshot in (_window_snapshot(window) for window in _visible_top_level_windows())
        if snapshot.get("handle") is not None
    }

    foreground_before = describe_foreground_window()
    accelerator_info = send_project_open_accelerator(mode=accelerator_mode, step_delay_s=step_delay_s)
    detection = _detect_dialog(process_id=process_id, baseline_handles=baseline_handles, timeout_s=timeout_s)
    foreground_after = describe_foreground_window()
    elapsed_s = round(time.monotonic() - started_monotonic, 3)

    dialog = detection.get("dialog") or {}
    payload = {
        "timestamp_utc": started_at,
        "script": str(Path(__file__).relative_to(ROOT)),
        "project_open_method": accelerator_info["project_open_method"],
        "sequence": accelerator_info["sequence"],
        "foreground_before": foreground_before,
        "foreground_after": foreground_after,
        "dialog_detected": bool(detection.get("dialog_detected")),
        "dialog_title": dialog.get("title"),
        "dialog_class": dialog.get("class_name"),
        "dialog_handle": dialog.get("handle"),
        "dialog_process_id": dialog.get("process_id"),
        "elapsed_time_s": elapsed_s,
        "timeout_s": timeout_s,
        "step_delay_s": step_delay_s,
        "candidate_count": detection.get("candidate_count"),
    }

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["dialog_detected"] else 1



def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke diagnostic for the configured WinWatt project-open accelerator path")
    parser.add_argument("--timeout", type=float, default=5.0, help="How long to wait for the dialog after sending the configured accelerator")
    parser.add_argument("--step-delay", type=float, default=0.15, help="Delay between accelerator key steps when the mode uses multiple keypresses")
    parser.add_argument("--accelerator-mode", default=PROJECT_OPEN_ACCELERATOR_MODE, choices=["alt_f_p", "ctrl_o"], help="Project-open accelerator mode to send")
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH, help="Path of the JSON result log file")
    args = parser.parse_args()

    raise SystemExit(run_smoke(timeout_s=args.timeout, step_delay_s=args.step_delay, log_path=args.log_path, accelerator_mode=args.accelerator_mode))


if __name__ == "__main__":
    main()
