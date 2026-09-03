"""Run one exact, approved Hungarian safe command."""

from __future__ import annotations

import argparse
import json

from winwatt_automation.commands.safe_runtime_commands import execute_safe_command


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a constrained safe WinWatt command")
    parser.add_argument("command", help="Exact approved Hungarian command")
    args = parser.parse_args()
    result = execute_safe_command(args.command)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
