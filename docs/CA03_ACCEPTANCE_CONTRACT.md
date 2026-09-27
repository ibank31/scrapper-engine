# CA-03 Acceptance Contract — Campaign Rule Reconciliation

## Hypothesis

A deterministic reconciliation stage can consume the campaign source evidence, canonical Campaign Brain, and read-only Campaign Critic output, produce a downstream-safe source-backed rule set, and explicitly retain every ambiguity or critic finding that cannot be safely resolved.

## Architecture and persistence

```text
campaign source
  → CA-00 evidence contract
  → CA-01 campaign_brain
  → CA-02 campaign_critic
  → CA-03 campaign_reconciliation
  → persisted ai_rules_json
```

`campaign_brain` remains canonical semantic interpretation. `campaign_critic` remains detection-only. `campaign_reconciliation` is additive and does not replace either stage or the legacy `ai_rules.rules` compatibility projection. No database migration is required because the intelligence payload is already serialized in `ai_rules_json`.

`normalize_ai_result()` emits the CA-03 contract beside the Brain and Critic. The campaign sync cache gate rejects prior intelligence without a schema-valid reconciliation identity and matching campaign/source/Brain identity, causing bounded re-analysis instead of using stale, pre-CA-03 intelligence.

## Contract

`reconcile_campaign_rules(campaign, evidence_contract, campaign_brain, campaign_critic)` returns a deterministic JSON-serializable object with:

- `schema_version`, `reconciliation_id`;
- `campaign_id`, `source_hash`, `brain_id`, and `critic_id`;
- status `resolved`, `review`, or `blocked`;
- reconciled `rules`, explicit `conflicts`, and per-finding resolution records;
- integrity errors and summary counts.

Every canonical reconciled rule includes stable identity, source rule path, source-backed value, requirement level, platform/language/audience scope, evidence IDs, source references, Brain rule IDs, source priority, and resolution status/method/reason. Values are not manufactured from model-only assertions.
Rules affected by an unresolved or resolved source conflict also retain the corresponding stable `conflict_ids`; conflict records point back to affected reconciled rule IDs.

## Resolution policy

1. **Evidence is authoritative.** Brain rules without a current verified evidence link are not promoted. Unsupported/inferred rules without evidence are excluded; the associated critic finding is retained as resolved by `rejected_unsupported_inference`.
2. **Exact agreement.** Same path, value, requirement level, and scope coalesce deterministically. Every evidence ID and Brain rule ID is retained.
3. **Explicit source priority.** Overlapping, disagreeing rules resolve only if source evidence metadata gives one unique highest priority. The selected evidence and all losing evidence remain linked through the conflict record.
4. **No unique precedence.** Disagreement is `unresolved`; no value silently replaces another. Critical unresolved findings yield `blocked`, other unresolved findings yield `review`.
5. **Requirement semantics.** Mandatory/optional disagreement is a conflict, not a silent level change; absent unique source precedence it remains unresolved.
6. **Scope variants.** Disjoint platform, language, or audience scopes remain separate rules and do not create false conflicts.
7. **Missing Brain rule.** A `MISSING_RULE` or `MISSING_MATERIAL_REQUIREMENT` finding can be repaired only from its linked, currently verified evidence. The exact quote is retained as an opaque value, requirement metadata is read from structured campaign evidence when available, and the method is `reconstructed_from_evidence`.
8. **Critic observability.** Every incoming critic `finding_id` appears once in the reconciliation findings. Resolved findings have an explicit method/reason; unresolved findings also receive a conflict entry. Findings are never dropped to improve status.
9. **Integrity.** Campaign, source, Brain, and Critic identity mismatches are recorded and block reconciliation.
10. **No AI and no mutation.** Sorting, hashing, equality, scope comparison, evidence matching, and priority resolution are deterministic. No input object is mutated and no model call is made.

## Required verification matrix

Covered by `tests/test_campaign_reconciliation.py`:

- exact agreement and provenance-preserving coalescence;
- current/high-priority source beats legacy/lower-priority source;
- conflict without precedence remains unresolved;
- platform and language variants remain distinct;
- missing Brain rule reconstructed from verified evidence;
- unsupported inference is not promoted;
- mandatory/optional disagreement remains explicit;
- every resolved source-backed rule retains evidence and source references;
- stable repeated identity/output;
- campaign/evidence/Brain/Critic input immutability;
- unresolved finding preservation and identity-mismatch blocking;
- every actual Critic finding is represented.

## Verification commands

```text
python -m unittest -v tests.test_campaign_reconciliation
python -m unittest -v tests.test_campaign_evidence_acceptance tests.test_campaign_brain tests.test_campaign_critic
python -m unittest discover -s tests -v
python -m py_compile core/*.py modules/*/*.py worker/*.py tests/*.py
python -m compileall -q core modules worker
python -m pip check
git diff --check
```

## Bounded production acceptance

The existing controlled Ryan workflow is extended to verify one targeted campaign only. Its persisted acceptance checks:

- `campaign_reconciliation` is present and persisted beside Brain/Critic;
- campaign ID, source hash, Brain ID, and Critic ID match;
- all reconciled rules retain evidence IDs and source references;
- every persisted Critic finding ID remains observable in reconciliation;
- unresolved critic findings are represented in explicit conflicts;
- legacy `ai_rules.rules` remains present and compatible;
- sync uses `CLIPPER_AUTO_QUEUE=0` and invokes no Buffer publishing path.

Final bounded production acceptance passed in GitHub Actions run `36286329412` on branch SHA `383e8fc77a7c18cc7e9194024d0cbee53ccc3c64`. Persisted output: status `review`; 17 reconciled rules; one Critic finding retained as one unresolved finding; 14 verified evidence items; zero unverified evidence; coverage 1.0. Legacy rules compatibility passed, and `CLIPPER_AUTO_QUEUE=0` confirmed no Buffer publishing mutation. The PR test and phase-5 checks also passed. This is a bounded campaign acceptance, not a campaign-corpus migration. Two earlier fresh-AI attempts failed the unchanged pre-existing 100% Brain evidence-coverage gate; the final run passed without weakening that gate or changing production data manually.

## Deliberate limitations

- Semantic rewriting of arbitrary prose into a normalized rule is not attempted. Missing rules are preserved as exact evidence quotes until a later explicitly specified compiler can safely transform them.
- Semantic ambiguity that lacks deterministic source precedence remains `review` or `blocked`; CA-03 does not call AI to guess.
- The legacy rules projection remains for compatibility and is not the reconciliation source of truth.
