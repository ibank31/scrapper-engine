

## 2026-09-27 — CA-03 starts from a verified CA-00 → CA-02 chain

The merged main SHA `47ab5d1` proves the first three campaign-intelligence layers can execute together: verified evidence feeds the canonical Brain, and the deterministic Critic consumes that Brain and remains read-only. Controlled production acceptance observed seven non-critical findings.

Decision: CA-03 is responsible for reconciling those findings and source conflicts. Reconciliation must preserve evidence IDs/source references, make precedence explicit, and represent unresolved ambiguity as data rather than silently choosing a value.

## 2026-09-27 — CA-03 deterministic reconciliation policy

Implemented `core/campaign_reconciliation.py` as a separate deterministic stage that consumes campaign data, the evidence contract, canonical Brain, and read-only Critic. The stage is integrated into `normalize_ai_result()` and persisted inside the existing `ai_rules_json` payload; no D1 schema change or migration is needed. Existing cached AI results without a matching reconciliation identity are stale and must be recomputed.

Decision: only evidence-linked Brain rules can be promoted. Exact same-scope agreement coalesces with all provenance. A source conflict is resolved only when metadata supplies a unique highest priority; otherwise it remains unresolved. Disjoint platform/language scopes are variants. Missing-rule reconstruction retains the verified quote verbatim; unsupported inference is not promoted. Every Critic finding must carry an explicit resolution record or unresolved conflict record. No model call or input mutation is permitted.

Final verified branch SHA: `383e8fc77a7c18cc7e9194024d0cbee53ccc3c64`; pull request #48. **CA-03 accepted** after 245 passing local tests, Python compile/dependency/diff checks, PR tests/phase-5 acceptance, and bounded production run `36286329412`. Persisted production result: reconciliation `review`, 17 rules, one Critic finding retained explicitly unresolved, 14 verified evidence items, zero unverified evidence, 100% evidence coverage, and legacy rules compatibility; publishing queue disabled and no Buffer mutation. Two intervening fresh model reruns failed at the existing upstream Brain evidence-coverage gate; the final rerun passed with the strict gate unchanged. No manual D1 changes were made.
