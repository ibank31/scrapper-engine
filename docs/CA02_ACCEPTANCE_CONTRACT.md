# CA-02 Acceptance Contract

## Hypothesis

A structurally valid Campaign Brain can still be semantically wrong. A deterministic Campaign Critic must detect source-to-Brain defects without mutating or reconciling the Brain.

## Contract

`critique_campaign(campaign, campaign_brain)` returns a serializable object containing:

- `schema_version=1`;
- deterministic `critic_id`;
- `campaign_id`, `source_hash`, and `brain_id`;
- `status`: `pass`, `review`, or `blocked`;
- `summary.finding_count` and counts by severity;
- sorted `findings` with deterministic `finding_id`.

Each finding contains:

- `severity`: exactly `CRITICAL`, `WARNING`, `AMBIGUITY`, or `INFO`;
- `code`, `category`, `message`, `rule_path`;
- `brain_rule_ids`, `evidence_ids`, `source_references`;
- `reason` and `status=open`.

## Required detection gate

The existing six-shape corpus must remain clean, while seeded Brain mutations must detect:

- missing rule;
- duplicate rule;
- contradiction;
- unsupported inference;
- platform scope mismatch;
- lost value;
- wrong CTA;
- wrong handle;
- wrong hashtag;
- missing material requirement.

Legitimate variants, platform-specific rules, optional rules, and unresolved source conflicts must not be reported as simple duplicate/contradiction defects.

## Safety and determinism

- The critic never mutates `campaign_brain`.
- CA-02 detects; CA-03 reconciles.
- Findings are sorted and identities are hash-derived, never random.
- Substantive source-backed findings include evidence IDs whenever source evidence exists.
- `CRITICAL` findings produce `status=blocked`.
- Exact facts use deterministic comparison; no AI call is required.

## Verification commands

```text
python -m unittest -v tests.test_campaign_critic
python -m unittest discover -s tests -v
python -m py_compile core/*.py modules/*/*.py worker/*.py tests/*.py
python -m compileall -q core modules worker
python -m pip check
git diff --check
```

## Production gate

After merge, the bounded Ryan workflow must prove:

- `campaign_critic` is persisted alongside `campaign_brain`;
- critic `brain_id` and `source_hash` match the persisted Brain and AI result;
- the critic result is observable and has zero critical findings;
- existing legacy rules remain compatible;
- Buffer and publishing are not mutated.

## Verified production evidence

The merged main SHA `47ab5d11935fe74406ed210a2db122a3d02e5f2d` passed controlled acceptance run `36284355791`.

The persisted result was observable with `CRITIC_STATUS=review`, `CRITIC_FINDINGS=7`, and zero critical findings. This is an accepted CA-02 outcome: warnings remain available for later reconciliation/review, while no critical issue blocks the bounded pipeline proof. The ordinary `tests` run `36284355788` and `phase5-acceptance` run `36284355798` also passed on the same SHA.
