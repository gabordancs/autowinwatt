"""Manage the local gap-driven reconstruction/mapping state machine."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from winwatt_automation.certificates.adaptive_cycle import (
    acquire_ui_lease,
    initialize_cycle,
    load_cycle,
    next_action,
    record_gap,
    record_gap_result,
    release_ui_lease,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--certificate-id", required=True)
    init.add_argument("--profile-id", required=True)
    init.add_argument("--project", required=True, type=Path)
    init.add_argument("--checkpoint", required=True, type=Path)
    add = commands.add_parser("add-gap")
    add.add_argument("--gap", required=True, type=Path)
    resolve = commands.add_parser("resolve-gap")
    resolve.add_argument("--gap-id", required=True)
    resolve.add_argument("--result", required=True)
    resolve.add_argument("--evidence", action="append", default=[])
    lease = commands.add_parser("acquire-ui")
    lease.add_argument("--owner", required=True)
    lease.add_argument("--pid", required=True, type=int)
    release = commands.add_parser("release-ui")
    release.add_argument("--owner", required=True)
    commands.add_parser("status")
    args = parser.parse_args()

    if args.command == "init":
        state = initialize_cycle(
            args.workspace, certificate_id=args.certificate_id,
            profile_id=args.profile_id, project=args.project,
            reconstruction_checkpoint=args.checkpoint,
        )
    elif args.command == "add-gap":
        state = record_gap(args.workspace, json.loads(args.gap.read_text(encoding="utf-8")))
    elif args.command == "resolve-gap":
        state = record_gap_result(
            args.workspace, gap_id=args.gap_id, result=args.result, evidence=args.evidence,
        )
    elif args.command == "acquire-ui":
        state = acquire_ui_lease(args.workspace, owner=args.owner, pid=args.pid)
    elif args.command == "release-ui":
        state = release_ui_lease(args.workspace, owner=args.owner)
    else:
        state = load_cycle(args.workspace)
    print(json.dumps({"state": state, "next_action": next_action(state)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
