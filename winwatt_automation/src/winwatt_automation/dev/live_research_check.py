"""Run the real bounded research path with secret-safe diagnostics."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_project_env() -> Path | None:
    """Shell environment wins; search only the checkout and its package root."""
    package_root = Path(__file__).resolve().parents[3]
    candidates = (package_root / ".env", package_root.parent / ".env")
    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=False)
            return path
    return None


def main() -> int:
    load_project_env()
    if not os.environ.get("OPENAI_API_KEY"):
        print("LIVE CHECK BLOCKED: OPENAI_API_KEY unavailable")
        return 2
    if os.environ.get("WINWATT_E2E") != "1":
        print("LIVE CHECK BLOCKED: WINWATT_E2E unavailable")
        return 2
    from winwatt_automation.cli.main import app
    # Typer's normal CLI path is intentionally reused; no mocked planner loop.
    app(args=["research", "run", "Tanuld meg, hogyan kell új szerkezetet létrehozni.", "--hint", "A Jegyzékek menüben van a Szerkezetek ablak. Meg kell nyitni a felső menüből. Új szerkezetet az Új elem gombbal lehet létrehozni, ezért ott kutakodj.", "--json"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
