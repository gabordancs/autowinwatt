# ExperimentRunner v0

`ExperimentRunner` is a narrow sandbox-only bridge from a semantic experiment
to an existing verified service workflow. It is not a second automation engine.

## Safety boundary

An `ExperimentSpec` contains only a capability ID, entity, semantic from/to
values, and requested observations. Pydantic rejects extra fields, so it
cannot contain coordinates, raw key sequences, or arbitrary desktop actions.
The v0 whitelist contains only `room.area_m2`.

Every run first copies its source project to a timestamped sandbox directory.
It preserves the completed sandbox for evidence and replay; a later run gets a
new copy rather than mutating or deleting the earlier one.

## Reused primitives

| Runner primitive | Existing behaviour it calls |
| --- | --- |
| `prepare_sandbox_project()` | `RoomService.create_sandbox()` |
| `observe_current_state()` | records the copied sandbox baseline; an optional known-room lookup uses `RoomService.read_room()` |
| `execute_known_action()` | `RoomService.prepare_rooms()` with `RoomInput` |
| `save_project()` | `prepare_rooms()` evidence from native Save As |
| `reopen_project()` | `prepare_rooms()` close/reopen verification |
| `read_known_values()` | `room_values` UI readback evidence |
| `compare_expected_actual()` | deterministic numeric comparison |
| `reset_sandbox()` | preserves the evidence artifact; next run has a new sandbox |

The first vertical slice is `room.area_m2`. A room can be new in v0, therefore
the declared `from` value is provenance rather than a numeric precondition;
the deterministic numeric observation is the post-save/reopen UI readback.
Its result contains the expected
and actual value plus a deterministic `verification` evidence item. Only that
item can promote a semantic concept to `verified`.

## Run an E2E experiment

The normal test suite never starts WinWatt. The CLI and the E2E test both
require an explicit opt-in:

```powershell
$env:WINWATT_E2E = '1'
winwatt experiment run .\experiment.json
```

Example `experiment.json`:

```json
{
  "hypothesis_id": "hyp_room_area",
  "target_capability": "room.area_m2",
  "source_project": "C:/path/to/template.wwp",
  "change": {"entity": "MVP Nappali", "from": 28.4, "to": 31.7},
  "observe": ["ui_readback", "save_reopen"]
}
```

Output is JSON and includes the sandbox path, evidence, expected/actual values,
and `roundtrip_verified`.
