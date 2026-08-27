"""Small local UI for selecting the next cumulative mapping scopes."""
from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from winwatt_automation.runtime_mapping.unified_mapping import PROJECT_ROOT, UNIFIED_ROOT
from winwatt_automation.scripts.run_scoped_rooms import SCOPES


PROJECT = PROJECT_ROOT / "data" / "runtime_maps" / "full_authorized_sandbox" / "20260826T123933Z" / "testwwp.wwp"


def main() -> int:
    root = tk.Tk()
    root.title("AutoWinWatt – feltérképezési területek")
    root.resizable(False, False)
    root.geometry("620x680+40+40")
    ttk.Label(root, text="Válaszd ki a következő célzott feltérképezési köröket.", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=18, pady=(18, 4))
    ttk.Label(root, text="A korábbi futások változatlanok maradnak; az új kör az egységes manifesthez kapcsolódik.", wraplength=480).pack(anchor="w", padx=18, pady=(0, 12))
    variables = {key: tk.BooleanVar(value=key in {"general", "winter", "summer"}) for key in SCOPES}
    menu_names = ["Fájl", "Jegyzékek", "Beállítások", "Súgó", "Szerkesztés", "Csoport", "Elem"]
    menu_vars = {name: tk.BooleanVar(value=False) for name in menu_names}
    full_frame = ttk.LabelFrame(root, text="Teljes WinWatt")
    full_frame.pack(fill="x", padx=18, pady=4)
    ttk.Checkbutton(full_frame, text=SCOPES["full_program"], variable=variables["full_program"]).pack(anchor="w", padx=12, pady=(7, 2))
    ttk.Label(full_frame, text="Fájl, Beállítások, Súgó, mind a 15 jegyzék, dinamikus Szerkesztés/Csoport/Elem menük és belső párbeszédablakok.\nMinden engedélyezett művelet új, eldobható sandbox-projektben fut.", wraplength=510).pack(anchor="w", padx=32, pady=(0, 7))
    main_frame = ttk.LabelFrame(root, text="Főablak és felsőmenük – külön kiválasztható")
    main_frame.pack(fill="x", padx=18, pady=4)
    ttk.Checkbutton(main_frame, text=SCOPES["main_window"], variable=variables["main_window"]).pack(anchor="w", padx=12, pady=4)
    menus = ttk.Frame(main_frame)
    menus.pack(anchor="w", padx=12, pady=(0, 6))
    for index, name in enumerate(menu_names):
        ttk.Checkbutton(menus, text=name, variable=menu_vars[name]).grid(row=index // 3, column=index % 3, sticky="w", padx=(0, 22), pady=2)
    frame = ttk.LabelFrame(root, text="Helyiségek – külön is kiválasztható, célzott ágak")
    frame.pack(fill="x", padx=18, pady=4)
    for key, label in SCOPES.items():
        if key == "full_program":
            continue
        ttk.Checkbutton(frame, text=label, variable=variables[key]).pack(anchor="w", padx=12, pady=4)
    status = ttk.Label(root, text=f"Projekt: {PROJECT.name}")
    status.pack(anchor="w", padx=18, pady=10)

    def start() -> None:
        selected = [key for key, variable in variables.items() if variable.get()]
        selected_menus = [name for name, variable in menu_vars.items() if variable.get()]
        if not selected and not selected_menus:
            messagebox.showwarning("Nincs kiválasztás", "Válassz legalább egy feltérképezési területet.")
            return
        command = [sys.executable, "-m", "winwatt_automation.scripts.run_scoped_rooms", "--project", str(PROJECT)]
        for key in selected:
            command.extend(("--scope", key))
        for name in selected_menus:
            command.extend(("--top-menu", name))
        subprocess.Popen(command, cwd=PROJECT_ROOT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        root.destroy()

    buttons = ttk.Frame(root)
    buttons.pack(fill="x", padx=18, pady=12)
    ttk.Button(buttons, text="Feltérképezés indítása", command=start).pack(side="right")
    ttk.Button(buttons, text="Mégse", command=root.destroy).pack(side="right", padx=(0, 8))
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
