from __future__ import annotations

import argparse
import threading
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import scrolledtext

from winwatt_automation.controller import ControllerConfig, DevCycleController
from winwatt_automation.controller.gui_helpers import build_map_command, command_preview


class DevCycleGui:
    def __init__(self, controller: DevCycleController):
        self.controller = controller
        self.root = tk.Tk()
        self.root.title("WinWatt Dev Cycle Controller")
        self.root.geometry("900x600")

        self.python_var = tk.StringVar(value=self.controller.config.python_executable)
        self.safe_mode_var = tk.StringVar(value=self.controller.config.default_safe_mode)
        self.timeout_var = tk.StringVar(value=str(self.controller.config.default_timeout_seconds))
        self.goal_var = tk.StringVar(value="Stabilizálni a következő tesztkört")
        self.request_var = tk.StringVar(value="Adj következő minimális fejlesztői lépést")
        self.project_path_var = tk.StringVar(value="")
        self.extra_args_var = tk.StringVar(value="")

        self._build_ui()
        self._refresh_preview()

    def _build_ui(self) -> None:
        form = tk.Frame(self.root)
        form.pack(fill="x", padx=8, pady=8)

        self._add_row(form, "Python exe", self.python_var)
        self._add_row(form, "Safe mode", self.safe_mode_var)
        self._add_row(form, "Timeout sec", self.timeout_var)
        self._add_row(form, "Goal", self.goal_var)
        self._add_row(form, "Request", self.request_var)
        self._add_row(form, "Project path", self.project_path_var, browse=True)
        self._add_row(form, "Extra args", self.extra_args_var)

        preview_frame = tk.Frame(self.root)
        preview_frame.pack(fill="x", padx=8, pady=4)
        tk.Label(preview_frame, text="Map command preview:").pack(anchor="w")
        self.preview_label = tk.Label(preview_frame, justify="left", anchor="w", fg="#333")
        self.preview_label.pack(fill="x")

        actions = tk.Frame(self.root)
        actions.pack(fill="x", padx=8, pady=8)

        tk.Button(actions, text="Status", command=lambda: self._run_bg(self._status)).pack(side="left", padx=4)
        tk.Button(actions, text="Git pull", command=lambda: self._run_bg(self._pull)).pack(side="left", padx=4)
        tk.Button(actions, text="Prepare chat", command=lambda: self._run_bg(self._prepare_chat)).pack(side="left", padx=4)
        tk.Button(actions, text="Start WinWatt", command=lambda: self._run_bg(self._start_winwatt)).pack(side="left", padx=4)
        tk.Button(actions, text="Stop WinWatt", command=lambda: self._run_bg(self._stop_winwatt)).pack(side="left", padx=4)
        tk.Button(actions, text="Run map_full_program", command=lambda: self._run_bg(self._run_map)).pack(side="left", padx=4)
        tk.Button(actions, text="Open project + run", command=lambda: self._run_bg(self._open_project_and_run_map)).pack(side="left", padx=4)
        tk.Button(actions, text="Cycle map_full_program", command=lambda: self._run_bg(self._cycle_map)).pack(side="left", padx=4)

        log_frame = tk.Frame(self.root)
        log_frame.pack(fill="both", expand=True, padx=8, pady=8)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap="word")
        self.log_text.pack(fill="both", expand=True)

        for var in (self.python_var, self.safe_mode_var, self.timeout_var, self.project_path_var, self.extra_args_var):
            var.trace_add("write", lambda *_: self._refresh_preview())

    def _add_row(self, parent: tk.Widget, label: str, variable: tk.StringVar, *, browse: bool = False) -> None:
        row = tk.Frame(parent)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=label, width=14, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        if browse:
            tk.Button(row, text="Browse…", command=lambda: self._browse_project_path(variable)).pack(side="left", padx=(6, 0))

    def _browse_project_path(self, variable: tk.StringVar) -> None:
        selected = filedialog.askopenfilename(title="Select WinWatt project")
        if selected:
            variable.set(selected)

    def _refresh_preview(self) -> None:
        command = build_map_command(
            python_executable=self.python_var.get().strip() or self.controller.config.python_executable,
            safe_mode=self.safe_mode_var.get().strip() or self.controller.config.default_safe_mode,
            project_path=self.project_path_var.get().strip() or None,
            extra_args=self.extra_args_var.get().strip() or None,
        )
        self.preview_label.config(text=command_preview(command))

    def _timeout(self) -> int:
        try:
            return max(1, int(self.timeout_var.get().strip()))
        except ValueError:
            return self.controller.config.default_timeout_seconds

    def _append(self, message: str) -> None:
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")

    def _append_threadsafe(self, message: str) -> None:
        self.root.after(0, lambda: self._append(message))

    def _run_bg(self, func) -> None:
        thread = threading.Thread(target=lambda: self._guarded(func), daemon=True)
        thread.start()

    def _guarded(self, func) -> None:
        try:
            func()
        except Exception as exc:  # pragma: no cover
            self._append_threadsafe(f"ERROR: {exc}")
            self.root.after(0, lambda: messagebox.showerror("Dev cycle GUI", str(exc)))

    def _status(self) -> None:
        payload = self.controller.repo_status()
        self._append_threadsafe("=== STATUS ===")
        for key, value in payload.items():
            self._append_threadsafe(f"{key}: {value}")

    def _pull(self) -> None:
        result = self.controller.git.pull()
        self._append_threadsafe(f"git pull rc={result.returncode}")
        self._append_threadsafe(result.stdout or result.stderr or "(no output)")

    def _prepare_chat(self) -> None:
        output = self.controller.prepare_chat(self.goal_var.get(), self.request_var.get())
        self._append_threadsafe(f"chat brief written: {output}")

    def _start_winwatt(self) -> None:
        result = self.controller.winwatt.start()
        self._append_threadsafe(result.message)

    def _stop_winwatt(self) -> None:
        result = self.controller.winwatt.stop(force=False)
        self._append_threadsafe(result.message)

    def _run_map(self) -> None:
        self.controller.runner.python_executable = self.python_var.get().strip() or self.controller.config.python_executable
        result = self.controller.run_script(
            "map_full_program",
            timeout_seconds=self._timeout(),
            safe_mode=self.safe_mode_var.get().strip() or self.controller.config.default_safe_mode,
            passthrough_args=self._map_passthrough_args(),
        )
        self._append_threadsafe(
            f"run status={result.status} elapsed={result.elapsed_seconds:.2f}s timed_out={result.timed_out} exit_code={result.exit_code}"
        )

    def _map_passthrough_args(self) -> list[str] | None:
        args: list[str] = []
        project_path = self.project_path_var.get().strip()
        if project_path:
            args.extend(["--project-path", project_path])
        if self.extra_args_var.get().strip():
            args.extend(self.extra_args_var.get().split())
        return args or None

    def _open_project_and_run_map(self) -> None:
        if not self.project_path_var.get().strip():
            self.root.after(0, lambda: messagebox.showwarning("Dev cycle GUI", "Adj meg egy project path értéket az automatikus projektnyitáshoz."))
            return
        self._append_threadsafe(f"Auto-run armed for project: {self.project_path_var.get().strip()}")
        self._run_map()

    def _cycle_map(self) -> None:
        self.controller.runner.python_executable = self.python_var.get().strip() or self.controller.config.python_executable
        result = self.controller.run_cycle(
            script_name="map_full_program",
            goal=self.goal_var.get(),
            concrete_request=self.request_var.get(),
            timeout_seconds=self._timeout(),
            safe_mode=self.safe_mode_var.get().strip() or self.controller.config.default_safe_mode,
            stop_winwatt_on_timeout=False,
        )
        self._append_threadsafe(
            f"cycle script={result.script_result.status} pull_rc={result.pull_result.returncode} chat={result.chat_brief_path}"
        )

    def run(self) -> None:
        self.root.mainloop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal Tk GUI for WinWatt dev-cycle tasks")
    parser.add_argument("--python", dest="python_executable", default=None, help="Override Python executable in GUI default")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = ControllerConfig.from_env()
    if args.python_executable:
        config.python_executable = args.python_executable

    gui = DevCycleGui(DevCycleController(config))
    gui.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
