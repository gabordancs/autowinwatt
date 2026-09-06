# Research Planner v0

Research Planner v0 turns a human research goal into a validated, dry-run
plan. It is not an autonomous automation agent and does not invoke WinWatt.

```text
Human goal
    |
    v
deterministic KnowledgeStore + manual retrieval
    |
    v
ResearchContext
    |
    v
provider-neutral LLM ResearchPlanner
    |
    v
validated structured ResearchPlan
    |
    v
proposed hypothesis / experiment
    |
    v
STOP (v0 never executes)
```

## Retrieval and evidence boundary

The planner sends only a bounded `ResearchContext`: relevant concepts and
capabilities, their statuses and evidence kinds, linked hypotheses and prior
experiment IDs, lexical manual excerpts with source/page/heading, and the
small whitelist of safe experiment handlers. It does not send the complete
knowledge store or PDF.

The models deliberately cannot express a `verified` status change. Before a
plan is returned, code checks that any `known_verified` entry was already
verified in the retrieved context. An executable `ExperimentSpec` is accepted
only when it validates under the existing schema and names an existing safe
handler. An unsupported proposal must not contain a spec.

Manual evidence remains documentation (`deterministic=false`) and can only
support a hypothesis. The existing Learning Loop verification gate remains the
sole path to verified knowledge.

## Provider configuration

The planner depends on a small `LLMProvider` protocol. `OpenAIProvider` is the
first implementation and reads its API key only from `OPENAI_API_KEY`; it
never writes a secret to the repository. The model defaults to `gpt-5.6-sol`
and can be overridden with `WINWATT_RESEARCH_MODEL` or the CLI option.

Alternatively, set `OPENAI_API_KEY` in the local `winwatt_automation/.env`
file. It is ignored by Git; `.env.example` is the safe committed template.

```powershell
$env:OPENAI_API_KEY = "..." # only for the current shell
.\.venv-win32\Scripts\winwatt.exe research plan "Tanuld meg a külső falak kezelését" --json --output-path .\data\research\plans\external_wall.json
```

Without a key the command returns a JSON configuration error and takes no
WinWatt action. `research plan` does not need `WINWATT_E2E=1` and never starts
the application.

## Audit trail

When `--output-path` is supplied, the JSON contains the prompt version,
provider/model identifiers, exact `ResearchContext`, and structured response.
No secret is recorded. This makes the choice of a next target replayable.

If validation rejects a structured response, `--output-path` still writes a
secret-free failure artifact containing the retrieved context, the complete
versioned instructions, provider/model, raw structured response, parsed plan,
and validation error. The error explicitly reports
`retrieved_verified_concepts`, `planner_known_verified`, and
`invalid_verified_claims`; it does not silently drop an invalid claim.

The instructions also include context-derived
`allowed_verified_concepts` and `allowed_hypothesis_concepts`. Those are exact
identifier allow-lists, not parent prefixes: verification of
`room.boundary.external_wall.x_m` never verifies
`room.boundary.external_wall` or any related capability.

The caller's requested goal is also canonicalized after parsing. An LLM may
paraphrase it, but that text is non-authoritative: final `ResearchPlan.goal`
always equals the exact caller input, while `interpreted_scope` preserves the
LLM's interpretation. No fuzzy goal-equivalence check is used.

## Candidate boundary and research step types

The provider produces a `CandidateResearchPlan`, which deliberately preserves
candidate `observe` strings for audit. The planner then performs the only
conversion to the strict `ExperimentSpec`. An unsupported natural-language
observation is rejected there, retained in the failure artifact, and never
reaches `ExperimentRunner`.

`research_step_type` distinguishes `documentation_research`,
`capability_enumeration`, `experiment`, `human_question`, and `unsupported`.
Only `experiment` may contain a proposed experiment. Enumeration can return
manual-supported boundary types, workflows, common/type-specific fields, and
semantic capability candidates without fabricating an experiment or changing
knowledge status.

## First target behavior

For the external-wall goal, retrieval exposes the already verified
`room.boundary.external_wall.x_m`, the manual-supported but unverified
`room.boundary.external_wall.solar_absorptance`, related manual excerpts, and
the existing safe handlers. If the selected target has no safe read/write
handler, the valid output is `experiment_status: unsupported`, not a fabricated
experiment.

The next sprint can explicitly connect an approved plan to `ExperimentRunner`:

```text
ResearchPlan -> human approval -> ExperimentRunner -> evidence -> replanning
```
