from __future__ import annotations

import argparse
import json
from pathlib import Path

from winwatt_automation.controller import ControllerConfig, DevCycleController


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local developer cycle controller for WinWatt automation")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show repo + runlog status")
    sub.add_parser("pull", help="Run git pull")

    prep = sub.add_parser("prepare-chat", help="Generate ChatGPT-ready brief")
    prep.add_argument("--goal", default="Stabilizálni a következő tesztkört")
    prep.add_argument("--request", default="Adj következő minimális fejlesztői lépést")

    sub.add_parser("start-winwatt", help="Start WinWatt process")
    stop = sub.add_parser("stop-winwatt", help="Stop WinWatt process")
    stop.add_argument("--force", action="store_true")

    run = sub.add_parser("run", help="Run a repo script with timeout")
    run.add_argument("script")
    run.add_argument("--safe-mode", default=None, choices=["safe", "hybrid", "caution", "blocked"])
    run.add_argument("--timeout", type=int, default=None)
    run.add_argument("script_args", nargs=argparse.REMAINDER)

    cycle = sub.add_parser("cycle", help="Run pull -> status -> start -> script -> prepare-chat")
    cycle.add_argument("script")
    cycle.add_argument("--goal", default="Stabilizálni a következő tesztkört")
    cycle.add_argument("--request", default="Adj következő minimális fejlesztői lépést")
    cycle.add_argument("--safe-mode", default=None, choices=["safe", "hybrid", "caution", "blocked"])
    cycle.add_argument("--timeout", type=int, default=None)
    cycle.add_argument("--stop-winwatt-on-timeout", action="store_true")

    add = sub.add_parser("add", help="Run git add")
    add.add_argument("target", default=".", nargs="?")

    commit = sub.add_parser("commit", help="Run git commit")
    commit.add_argument("-m", "--message", required=True)

    sub.add_parser("push", help="Run git push")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = ControllerConfig.from_env()
    controller = DevCycleController(config)

    if args.command == "status":
        print(json.dumps(controller.repo_status(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "pull":
        result = controller.git.pull()
        print(result.stdout or result.stderr)
        return 0 if result.ok else 1

    if args.command == "prepare-chat":
        output = controller.prepare_chat(goal=args.goal, concrete_request=args.request)
        print(f"Chat brief written: {output}")
        return 0

    if args.command == "start-winwatt":
        result = controller.winwatt.start()
        print(result.message)
        return 0 if result.ok else 1

    if args.command == "stop-winwatt":
        result = controller.winwatt.stop(force=args.force)
        print(result.message)
        return 0 if result.ok else 1

    if args.command == "run":
        passthrough = args.script_args[1:] if args.script_args and args.script_args[0] == "--" else args.script_args
        result = controller.run_script(args.script, timeout_seconds=args.timeout, safe_mode=args.safe_mode, passthrough_args=passthrough)
        print(f"status={result.status} elapsed={result.elapsed_seconds:.2f}s timed_out={result.timed_out}")
        return 0 if result.status == "success" else 1

    if args.command == "cycle":
        cycle_result = controller.run_cycle(
            script_name=args.script,
            goal=args.goal,
            concrete_request=args.request,
            timeout_seconds=args.timeout,
            safe_mode=args.safe_mode,
            stop_winwatt_on_timeout=args.stop_winwatt_on_timeout,
        )
        print(f"git pull: {cycle_result.pull_result.returncode}")
        print(f"winwatt: {cycle_result.winwatt_start_result.message}")
        print(f"script: {cycle_result.script_result.status} ({cycle_result.script_result.elapsed_seconds:.2f}s)")
        print(f"chat brief: {cycle_result.chat_brief_path}")
        return 0 if cycle_result.script_result.status == "success" else 1

    if args.command == "add":
        result = controller.git.add(args.target)
        print(result.stdout or result.stderr)
        return 0 if result.ok else 1

    if args.command == "commit":
        result = controller.git.commit(args.message)
        print(result.stdout or result.stderr)
        return 0 if result.ok else 1

    if args.command == "push":
        result = controller.git.push()
        print(result.stdout or result.stderr)
        return 0 if result.ok else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
