"""Bounded local tab inventory using the existing Delphi mapping helpers.

Attach to an already open building editor. Does not create/delete records or
promote observed fields to verified write capabilities.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from winwatt_automation.version_profile import require_profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    args = parser.parse_args()
    run = args.campaign.resolve()
    profile = require_profile(run / 'version_profile.json')
    from pywinauto import Desktop
    from winwatt_automation.runtime_mapping.room_deep_explorer import state_signature, logical_state_hash
    from loguru import logger
    logger.remove()
    output = run / ('building_tabs_' + time.strftime('%Y%m%dT%H%M%S'))
    candidates = [w for w in Desktop(backend='uia').windows()
                  if w.class_name() == 'TBuildingModifyForm' and w.is_visible() and w.is_enabled()]
    if len(candidates) != 1:
        raise RuntimeError(f'Expected one building editor, found {len(candidates)}')
    window = candidates[0]
    # Match the live process executable against the captured identity.
    import win32api
    import win32process
    process = win32api.OpenProcess(0x410, False, window.process_id())
    try:
        actual_exe = win32process.GetModuleFileNameEx(process, 0)
    finally:
        process.Close()
    if Path(actual_exe).resolve() != Path(profile['exe_path']).resolve():
        raise RuntimeError('Editor belongs to a different executable')
    tabs = window.descendants(control_type='TabItem')
    names = [tab.window_text() for tab in tabs]
    if len(names) != len(set(names)):
        raise RuntimeError('Ambiguous tab names; inspect parent hierarchy before capture')
    output.mkdir(exist_ok=False)
    report = {'profile_id': profile['profile_id'], 'status': 'observed_only',
              'scope': 'top-level exposed tabs; conditional branches and field writes not verified',
              'tabs': [], 'errors': []}
    for index, name in enumerate(names):
        try:
            matches = [tab for tab in window.descendants(control_type='TabItem') if tab.window_text() == name]
            if len(matches) != 1:
                raise RuntimeError('Tab no longer uniquely available')
            matches[0].select()
            deadline = time.monotonic() + 4
            while not matches[0].is_selected() and time.monotonic() < deadline:
                time.sleep(0.1)
            if not matches[0].is_selected():
                raise RuntimeError('Tab selection not confirmed')
            time.sleep(0.6)
            signature = state_signature(window)
            # Delphi can expose several independent page controls. Preserve
            # the selected context and hidden native pages, not only captions.
            signature['selected_tabs'] = [t.window_text() for t in window.descendants(control_type='TabItem') if t.is_selected()]
            native = Desktop(backend='win32').window(handle=window.handle)
            signature['native_pages'] = [{'name': c.window_text(), 'visible': c.is_visible()}
                                         for c in native.descendants() if c.class_name() == 'TTabSheet']
            signature['native_choices'] = []
            for control in native.descendants():
                if control.is_visible() and 'ComboBox' in control.class_name():
                    try:
                        from pywinauto.controls.win32_controls import ComboBoxWrapper
                        combo = ComboBoxWrapper(control.handle)
                        signature['native_choices'].append({'control_id': combo.control_id(),
                                                            'values': combo.item_texts(), 'selected': combo.selected_index()})
                    except Exception as exc:
                        signature['native_choices'].append({'error': str(exc)})
            stem = f'tab_{index:02d}'
            (output / f'{stem}.json').write_text(json.dumps(signature, ensure_ascii=False, indent=2), encoding='utf-8')
            window.capture_as_image().save(str(output / f'{stem}.png'))
            report['tabs'].append({'name': name, 'snapshot': f'{stem}.json',
                                   'fingerprint': logical_state_hash(signature),
                                   'controls': len(signature['controls'])})
        except Exception as exc:
            report['errors'].append({'tab': name, 'error': str(exc)})
            break
        finally:
            (output / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if not names:
        report['errors'].append({'error': 'No exposed tabs; native Win32 fallback required'})
    (output / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
