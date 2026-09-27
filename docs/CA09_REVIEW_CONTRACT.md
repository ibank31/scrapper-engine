# CA-09 Review Contract

## Purpose

CA-09 introduces a deterministic human-review projection over the existing CA-08 compliance gate and rendered preview. It does not replace CA-08, create a second AI reviewer, or weaken the publication safety boundary.

## Contract boundary

```
campaign intelligence
  -> CA-08 compliance_gate
  -> CA-09 review_contract
  -> human review
  -> approval / rejection / changes requested
```

CA-08 remains authoritative for compliance. A blocked CA-08 gate cannot be overridden by a human approval.

## Human-facing states

- `siap_ditinjau`: the preview can enter the review workspace.
- `perlu_perhatian`: the preview can be reviewed, but one or more checks deserve attention.
- `tidak_dapat_dilanjutkan`: the review must remain blocked.

The internal state remains separate from preview state:

- CA-08: `ready | review | blocked`
- preview review: `pending_review | approved_for_manual_post | rejected | changes_requested | pending_render`

## Contract identity

The deterministic `review_contract_id` binds:

- campaign_id
- source_hash
- compliance_gate_id
- preview_id
- artifact_hash
- caption_revision_id
- human-readable checks/exceptions

The contract is a projection, not an independent policy engine.

## Required safety behavior

1. Missing CA-08 -> blocked.
2. Blocked CA-08 -> blocked.
3. Missing artifact identity -> blocked for approval.
4. Missing caption revision -> blocked for approval.
5. No LLM calls.
6. Upstream inputs are copied and never mutated.
7. Re-render creates a new preview identity, so the old review contract cannot become current for the new artifact.
