# Learning Loop v1

Learning Loop v1 proves that AutoWinWatt can acquire a previously unseeded
capability, not merely retain an old mapping record.

```text
unknown → hypothesis → experimented → verified / rejected
```

The first target is `room.boundary.external_wall.x_m`. It is intentionally not
imported from `room_capabilities.json`. A `Hypothesis` creates an unverified
concept/capability record. Storing an experiment links the hypothesis,
experiment ID, concept, capability, and evidence in both directions through
`get_hypothesis_experiments()` and `get_concept_hypotheses()`.

`KnowledgeStore.promote_to_verified()` additionally requires that the stored
experiment has the same target capability as the concept and as its hypothesis,
and that it has succeeded with a deterministic verification record after a
save/reopen round trip.

The experiment handler registry contains only semantic handlers. The external
wall handler calls the existing `RoomService.prepare_rooms()` route with a
new sandbox room, its required valid 10 m² room area, and
`external_wall_x_m=1.37`; it neither emits coordinates nor raw key sequences.

```powershell
winwatt knowledge show room.boundary.external_wall.x_m
winwatt knowledge hypothesize room.boundary.external_wall.x_m hyp_wall_x "External-wall X in metres" --confidence 0.72
$env:WINWATT_E2E = '1'
winwatt experiment run .\external_wall_x_experiment.json
winwatt knowledge show room.boundary.external_wall.x_m
```
