# Campaign Material Intelligence

## Goal

Every campaign gets a campaign-specific material acquisition plan before media intake. Old campaigns are migrated conservatively and re-analyzed when their cached AI result predates the material-policy contract.

## Contract

core/material_acquisition.py defines the normalized contract:

- acquisition_mode
- required_assets
- per-asset intent and quantity
- preferred and fallback sources
- allowed and forbidden source types
- discovery methods
- identity fields for named material
- verification requirements and evidence
- global source hierarchy
- exclusions
- manual escalation

The material plan has its own fingerprint. It is separate from campaign rules so later stages can prove which acquisition contract was used.

## AI behavior

core/campaign_ai.py now asks Gemini to build the material acquisition policy independently for each campaign. It must not assume one global acquisition method. The model is instructed to treat examples/reference links as non-production unless the campaign explicitly authorizes them, and to use unresolved/manual states instead of inventing sources.

## Legacy migration

During campaign sync:

1. A campaign whose cached AI result has no material_policy is re-analyzed.
2. If AI is unavailable, a conservative legacy_conservative policy is created.
3. Legacy policy only trusts explicit campaign resources/source URLs and never authorizes arbitrary public reuploads.
4. The resulting policy and fingerprint are attached to the production plan.

This means old campaigns do not silently keep using the pre-intelligence acquisition behavior forever.

## Intake execution

modules/reward_campaign/intake.py consumes production.material_policy.

For named discovery intents, identity fields are converted into symbolic discovery references. Existing deterministic reference resolution then searches and verifies candidates before download. The policy is persisted in MATERIAL_ACQUISITION_PLAN.json and assets.json.

The intake remains deterministic for downloading and media validation. AI does not directly download arbitrary URLs.

## Stop states

Material acquisition distinguishes:

- resolved
- accessible
- unresolved
- manual_required

A missing required asset is not treated as successful acquisition.

## Current phase boundary

This phase establishes the contract and routes campaign-specific intent into intake. Full provider adapters and provider-specific verification are still separate work. named_search, Drive inventory, tracker resolution, and official-source verification should eventually consume the per-asset preferred_sources, fallback_sources, and verification fields directly rather than relying only on the existing generic reference resolver.

## Next implementation layer

1. Add provider adapters driven by discovery_methods.
2. Bind every acquired asset to asset_id from the policy.
3. Verify each acquired asset against its per-asset identity and source policy.
4. Require all quantity.min assets before intake can return success.
5. Persist acquisition evidence and the material-plan fingerprint into the job snapshot.
6. Block a job if its campaign material plan changes after enqueue.
