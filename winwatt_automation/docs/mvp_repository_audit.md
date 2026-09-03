# AutoWinWatt MVP repository audit

## Scope and evidence policy

This audit distinguishes source-level knowledge from live WinWatt proof. A
capability is **runtime-verified** only when a sandbox run has an artifact
showing the resulting UI state or persisted file. Static `Hungarian.xml` and
the UI parser describe the application; they are not a project XML adapter.

## Reused runtime infrastructure

| Capability | Implementation | Evidence / note |
| --- | --- | --- |
| Fresh process and project start | `runtime_mapping/program_mapper.py:prepare_fresh_winwatt_session` | Starts the native executable with a `.wwp` target and waits for a main-window snapshot. |
| Runtime state graph and screenshots | `runtime_mapping/room_deep_explorer.py` | State signature, state diff, menu snapshot, checkpoint/event log and replay paths are stored under `data/runtime_maps/`. |
| Stable Rooms catalog activation | `room_deep_explorer.py:_activate_rooms_catalog_fast` | Native `Jegyzékek` menu and the mapped Rooms catalog index; used by `RoomService`. |
| Room creation and reopening | `room_deep_explorer.py:_create_sandbox_room`, `open_sandbox_room` | Uses the verified native `Elem → Új elem/Módosítás` route and waits for the room form/list row. |
| Parent Building route | `room_deep_explorer.py:open_sandbox_building` | The room batch creates/reopens its required Building parent before room actions. |

## Proven room fields and locators

`services/room_service.py` combines window type, tab context, control type and
relative layout. It does not expose coordinates in domain models.

| Semantic field | Runtime route | Readback |
| --- | --- | --- |
| Name | Rooms list / `TRoomModifyForm` | list item after reopen |
| Floor area | General data tab, nearby native `TEdit` | UI readback |
| Height | General data tab, nearby native `TEdit` | UI readback |
| Winter temperature | Winter tab | UI readback |
| Summer design temperature | Summer tab | UI readback |
| External-wall X | `Szerkezetek… → Határoló szerkezetek → Külső fal` | reopens boundary detail and reads semantic X field |

Fresh runtime proof is retained in:

- `data/runtime_maps/mvp_e2e/external_wall_service_final_20260903T122340/operation_result.json`
- `data/runtime_maps/mvp_e2e/winter_temperature_20260903T123307/operation_result.json`
- `data/runtime_maps/mvp_e2e/summer_design_temp_20260903T123038/operation_result.json`
- `data/runtime_maps/full_authorized_sandbox/building_e2e_stable_20260903T132028/verification_result.json`

The last artifact proves a reopened Building plus three named rooms with one
external wall each and `X=1`.

## Persistence and verification

`services/winwatt_service.py:save_project_as` uses the native Save As command.
`RoomService.prepare_rooms` creates records in a sandbox copy, performs native
Save As, closes the project, then reopens and compares expected/actual values.
`services/verification_service.py` produces semantic evidence items rather
than treating a click as success.

The CLI command is `winwatt prepare-rooms INPUT.json`, implemented in
`cli/main.py`. It creates a time-stamped sandbox and writes an
`operation_result.json` report.

## Native XML status

The native commands are mapped in `live_ui/native_menu.py`:

| Command | Native ids | Current status |
| --- | --- | --- |
| `MainForm.XMLExportAction` | Fájl `(1, 9)` | Save dialog live-probed and cancelled; actual file-writing adapter implemented in `services/xml_native_service.py`, awaiting sandbox runtime proof. |
| `MainForm.XMLImportAction` | Fájl `(1, 10)` | Open dialog live-probed and cancelled; actual file-import adapter implemented in `services/xml_native_service.py`, awaiting sandbox runtime proof. |

`parser/xml_parser.py` parses the repository's `Hungarian.xml`, which is a UI
description/source artifact. It must not be confused with XML emitted by a
WinWatt project export. The latter is investigated only by native export,
semantic diff, import, and re-export in an isolated sandbox.

## Known gaps at audit time

The native XML adapter has completed a transport round-trip, but no room
property is automatically assigned `xml_import=verified`. The first
controlled experiment is recorded in `data/capabilities/xml_capabilities.json`:
`WinWatt32Room/Area` survives a native re-export as `11`, but the WinWatt room
editor still reads `10`; it is classified `unsafe`, with UI remaining the
preferred writer.
