from __future__ import annotations

import argparse
import json
from pathlib import Path
import tkinter as tk


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Show a non-blocking progress HUD for runtime mapping")
    parser.add_argument("--status-file", required=True)
    parser.add_argument("--refresh-ms", type=int, default=700)
    return parser


def _read_status(path: Path) -> dict:
    if not path.exists():
        return {"state": "waiting", "message": "Waiting for mapper status…", "updated_at": ""}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"state": "warning", "message": "Could not parse mapper status file.", "updated_at": ""}


def _apply_non_activating_window(root: tk.Tk) -> None:
    if root.tk.call("tk", "windowingsystem") != "win32":
        return
    try:
        import ctypes

        hwnd = root.winfo_id()
        user32 = ctypes.windll.user32
        gwl_exstyle = -20
        ws_ex_toolwindow = 0x00000080
        ws_ex_topmost = 0x00000008
        ws_ex_noactivate = 0x08000000
        current = user32.GetWindowLongW(hwnd, gwl_exstyle)
        user32.SetWindowLongW(hwnd, gwl_exstyle, current | ws_ex_toolwindow | ws_ex_topmost | ws_ex_noactivate)
        user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
    except Exception:
        return


def main() -> int:
    args = _build_parser().parse_args()
    status_path = Path(args.status_file)

    root = tk.Tk()
    root.title("WinWatt mapper status")
    root.geometry("420x120+20+20")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    state_var = tk.StringVar(value="waiting")
    message_var = tk.StringVar(value="Waiting for mapper status…")
    updated_var = tk.StringVar(value="")

    frame = tk.Frame(root, padx=12, pady=10)
    frame.pack(fill="both", expand=True)
    tk.Label(frame, text="WinWatt mapper állapot", font=("Segoe UI", 12, "bold")).pack(anchor="w")
    tk.Label(frame, textvariable=state_var, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 0))
    tk.Label(frame, textvariable=message_var, justify="left", wraplength=390).pack(anchor="w", pady=(4, 0))
    tk.Label(frame, textvariable=updated_var, justify="left", fg="#666666").pack(anchor="w", pady=(6, 0))

    root.update_idletasks()
    _apply_non_activating_window(root)

    def refresh() -> None:
        payload = _read_status(status_path)
        state = str(payload.get("state") or "unknown")
        state_var.set(f"Állapot: {state}")
        message_var.set(str(payload.get("message") or ""))
        updated_var.set(f"Frissítve: {payload.get('updated_at') or 'n/a'}")
        if state in {"finished", "failed"}:
            root.after(max(3000, args.refresh_ms), root.destroy)
            return
        root.after(args.refresh_ms, refresh)

    root.after(0, refresh)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
