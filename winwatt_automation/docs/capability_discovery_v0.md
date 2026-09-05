# Capability Discovery v0

Discovery is a separate, bounded sandbox capability. It is not production
automation and it is not deterministic verification.

```text
DiscoveryGoal (fixed operation)
  -> disposable sandbox project
  -> existing room/UIA navigation
  -> catalog/list/detail observations
  -> DiscoveryEvidence (deterministic=false)
  -> CandidateCapability (status=hypothesis)
  -> STOP
```

The first and only supported operation is
`enumerate_room_boundary_structure_types`. It opens the existing room-boundary
selector through the previously mapped UIA route, reads captions from the live
catalog, selects each bounded candidate, observes the uncommitted detail form,
then closes it with Escape. It does not save or promote any capability.

Run only with an explicitly enabled desktop sandbox:

```powershell
$env:WINWATT_E2E = "1"
.\.venv-win32\Scripts\winwatt.exe discover room-boundary-types --json
```

Limits default to 24 UI actions and 90 seconds. It refuses project settings,
irreversible dialogs, and non-sandbox saves by design. A foreground/focus
failure becomes a persisted `blocked_before_catalog` result rather than an
unbounded retry or an unaudited action.

Candidate concept IDs are derived from the observed captions; no boundary-type
list is hardcoded. A later controlled experiment must still save, reopen, and
read back a value before `verified` is possible.
