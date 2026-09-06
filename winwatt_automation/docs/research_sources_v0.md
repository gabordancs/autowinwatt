# Research Sources v0

`WinWatt.pdf` is now a local, searchable research source. It can support a
careful hypothesis, but it is never proof that a UI capability works.

## Scope and reuse

This slice reuses `KnowledgeStore`, `Hypothesis`, `ExperimentResult`, the
existing verification gate, and the later sandbox `ExperimentRunner` flow. It
adds only a Pydantic source/evidence schema and a deterministic lexical manual
index. The PDF remains the source of truth; the JSON index is regenerable.

The 122-page manual has a usable text layer and is read with `pypdf`; OCR is
not used. The index records page, inferred heading, and text chunks.

```text
raw mapping / WinWatt manual
             |
             v
        observations
             |
             v
   Semantic Knowledge Layer
             |
             v
  manual hypothesis (non-deterministic)
             |
             v
   ExperimentRunner + WinWatt sandbox
             |
             v
 deterministic save/reopen verification
             |
             v
       verified knowledge
```

## Epistemic rule

`ResearchEvidence.deterministic` is statically `false`. Recording or attaching
manual evidence cannot alter a concept from `hypothesis` to `verified`.
`KnowledgeStore.promote_to_verified()` still requires a stored, matching,
successful experiment with `roundtrip_verified=true` and deterministic
`verification` evidence.

## Commands

From `winwatt_automation`:

```powershell
.\.venv-win32\Scripts\winwatt.exe manual index
.\.venv-win32\Scripts\winwatt.exe sources list
.\.venv-win32\Scripts\winwatt.exe manual search "külső fal"
.\.venv-win32\Scripts\winwatt.exe manual search "határoló szerkezet"
.\.venv-win32\Scripts\winwatt.exe manual hypothesize "külső fal" room.boundary.external_wall.solar_absorptance hyp_manual_wall_absorptance "A kézikönyv külső fal felületéhez abszorpciós adatot említ." --confidence 0.72
.\.venv-win32\Scripts\winwatt.exe knowledge evidence room.boundary.external_wall.solar_absorptance
```

All commands emit JSON. The last command deliberately shows distinct
`manual_evidence` and knowledge/verification evidence collections.

## First manual-guided example

The manual's external-wall material discusses surface-related properties of an
external wall. The initial interpretation is deliberately recorded as
`room.boundary.external_wall.solar_absorptance` with `hypothesis` status and
confidence 0.72. It is not an assertion that the currently mapped control has
that meaning. A later sandbox experiment must write a value, natively save,
reopen, read it back, and provide deterministic evidence before promotion.

## Next smallest step

An LLM planner may later *propose* `manual hypothesize`-style structured
requests from search results. It must remain behind this same non-deterministic
manual-evidence boundary; the existing ExperimentRunner and verification gate
remain the only route to `verified`.
