"""Local executable identity and isolated mapping campaigns (no UI side effects)."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import shutil
import struct
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_EXE = r"C:\Program Files (x86)\Bausoft\WinWatt gólya\WinWatt32.exe"
IDENTITY_FIELDS = ('exe_sha256', 'file_version', 'product_version', 'architecture', 'resources')


def resolve_executable(explicit: str | Path | None = None) -> Path:
    return Path(explicit or os.getenv('WWA_WINWATT_EXE_PATH') or DEFAULT_EXE).resolve()


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pe_architecture(path: Path) -> str:
    with path.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError(f'Not a Windows executable: {path}')
        stream.seek(60)
        offset = stream.read(4)
        if len(offset) != 4:
            raise ValueError('Truncated DOS header')
        stream.seek(struct.unpack('<I', offset)[0])
        header = stream.read(6)
        if len(header) != 6 or header[:4] != b'PE\x00\x00':
            raise ValueError('Invalid PE header')
        machine = struct.unpack('<H', header[4:])[0]
        if machine not in {0x14c, 0x8664, 0xaa64}:
            raise ValueError(f'Unsupported PE architecture: {machine:#x}')
        return {0x14c: 'x86', 0x8664: 'x64', 0xaa64: 'arm64'}[machine]


def windows_versions(path: Path) -> tuple[str, str]:
    """Read the fixed version resource without loading or executing the EXE."""
    if os.name != 'nt':
        raise OSError('Windows version resource capture requires Windows')
    from ctypes import wintypes
    version = ctypes.WinDLL('version', use_last_error=True)
    version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    version.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    version.GetFileVersionInfoW.restype = wintypes.BOOL
    version.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
    version.VerQueryValueW.restype = wintypes.BOOL
    size = version.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(str(path), 0, size, buffer):
        raise ctypes.WinError(ctypes.get_last_error())
    pointer, length = ctypes.c_void_p(), wintypes.UINT()
    if not version.VerQueryValueW(buffer, '\\', ctypes.byref(pointer), ctypes.byref(length)) or length.value < 52:
        raise ValueError('Missing fixed version info')
    values = struct.unpack('<13I', ctypes.string_at(pointer, 52))
    if values[0] != 0xFEEF04BD:
        raise ValueError('Invalid version resource signature')
    def dotted(high: int, low: int) -> str:
        return '.'.join(str(v) for v in (high >> 16, high & 65535, low >> 16, low & 65535))
    return dotted(values[2], values[3]), dotted(values[4], values[5])


def profile_id(profile: dict[str, Any]) -> str:
    identity = {key: profile[key] for key in IDENTITY_FIELDS}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return 'winwatt_' + digest[:24]


def capture_profile(exe: Path, resources: list[Path] | None = None) -> dict[str, Any]:
    exe = exe.resolve(strict=True)
    architecture = pe_architecture(exe)
    file_version, product_version = windows_versions(exe)
    # Record application-side DLL/XML/INI files by relative name, not machine path.
    inputs = {p.resolve() for p in exe.parent.iterdir()
              if p.is_file() and p.suffix.lower() in {'.dll', '.xml', '.ini'}}
    inputs.update(p.resolve(strict=True) for p in (resources or []))
    resource_hashes = {}
    for path in sorted(inputs):
        name = path.relative_to(exe.parent).as_posix() if path.is_relative_to(exe.parent) else str(path)
        resource_hashes[name] = sha256(path)
    result = {
        'schema_version': 1, 'exe_path': str(exe), 'exe_sha256': sha256(exe),
        'file_version': file_version, 'product_version': product_version,
        'architecture': architecture, 'resources': resource_hashes,
        'extra_resource_paths': [str(p.resolve()) for p in (resources or [])],
        'captured_at': datetime.now(timezone.utc).isoformat(),
        'environment': {'python': sys.version, 'python_bits': struct.calcsize('P') * 8,
                        'machine': platform.node(), 'platform': platform.platform()},
        'ui_verification': {'edition': None, 'enabled_modules': None, 'status': 'pending'},
        'scope': 'Executable and listed resources only; UI modules/licence/catalog completeness unverified.',
    }
    result['profile_id'] = profile_id(result)
    return result


def compare_profiles(expected: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    if expected.get('schema_version') != 1 or current.get('schema_version') != 1:
        raise ValueError('Unsupported profile schema')
    for profile in (expected, current):
        if profile_id(profile) != profile.get('profile_id'):
            raise ValueError('Profile identity does not match its recorded contents')
    changes = {key: {'expected': expected[key], 'current': current[key]}
               for key in IDENTITY_FIELDS if expected[key] != current[key]}
    return {'binary_resources_match': not changes, 'changes': changes,
            'ui_revalidation_required': True,
            'note': 'Identity match alone does not verify UI capabilities or module availability.'}


def require_profile(expected_path: Path, exe: Path | None = None) -> dict[str, Any]:
    expected = json.loads(expected_path.read_text(encoding='utf-8'))
    current = capture_profile(exe or Path(expected['exe_path']),
                              [Path(p) for p in expected.get('extra_resource_paths', [])])
    report = compare_profiles(expected, current)
    if not report['binary_resources_match']:
        raise ValueError('WinWatt profile changed: ' + ', '.join(report['changes']))
    return current


def write_new_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def prepare_campaign(profile: dict[str, Any], root: Path, source_project: Path) -> Path:
    """Copy a seed project into a new run; never launch or mutate WinWatt."""
    if profile_id(profile) != profile.get('profile_id'):
        raise ValueError('Invalid profile identity')
    source_project = source_project.resolve(strict=True)
    if source_project.suffix.lower() != '.wwp':
        raise ValueError('Campaign seed must be a WWP project')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run = root.resolve() / profile['profile_id'] / (stamp + '_' + uuid.uuid4().hex[:12])
    run.mkdir(parents=True, exist_ok=False)
    sandbox = run / 'sandbox'
    sandbox.mkdir()
    target = sandbox / 'testwwp.wwp'
    shutil.copy2(source_project, target)
    write_new_json(run / 'version_profile.json', profile)
    phases = ['about_and_modules', 'building_root', 'building_tabs', 'conditional_fields',
              'field_roundtrips', 'calculation', 'certificate_package']
    write_new_json(run / 'campaign.json', {
        'schema_version': 1, 'profile_id': profile['profile_id'],
        'status': 'prepared_not_executed', 'seed_sha256': sha256(source_project),
        'sandbox_project': str(target), 'seed_source': str(source_project),
        'historical_policy': 'reference_only_no_verified_promotion',
        'tasks': [{'id': name, 'status': 'pending', 'evidence': []} for name in phases],
    })
    return run
