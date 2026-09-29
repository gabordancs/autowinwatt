"""Read-only version capture/check and isolated mapping campaign preparation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from winwatt_automation.version_profile import (
    capture_profile, compare_profiles, prepare_campaign, resolve_executable, write_new_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path)
    parser.add_argument('--resource', action='append', type=Path, default=[])
    sub = parser.add_subparsers(dest='command', required=True)
    capture = sub.add_parser('capture')
    capture.add_argument('--output', required=True, type=Path)
    check = sub.add_parser('check')
    check.add_argument('--against', required=True, type=Path)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--root', required=True, type=Path)
    prepare.add_argument('--project', required=True, type=Path)
    args = parser.parse_args()
    try:
        expected = None
        if args.command == 'check':
            expected = json.loads(args.against.read_text(encoding='utf-8'))
        exe = resolve_executable(args.exe or (expected['exe_path'] if expected else None))
        resources = args.resource or ([Path(p) for p in expected.get('extra_resource_paths', [])] if expected else [])
        current = capture_profile(exe, resources)
        if args.command == 'check':
            report = compare_profiles(expected, current)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report['binary_resources_match'] else 2
        if args.command == 'capture':
            write_new_json(args.output, current)
            print(json.dumps(current, ensure_ascii=False, indent=2))
        else:
            run = prepare_campaign(current, args.root, args.project)
            print(json.dumps({'run': str(run), 'profile_id': current['profile_id'],
                              'status': 'prepared_not_executed'}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
