# Semantic Knowledge Layer v0

The Semantic Knowledge Layer turns already observed WinWatt behaviour into a
small, local, queryable knowledge record. It does not drive the desktop UI and
does not infer that a field is safe merely from a label or a heuristic.

## Reused implementation

| Need | Existing implementation reused |
| --- | --- |
| Runtime state/control/action/transition observations | `runtime_mapping/program_mapper.py`, `runtime_mapping/room_deep_explorer.py` |
| Sandbox project copies | `services/winwatt_service.py:WinWattService.create_sandbox()` |
| Semantic room action | `services/room_service.py:RoomService` |
| Save/reopen | `WinWattService.save_project_as()` and `close_project_gracefully()` |
| UI readback verification | `RoomService.verify_rooms()` and `VerificationService` |
| Existing proven capability evidence | `data/capabilities/room_capabilities.json` |

This sprint adds only `knowledge/models.py` and `knowledge/store.py`. The store
is a JSON file under `data/knowledge/knowledge_store.json`; it deliberately is
not a graph database.

## Status and evidence rule

The explicit statuses are `unknown`, `hypothesis`, `experimented`, `verified`,
and `rejected`. `Hypothesis` rejects `verified` at model validation. More
importantly, `KnowledgeStore.promote_to_verified()` requires all of:

1. a successful experiment;
2. a successful save/reopen round-trip; and
3. at least one deterministic `verification` evidence reference.

Therefore an LLM, a guessed label, or a heuristic can at most create a
`hypothesis`. The initial `room.area_m2` record is imported as verified only
because the existing capability registry already names a save/reopen evidence
file and marks UI read, UI write, and roundtrip verification as verified.

## Data flow

```text
raw mapping
    ↓
observations
    ↓
Semantic Knowledge Layer
    ↓
hypothesis
    ↓
ExperimentRunner
    ↓
WinWatt sandbox
    ↓
verification
    ↓
verified knowledge
```

## Local API

`KnowledgeStore` provides `search_concepts`, `get_concept`,
`get_capability`, `get_state_evidence`, `get_transition_evidence`,
`store_hypothesis`, `store_experiment_result`, and `promote_to_verified`.

The CLI exposes machine-readable JSON:

```powershell
winwatt knowledge show room.area_m2
winwatt knowledge search room
```
