from __future__ import annotations

import json
import struct
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

from winwatt_automation.version_profile import (
    compare_profiles, pe_architecture, prepare_campaign, profile_id, sha256, write_new_json,
)


def sample(**changes):
    result = dict(schema_version=1, exe_sha256='a' * 64, file_version='9.60.0.0',
                  product_version='1.0.0.0', architecture='x86', resources={'catalog.xml': 'b' * 64})
    result.update(changes)
    result['profile_id'] = profile_id(result)
    return result


class VersionProfileTests(unittest.TestCase):
    def test_binary_change_even_with_identical_version(self):
        report = compare_profiles(sample(), sample(exe_sha256='c' * 64))
        self.assertFalse(report['binary_resources_match'])
        self.assertIn('exe_sha256', report['changes'])

    def test_resource_change_requires_new_identity(self):
        self.assertFalse(compare_profiles(sample(), sample(resources={}))['binary_resources_match'])

    def test_machine_paths_do_not_affect_identity(self):
        self.assertTrue(compare_profiles(sample(exe_path='C:/one'), sample(exe_path='D:/two'))['binary_resources_match'])

    def test_tampered_profile_rejected(self):
        modified = sample()
        modified['exe_sha256'] = 'f' * 64
        with self.assertRaises(ValueError):
            compare_profiles(modified, sample())

    def test_architecture_and_invalid_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'app.exe'
            data = bytearray(134)
            data[:2] = b'MZ'
            struct.pack_into('<I', data, 60, 128)
            data[128:134] = b'PE\0\0' + struct.pack('<H', 0x14c)
            path.write_bytes(data)
            self.assertEqual(pe_architecture(path), 'x86')
            path.write_bytes(b'MZ')
            with self.assertRaises(ValueError):
                pe_architecture(path)

    def test_campaign_isolated_preserves_seed_and_marks_pending(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            seed = root / 'original.wwp'
            seed.write_bytes(b'seed project')
            before = sha256(seed)
            # Windows clock resolution can give consecutive calls exactly the
            # same timestamp; uniqueness must not depend on clock progress.
            with patch('winwatt_automation.version_profile.datetime') as clock:
                clock.now.return_value = datetime(2026, 9, 29, tzinfo=timezone.utc)
                runs = [prepare_campaign(sample(), root / 'runs', seed) for _ in range(2)]
            self.assertNotEqual(*runs)
            self.assertEqual(sha256(seed), before)
            manifest = json.loads((runs[0] / 'campaign.json').read_text())
            self.assertTrue(all(t['status'] == 'pending' for t in manifest['tasks']))
            self.assertEqual(sha256(Path(manifest['sandbox_project'])), before)
            with self.assertRaises(FileExistsError):
                write_new_json(runs[0] / 'campaign.json', {})


if __name__ == '__main__':
    unittest.main()
