"""A non-activating, continuously visible progress indicator for deep runs."""
from __future__ import annotations

import argparse
import ctypes
import json
import time
from pathlib import Path


def _snapshot(output_dir: Path) -> dict[str, int | bool]:
    try:
        progress = output_dir / "progress.json"
        if progress.exists():
            return json.loads(progress.read_text(encoding="utf-8"))
        graph = json.loads((output_dir / "graph.checkpoint.json").read_text(encoding="utf-8"))
        queue = json.loads((output_dir / "queue.checkpoint.json").read_text(encoding="utf-8"))
        return {"states": len(graph.get("states") or []), "edges": len(graph.get("edges") or []),
                "failures": len(graph.get("failures") or []), "queue": len(queue), "complete": bool(graph.get("complete"))}
    except (OSError, json.JSONDecodeError):
        return {"states": 0, "edges": 0, "failures": 0, "queue": 0, "complete": False}


def _eta_text(previous: dict[str, int | bool] | None, current: dict[str, int | bool], elapsed_s: float) -> str:
    if current.get("complete"):
        return "Hátralévő idő: elkészült"
    if previous is None:
        return "Hátralévő idő: becslés az első 5 perc után"
    completed = int(previous["queue"]) - int(current["queue"])
    if completed <= 0 or elapsed_s <= 0:
        return "Hátralévő idő: az ágak még bővülnek"
    seconds = int(int(current["queue"]) * elapsed_s / completed)
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"Hátralévő idő: kb. {hours} óra {minutes} perc"


def _show_non_activating(output_dir: Path, interval_seconds: int) -> None:
    # tkinter is independent of WinWatt's UIA tree.  The native ShowWindow
    # call makes the form visible without giving it keyboard focus.
    import tkinter as tk

    root = tk.Tk()
    root.title("AutoWinWatt – feltérképezés")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.geometry("360x175+30+30")
    text = tk.StringVar()
    tk.Label(root, textvariable=text, justify="left", padx=18, pady=14, font=("Segoe UI", 10)).pack()
    previous: dict[str, int | bool] | None = None
    previous_at = time.monotonic()

    def refresh() -> None:
        nonlocal previous, previous_at
        current = _snapshot(output_dir)
        now = time.monotonic()
        eta = _eta_text(previous, current, now - previous_at)
        text.set(
            "Helyiségek feltérképezése fut\n\n"
            f"Állapotok: {current['states']}    Ágak: {current['edges']}\n"
            f"Várólista: {current['queue']}    Hibák: {current['failures']}\n\n{eta}\n"
            "Frissítés: 5 percenként"
        )
        previous, previous_at = current, now
        root.after(max(1, interval_seconds) * 1000, refresh)

    root.update_idletasks()
    ctypes.windll.user32.ShowWindow(root.winfo_id(), 4)  # SW_SHOWNOACTIVATE
    refresh()
    root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--interval-seconds", type=int, default=300)
    # Retained for CLI compatibility with earlier runs; visibility is now continuous.
    parser.add_argument("--visible-seconds", type=int, default=0)
    args = parser.parse_args()
    _show_non_activating(args.output_dir, args.interval_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
