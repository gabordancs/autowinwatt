# Room boundary structure classification v0

The boundary selector enumerates **concrete structure references** from the
current project/catalogue.  A caption is not treated as a semantic structure
kind.  Discovery therefore records two separate non-verified objects:

- `StructureReferenceCandidate`: one observed catalogue row, its source
  control, detail-form evidence and optional explicit category value;
- `StructureKindCandidate`: an evidence-backed provisional grouping of one or
  more references.

All records have `status=hypothesis`.  Discovery evidence is explicitly
non-deterministic and cannot promote a semantic capability to `verified`.

## Classification evidence order

1. An explicit native detail-form type/category field, when available.
2. The same detail window class plus the same control-layout fingerprint.
3. `unclassified` with low confidence when the detail form cannot be observed.

Display names are used only to select a bounded, variant-rich sample.  They are
never used to assign a reference to a structure kind.

## Safety and workflow

`winwatt discover classify-room-boundary-structures --json` is E2E-gated with
`WINWATT_E2E=1`.  It copies the source project to a session sandbox, opens the
known room boundary selector, selects a catalogue reference, opens its detail
form and closes it with `Esc`.  It finally closes the selector with `Esc`.

The observed, non-committing transition is:

```text
catalogue reference -> Felvesz... -> native boundary detail form -> Esc -> selector restored -> Esc
```

There is no project save and no verified promotion in this discovery flow.  The
default bounds are six representatives, 40 UI actions and 180 seconds.

`--reference "<observed catalogue caption>"` may be repeated to make a
targeted comparison sample from captions already seen in a prior discovery
result.  This is sampling input only, not a classification rule.

The smallest follow-up deterministic experiment is: select one reference from a
shared kind candidate, set only an already mapped safe field, confirm the
selector, native Save As in the sandbox, close/reopen, then read the resulting
boundary row/detail value back.  Only that round trip may establish a verified
capability.
