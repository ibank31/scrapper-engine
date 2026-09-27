

## 2026-09-27 — CA-03 starts from a verified CA-00 → CA-02 chain

The merged main SHA `47ab5d1` proves the first three campaign-intelligence layers can execute together: verified evidence feeds the canonical Brain, and the deterministic Critic consumes that Brain and remains read-only. Controlled production acceptance observed seven non-critical findings.

Decision: CA-03 is responsible for reconciling those findings and source conflicts. Reconciliation must preserve evidence IDs/source references, make precedence explicit, and represent unresolved ambiguity as data rather than silently choosing a value.

## 2026-09-27 — CA-03 deterministic reconciliation policy

Implemented `core/campaign_reconciliation.py` as a separate deterministic stage that consumes campaign data, the evidence contract, canonical Brain, and read-only Critic. The stage is integrated into `normalize_ai_result()` and persisted inside the existing `ai_rules_json` payload; no D1 schema change or migration is needed. Existing cached AI results without a matching reconciliation identity are stale and must be recomputed.

Decision: only evidence-linked Brain rules can be promoted. Exact same-scope agreement coalesces with all provenance. A source conflict is resolved only when metadata supplies a unique highest priority; otherwise it remains unresolved. Disjoint platform/language scopes are variants. Missing-rule reconstruction retains the verified quote verbatim; unsupported inference is not promoted. Every Critic finding must carry an explicit resolution record or unresolved conflict record. No model call or input mutation is permitted.

CA-03 was merged in PR #48 at `fe21605`; a generic source-backed CTA-annotation recovery fix followed in PR #49. Final main SHA: `803997a3a3b221acd6c29e65b2a6003e7a7d9fb8`. **CA-03 accepted and closed** after 246 passing local tests, Python compile/dependency/diff checks, passing main CI/phase-5 workflows, and bounded production run `36287752424`. Persisted production result: reconciliation `review`, 40 rules, two Critic findings retained with one unresolved, 34 verified evidence items, zero unverified evidence, 100% coverage, CTA and legacy rules compatibility, and no Buffer mutation. Several prior fresh model reruns failed unchanged evidence/CTA assertions; the final run passed without loosening acceptance or manually changing D1.

Decision: source-recovered flat CTA values must also be applied to annotated `rules.cta_text` values before Brain construction. Source-exact evidence remains the only recovery basis. The strict bounded acceptance CTA check stays unchanged.


## 2026-09-27 — CA-04 deterministic production contract compiler

CA-04 consumes only canonical CA-03 reconciliation and emits an additive `production_contract` in the existing serialized `ai_rules_json` envelope. Contract identity is derived from campaign/source/Brain/reconciliation identity and schema version; no timestamp or random ID is used. Five domain contracts preserve evidence IDs, source references, requirement and interpretation semantics, and platform/language/audience scope. Unresolved critical findings and integrity failures block; non-critical unresolved state remains review. Asset resolution, clip selection, final compliance, and publishing remain outside CA-04. Cache reuse rejects missing or mismatched contract identity without a database migration.
