# NavigationKnowledge / UI route graph

`data/knowledge/navigation_knowledge.json` is the compact, persistent route
memory used between WinWatt research sessions.  It is deliberately separate
from raw `runtime_maps`: the planner receives only goal-relevant normalized
states, transitions and safe navigation capabilities.

## Evidence levels

- Legacy mapper and unified-exploration snapshots import as `observed` only.
- Research `before -> executed action -> after` observations upsert a graph
  edge automatically. Repeated matching results become `replayed`.
- A transition becomes `verified` only when an already registered deterministic
  native navigation handler proves its expected post-state.
- A post-action fingerprint mismatch makes that edge `stale`; stale and
  `rejected` edges cannot be selected by route search.

## Import and retrieval

Run once (or after adding mapping archives):

```powershell
python -m winwatt_automation.scripts.import_navigation_knowledge
```

The importer deduplicates by state fingerprint, preserves source provenance,
and creates an edge only where an old research audit contains both a before and
an after snapshot plus an executed action. It does not invent routes from menu
snapshots alone.

`ResearchPlanner.build_context()` retrieves a small goal/state-specific
`navigation_knowledge` summary and derives
`known_safe_navigation_capabilities` from verified graph edges. The executor
still owns the narrow deterministic handler registry.

## Runtime behavior

Every successful navigation or identity-based UI transition is captured and
upserted as:

```text
NavigationState -> NavigationTransition -> NavigationState
```

The resulting state is catalogued before the next planner call. Route search
uses weighted BFS: `verified`, then `replayed`, then `observed` edges. A replay
mismatch stops the replay and leaves subsequent exploration at the actual UI
state.
