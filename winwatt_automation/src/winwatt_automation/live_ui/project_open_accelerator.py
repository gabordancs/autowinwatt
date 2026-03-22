from __future__ import annotations

import time
from typing import Any

PROJECT_OPEN_ACCELERATOR_MODE = "ctrl_o"
PROJECT_OPEN_ACCELERATOR_MODES: dict[str, tuple[tuple[str, str], ...]] = {
    "alt_f_p": (("%", "ALT"), ("F", "F"), ("P", "P")),
    "ctrl_o": (("^o", "CTRL+O"),),
}


def project_open_accelerator_sequence(mode: str = PROJECT_OPEN_ACCELERATOR_MODE) -> list[str]:
    if mode not in PROJECT_OPEN_ACCELERATOR_MODES:
        raise ValueError(f"Unsupported project open accelerator mode: {mode}")
    return [label for _, label in PROJECT_OPEN_ACCELERATOR_MODES[mode]]


def send_project_open_accelerator(*, mode: str = PROJECT_OPEN_ACCELERATOR_MODE, step_delay_s: float = 0.05) -> dict[str, Any]:
    from pywinauto import keyboard

    if mode not in PROJECT_OPEN_ACCELERATOR_MODES:
        raise ValueError(f"Unsupported project open accelerator mode: {mode}")

    sequence: list[str] = []
    for index, (keys, label) in enumerate(PROJECT_OPEN_ACCELERATOR_MODES[mode]):
        keyboard.send_keys(keys)
        sequence.append(label)
        if index < len(PROJECT_OPEN_ACCELERATOR_MODES[mode]) - 1:
            time.sleep(step_delay_s)

    return {
        "project_open_method": mode,
        "sequence": sequence,
    }
