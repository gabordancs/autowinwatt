"""Build a portable, read-only union index; never promote historical UI routes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


def consolidate(root: Path) -> dict:
    root = root.resolve()
    artifacts: dict = {}
    errors = []
    profiles: Counter = Counter()
    summaries = {}
    allowed = {'.json', '.jsonl', '.md', '.txt', '.xml', '.png'}
    for folder in ('runtime_maps', 'snapshots', 'knowledge', 'capabilities', 'research', 'raw', 'parsed'):
        for path in sorted((root / 'data' / folder).rglob('*')):
            if not path.is_file() or path.is_symlink() or path.suffix.lower() not in allowed:
                continue
            if not path.resolve().is_relative_to(root):
                continue
            relative = path.relative_to(root).as_posix()
            try:
                data = path.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                entry = artifacts.setdefault(digest, {'bytes': len(data), 'sources': []})
                entry['sources'].append(relative)
                if path.suffix.lower() == '.json':
                    raw = json.loads(data)
                    text = data.decode('utf-8-sig')
                    profiles.update(set(re.findall(r'C:\\\\Users\\\\([^\\"/]+)', text)))
                    if isinstance(raw, dict):
                        sizes = {key: len(raw[key]) for key in ('states', 'edges', 'transitions', 'failures')
                                 if isinstance(raw.get(key), (dict, list))}
                        if sizes:
                            summaries[relative] = sizes
            except (OSError, ValueError, UnicodeError) as exc:
                errors.append({'source': relative, 'error': str(exc)})
    manifest = root / 'data/knowledge/global_mapping/import_manifest.json'
    references = []
    if manifest.exists():
        for source in json.loads(manifest.read_text(encoding='utf-8-sig')):
            portable = source.replace('\\', '/')
            suffix = portable.split('/winwatt_automation/', 1)[-1]
            candidate = root / suffix
            available = candidate.resolve().is_relative_to(root) and candidate.is_file()
            references.append({'original': source, 'relative': suffix, 'available': available})
    return {
        'schema_version': 1,
        'policy': 'reference_union_only; historical_unverified; no_runtime_activation',
        'machine_identity': 'Profile names are provenance hints, not verified machine identities.',
        'version_policy': '9_60 in a path is a hint; no artifact is verified for the new executable.',
        'artifact_count': sum(len(a['sources']) for a in artifacts.values()),
        'unique_content_count': len(artifacts),
        'profile_hints_by_json_file': dict(profiles),
        'historical_references': references,
        'graph_summaries': summaries,
        'artifacts_by_sha256': artifacts,
        'errors': errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.output.resolve().is_relative_to(root / 'data'):
        parser.error('Output must be outside data/ to avoid indexing generated output.')
    result = consolidate(root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('artifact_count', 'unique_content_count', 'profile_hints_by_json_file', 'errors')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
