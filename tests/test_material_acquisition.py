from core.material_acquisition import (
    acquisition_status,
    build_legacy_compatible_policy,
    material_plan_fingerprint,
    normalize_material_policy,
    validate_material_policy,
)


def test_policy_normalizes_campaign_specific_material():
    policy = normalize_material_policy({
        "acquisition_mode": "named_reference_resolution",
        "required_assets": [{
            "asset_id": "music_video",
            "intent": "official_music_video",
            "quantity": {"min": 1, "max": 1},
            "preferred_sources": ["youtube_official"],
            "fallback_sources": ["official_site"],
            "allowed_source_types": ["official_publisher"],
            "forbidden_source_types": ["fan_upload"],
            "discovery_methods": ["named_search"],
            "identity": {"artist": "Dardan", "work": "Erinnerung"},
            "verification": {"publisher_required": True},
            "evidence": [{"rule_path": "requirements.1", "quote": "Official Video"}],
        }],
        "discovery_methods": ["named_search"],
    })
    assert policy["acquisition_mode"] == "named_reference_resolution"
    assert policy["required_assets"][0]["identity"]["work"] == "Erinnerung"
    assert validate_material_policy(policy) == []


def test_invalid_policy_cannot_hide_missing_discovery_method():
    policy = normalize_material_policy({
        "required_assets": [{"asset_id": "x", "quantity": {"min": 1, "max": 1}}],
    })
    errors = validate_material_policy(policy)
    assert any("no discovery method" in error for error in errors)


def test_legacy_campaign_is_conservative():
    policy = build_legacy_compatible_policy({
        "resources": [{"url": "https://example.com/provided.mp4"}],
    })
    assert policy["acquisition_mode"] == "legacy_conservative"
    assert "manual" in policy["source_hierarchy"]
    assert "unverified public reuploads" in policy["exclusions"]


def test_acquisition_status_requires_all_required_minimums():
    policy = normalize_material_policy({
        "required_assets": [
            {"asset_id": "a", "quantity": {"min": 1, "max": 1}, "discovery_methods": ["explicit_url"]},
            {"asset_id": "b", "quantity": {"min": 1, "max": 1}, "discovery_methods": ["explicit_url"]},
        ],
    })
    assert acquisition_status([{"asset_id": "a", "status": "accessible"}], policy) == "unresolved"
    assert acquisition_status([
        {"asset_id": "a", "status": "accessible"},
        {"asset_id": "b", "status": "manual_required"},
    ], policy) == "manual_required"


def test_material_plan_fingerprint_is_stable():
    a = {"required_assets": [{"asset_id": "x", "quantity": {"min": 1, "max": 1}, "discovery_methods": ["explicit_url"]}]}
    b = {"required_assets": [{"discovery_methods": ["explicit_url"], "quantity": {"max": 1, "min": 1}, "asset_id": "x"}]}
    assert material_plan_fingerprint(a) == material_plan_fingerprint(b)


def test_policy_rejects_invalid_per_asset_discovery_method():
    policy = normalize_material_policy({
        "required_assets": [{
            "asset_id": "x",
            "quantity": {"min": 1, "max": 1},
            "discovery_methods": ["invented_provider"],
        }],
    })
    assert any("invalid discovery method" in error for error in validate_material_policy(policy))


def test_planner_binds_and_rejects_sources():
    from core.material_planner import match_candidate, permitted_source

    policy = normalize_material_policy({
        "required_assets": [{
            "asset_id": "official_video",
            "quantity": {"min": 1, "max": 1},
            "allowed_source_types": ["official_publisher"],
            "forbidden_source_types": ["fan_upload"],
            "discovery_methods": ["named_search"],
            "preferred_sources": ["youtube_official"],
        }],
    })
    asset_id, reason = match_candidate(policy, {
        "source_type": "youtube",
        "source_url": "https://youtube.com/watch?v=abc",
    })
    assert asset_id == "official_video"
    assert reason == "policy_match"
    assert permitted_source(policy, "official_video", "fan_upload") == (False, "source_type_forbidden")


def test_planner_fallback_order_is_deterministic():
    from core.material_planner import candidate_priority

    policy = normalize_material_policy({
        "required_assets": [{
            "asset_id": "video",
            "quantity": {"min": 1, "max": 1},
            "discovery_methods": ["named_search"],
            "preferred_sources": ["youtube_official"],
            "fallback_sources": ["official_site"],
        }],
    })
    preferred = candidate_priority(policy, "video", {"source_type": "youtube", "source_url": "youtube_official"})
    fallback = candidate_priority(policy, "video", {"source_type": "official_site", "source_url": "official_site"})
    assert preferred < fallback
