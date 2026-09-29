"""Local, bounded energy-mode survey and orientation save/reopen experiment.

Always works on a newly copied WWP. Historical modes are diagnostic cases,
not recommendations about which calculation rules to apply to a certificate.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from winwatt_automation.version_profile import require_profile, sha256


def parse_angle(value: str) -> float:
    return float(value.strip().replace(',', '.'))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--skip-mode-survey', action='store_true', help='Run only the field roundtrip on a fresh copy')
    parser.add_argument('--angle', type=float, default=42.0, help='Exact requested angle; fractional changes are not silently tolerated')
    args = parser.parse_args()
    profile = require_profile(args.profile)
    import os
    import shutil
    from loguru import logger
    from pywinauto import Desktop
    from pywinauto.controls.common_controls import ListViewWrapper
    from pywinauto.controls.win32_controls import ComboBoxWrapper
    from winwatt_automation.live_ui.app_connector import get_main_window
    from winwatt_automation.runtime_mapping.room_deep_explorer import open_sandbox_building, state_signature
    from winwatt_automation.services.winwatt_service import WinWattService
    from winwatt_automation.workflows.safe_project_options_probe import _open_project_options, _find_project_options_dialog

    os.environ['WWA_WINWATT_EXE_PATH'] = profile['exe_path']
    output = args.output.resolve()
    source = args.source.resolve(strict=True)
    if source.suffix.lower() != '.wwp':
        raise ValueError('Source must be WWP')
    output.mkdir(parents=True, exist_ok=False)
    project = output / 'testwwp.wwp'
    shutil.copy2(source, project)
    (output / 'version_profile.json').write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding='utf-8')
    logger.remove()
    logger.add(str(output / 'runtime.log'), level='WARNING')
    report = {'profile_id': profile['profile_id'], 'source': str(source),
              'source_sha256': sha256(source), 'project': str(project),
              'status': 'running', 'modes': [], 'restoration': 'not_attempted'}
    def checkpoint():
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def button(window, name):
        native = Desktop(backend='win32').window(handle=window.handle).wrapper_object()
        choices = [c for c in native.descendants() if c.class_name() == 'TButton' and c.window_text() == name and c.is_visible()]
        if len(choices) != 1:
            raise RuntimeError(f'Ambiguous button: {name}')
        choices[0].click()
        time.sleep(.25)

    def open_editor():
        main = get_main_window()
        native = Desktop(backend='win32').window(handle=main.handle).wrapper_object()
        lists = [c for c in native.descendants() if c.class_name() == 'TListViewWithHeader' and c.is_visible()]
        if len(lists) != 1:
            raise RuntimeError('Expected one active Buildings list')
        listing = ListViewWrapper(lists[0].handle)
        rows = [i for i in range(listing.item_count()) if listing.get_item(i).text() == 'Building graph explorer']
        if len(rows) != 1:
            raise RuntimeError('Sandbox building is missing or ambiguous')
        listing.get_item(rows[0]).click_input(double=True)
        editor = Desktop(backend='uia').window(process=main.process_id(), class_name='TBuildingModifyForm')
        editor.wait('visible enabled', timeout=10)
        return editor.wrapper_object()

    def options():
        main = get_main_window()
        _open_project_options(main)
        window = _find_project_options_dialog(main.process_id(), timeout=10)
        if window is None:
            raise RuntimeError('Project options did not open')
        ui = Desktop(backend='uia').window(handle=window.handle).wrapper_object()
        tab = next(t for t in ui.descendants(control_type='TabItem') if t.window_text() == 'Energetika')
        tab.select()
        time.sleep(.3)
        candidates = []
        for control in window.descendants():
            if control.class_name() == 'TComboBox' and control.is_visible():
                combo = ComboBoxWrapper(control.handle)
                values = combo.item_texts()
                if any('9/2023' in text for text in values) and any('7/2006' in text for text in values):
                    candidates.append(combo)
        if len(candidates) != 1:
            raise RuntimeError('Calculation-mode combo is ambiguous')
        return window, candidates[0]

    def snapshot(editor, name):
        signature = state_signature(editor)
        native = Desktop(backend='win32').window(handle=editor.handle).wrapper_object()
        signature['native_pages'] = [c.window_text() for c in native.descendants() if c.class_name() == 'TTabSheet']
        signature['available_tabs'] = [t.window_text() for t in editor.descendants(control_type='TabItem') if t.is_visible()]
        editor.set_focus()
        time.sleep(.2)
        editor.capture_as_image().save(str(output / f'{name}.png'))
        (output / f'{name}.json').write_text(json.dumps(signature, ensure_ascii=False, indent=2), encoding='utf-8')
        return signature

    def orientation(editor):
        next(t for t in editor.descendants(control_type='TabItem') if t.window_text() == 'Általános adatok').select()
        time.sleep(.2)
        native = Desktop(backend='win32').window(handle=editor.handle).wrapper_object()
        edits = [c for c in native.descendants() if c.class_name() == 'TEdit' and c.is_visible() and c.is_enabled()]
        if len(edits) != 1:
            raise RuntimeError('General-tab orientation edit no longer unique')
        return edits[0]

    original_mode = None
    checkpoint()
    try:
        editor = open_sandbox_building(project_path=str(project))
        button(editor, 'Elvet')
        window, combo = options()
        values = combo.item_texts()
        original_mode = values[combo.selected_index()]
        report['original_mode'] = original_mode
        button(window, 'Elvet')
        for index, value in enumerate([] if args.skip_mode_survey else values):
            window, combo = options()
            combo.select(value)
            if combo.selected_text() != value:
                raise RuntimeError('Calculation mode selection did not stick')
            button(window, 'OK')
            editor = open_editor()
            data = snapshot(editor, f'mode_{index:02d}')
            report['modes'].append({'index': index, 'mode': value, 'available_tabs': data['available_tabs'],
                                    'snapshot': f'mode_{index:02d}.json'})
            checkpoint()
            button(editor, 'Elvet')
        window, combo = options()
        combo.select(original_mode)
        button(window, 'OK')
        report['restoration'] = 'original_mode_selected'
        editor = open_editor()
        edit = orientation(editor)
        original_angle = edit.window_text()
        expected = args.angle
        if parse_angle(original_angle) == expected:
            raise ValueError('Choose an angle different from the source value')
        edit.set_edit_text(str(expected).replace('.', ','))
        snapshot(editor, 'orientation_written')
        button(editor, 'OK')
        service = WinWattService()
        service.save_project()
        service.close_project_gracefully()
        saved_hash = sha256(project)
        # First pass through the established launcher; open_editor then requires
        # the saved record, and cannot silently recreate a missing building.
        from winwatt_automation.runtime_mapping.room_deep_explorer import open_sandbox_buildings
        open_sandbox_buildings(project_path=str(project))
        editor = open_editor()
        actual = orientation(editor).window_text()
        snapshot(editor, 'orientation_reopened')
        report['roundtrip'] = {'field': 'building.orientation_deg', 'before': original_angle,
                               'expected': expected, 'actual': actual, 'saved_sha256': saved_hash,
                               'passed': parse_angle(actual) == expected}
        # Restore the test angle and save so the next experiment has the baseline.
        orientation(editor).set_edit_text(original_angle)
        button(editor, 'OK')
        service.save_project()
        window, combo = options()
        report['mode_after_reopen'] = combo.selected_text()
        button(window, 'Elvet')
        report['source_unchanged'] = sha256(source) == report['source_sha256']
        report['status'] = 'passed' if report['roundtrip']['passed'] and report['source_unchanged'] and report['mode_after_reopen'] == original_mode else 'failed'
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = repr(exc)
        # Preserve the failing dialog and copied project for diagnosis; never
        # claim an automatic restore happened after an unknown UI transition.
    finally:
        checkpoint()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
