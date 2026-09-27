# CA-06 Acceptance Contract — Campaign-aware Clip Strategy

## Scope

CA-06 compiles the CA-04 `production_contract` and CA-05 `material_plan` into an additive `clip_strategy` inside the existing intelligence envelope. It is a deterministic planning layer, not a renderer, downloader, publisher, compliance gate, or posting-package compiler.

The normalized chain is:

```
campaign → evidence → brain → critic → reconciliation → production_contract
→ material_plan → clip_strategy
```

The legacy `rules` projection remains available for existing consumers.

## Contract guarantees

`compile_clip_strategy(production_contract, material_plan, ...)` preserves:

- campaign, source, Brain, reconciliation, Production Contract, and Material Plan identity;
- platform scope and duration constraints;
- material requirement IDs and upstream production requirement lineage;
- reconciliation/Brain rule IDs, evidence IDs, and source references;
- mandatory, optional, and unknown requirement semantics;
- explicit `ready`, `review`, and `blocked` status;
- deterministic segment IDs, strategy IDs, ordering, issues, and summaries.

Only assets in `verified`, `acquired`, or `ready` lifecycle states may become selected segments. Candidate or discovered assets remain review/blocking inputs and are never silently promoted.

A timestamp is copied only from structured segment metadata. If it is absent, the segment remains timestamp-unresolved; no `0` or fabricated start time is emitted.

Authorized fallback assets are recorded but never activated implicitly. Fallback use requires a later explicit decision.

## Cache validity

`clip_strategy_is_current()` requires matching:

- `campaign_id`
- `source_hash`
- `brain_id`
- `reconciliation_id`
- `production_contract_id`
- `material_plan_id`
- schema version

The worker validates the strategy when it is present. Older valid CA-05 envelopes remain readable for legacy compatibility; newly normalized envelopes include `clip_strategy`.

## Acceptance

Run:

```bash
python -m unittest -v tests.test_clip_strategy
python scripts/accept_ca06.py
```

The bounded acceptance verifies strategy presence, identity linkage, mandatory segment preservation, platform scope, duration propagation, provenance coverage, missing mandatory blocking, optional semantics, explicit fallback behavior, cache invalidation, input immutability, legacy compatibility, and absence of Buffer/D1 mutation.

Full repository gates remain required before merge:

```bash
python -m unittest discover -s tests -v
python -m py_compile core/*.py modules/*/*.py worker/*.py tests/*.py
python -m compileall -q core modules worker
python -m pip check
git diff --check
```

## Limitations

CA-06 does not infer visually good hooks, analyze video frames, invent segment timestamps, render media, download arbitrary assets, publish to Buffer, mutate D1, or implement CA-07. Segment localization without structured timestamps remains a downstream/manual review responsibility.
