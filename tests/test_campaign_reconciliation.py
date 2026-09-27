import copy
import unittest

from core.campaign_critic import critique_campaign
from core.campaign_evidence import source_fingerprint, verify_quote
from core.campaign_reconciliation import reconcile_campaign_rules


def evidence(campaign, path, quote):
    item = verify_quote(campaign, quote)
    item["rule_path"] = path
    return item


def make_inputs(campaign, rules, findings=None, evidence_items=None):
    evidence_items = evidence_items or []
    brain = {
        "schema_version": 1,
        "campaign_id": campaign["id"],
        "source_hash": source_fingerprint(campaign),
        "brain_id": "brain-v1:test",
        "rules": rules,
        "evidence": {"verified": evidence_items},
    }
    critic_findings = findings or []
    critic = {
        "schema_version": 1,
        "campaign_id": campaign["id"],
        "source_hash": source_fingerprint(campaign),
        "brain_id": brain["brain_id"],
        "critic_id": "critic-v1:test",
        "status": "review" if critic_findings else "pass",
        "findings": critic_findings,
    }
    contract = {
        "schema_version": 1,
        "campaign_id": campaign["id"],
        "source_hash": source_fingerprint(campaign),
        "verified": evidence_items,
        "unverified": [],
    }
    return contract, brain, critic


def rule(path, value, evidence_item, *, requirement="mandatory", scope=None, rid="rule:test", priority=None):
    return {
        "rule_id": rid,
        "source_rule_path": path,
        "value": value,
        "requirement_level": requirement,
        "scope": scope or {},
        "evidence_ids": [evidence_item["evidence_id"]] if evidence_item else [],
        "source_references": [],
        "priority": priority,
        "interpretation_type": "explicit" if evidence_item else "inferred",
    }


def finding(code, path, evidence_items, *, severity="WARNING", rid="finding:test"):
    return {
        "finding_id": rid,
        "code": code,
        "severity": severity,
        "rule_path": path,
        "evidence_ids": [item["evidence_id"] for item in evidence_items],
        "brain_rule_ids": [],
    }


class CampaignReconciliationTests(unittest.TestCase):
    def test_exact_agreement_coalesces_rules_and_preserves_all_evidence(self):
        campaign = {
            "id": "agreement",
            "requirements": [
                {"text": "Duration must be 15 seconds.", "isMandatory": True},
                {"text": "Duration must be 15 seconds.", "isMandatory": True},
            ],
        }
        a = evidence(campaign, "rules.duration", campaign["requirements"][0]["text"])
        b = evidence(campaign, "rules.duration", campaign["requirements"][1]["text"])
        rules = [rule("rules.duration", "15 seconds", a, rid="rule:a"), rule("rules.duration", "15 seconds", b, rid="rule:b")]
        contract, brain, critic = make_inputs(campaign, rules, [finding("DUPLICATE_RULE", "rules.duration", [a, b])], [a, b])

        result = reconcile_campaign_rules(campaign, contract, brain, critic)
        self.assertEqual(len(result["rules"]), 1)
        self.assertEqual(result["rules"][0]["resolution"]["method"], "exact_agreement")
        self.assertEqual(set(result["rules"][0]["evidence_ids"]), {a["evidence_id"], b["evidence_id"]})
        self.assertEqual(set(result["rules"][0]["brain_rule_ids"]), {"rule:a", "rule:b"})
        self.assertEqual(result["findings"][0]["status"], "resolved")

    def test_explicit_current_source_priority_beats_legacy_source(self):
        campaign = {
            "id": "priority",
            "description": "Legacy duration is 15 seconds.",
            "source_of_truth": {"description": "Current duration is 30 seconds."},
        }
        old = evidence(campaign, "rules.duration", "Legacy duration is 15 seconds.")
        new = evidence(campaign, "rules.duration", "Current duration is 30 seconds.")
        self.assertGreater(new["source_priority"], old["source_priority"])
        rules = [rule("rules.duration", "15 seconds", old, rid="rule:old"), rule("rules.duration", "30 seconds", new, rid="rule:new")]
        critic_finding = finding("CONTRADICTORY_RULE", "rules.duration", [old, new], severity="CRITICAL")
        critic_finding["brain_rule_ids"] = ["rule:old", "rule:new"]
        contract, brain, critic = make_inputs(campaign, rules, [critic_finding], [old, new])

        result = reconcile_campaign_rules(campaign, contract, brain, critic)
        winner = next(item for item in result["rules"] if item["resolution"]["status"] == "resolved")
        self.assertEqual(winner["value"], "30 seconds")
        self.assertEqual(winner["resolution"]["method"], "explicit_source_priority")
        self.assertEqual(set(winner["resolution"]["loser_evidence_ids"]), {old["evidence_id"]})
        self.assertTrue(any(item["status"] == "resolved" for item in result["conflicts"]))

    def test_conflict_without_precedence_remains_unresolved(self):
        campaign = {"id": "unresolved", "docs_text": "Duration is 15 seconds. Duration is 60 seconds."}
        first = evidence(campaign, "rules.duration", "Duration is 15 seconds.")
        second = evidence(campaign, "rules.duration", "Duration is 60 seconds.")
        first["source_priority"] = second["source_priority"] = 0
        rules = [rule("rules.duration", "15 seconds", first, rid="rule:one"), rule("rules.duration", "60 seconds", second, rid="rule:two")]
        cf = finding("CONTRADICTORY_RULE", "rules.duration", [first, second], severity="CRITICAL")
        contract, brain, critic = make_inputs(campaign, rules, [cf], [first, second])

        result = reconcile_campaign_rules(campaign, contract, brain, critic)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(len([x for x in result["conflicts"] if x["kind"] == "overlapping_rule_disagreement"]), 1)
        self.assertTrue(all(item["resolution"]["status"] == "unresolved" for item in result["rules"]))
        conflict_ids = {item["conflict_id"] for item in result["conflicts"]}
        self.assertTrue(all(set(item["conflict_ids"]) & conflict_ids for item in result["rules"]))
        self.assertEqual(result["findings"][0]["status"], "unresolved")

    def test_platform_variants_with_distinct_scope_are_preserved(self):
        campaign = {"id": "platforms", "description": "Instagram uses #Alpha. TikTok uses #Beta."}
        instagram = evidence(campaign, "posting.instagram.hashtags", "Instagram uses #Alpha.")
        tiktok = evidence(campaign, "posting.tiktok.hashtags", "TikTok uses #Beta.")
        rules = [
            rule("posting.instagram.hashtags", "#Alpha", instagram, scope={"platforms": ["instagram"]}, rid="rule:ig"),
            rule("posting.tiktok.hashtags", "#Beta", tiktok, scope={"platforms": ["tiktok"]}, rid="rule:tt"),
        ]
        contract, brain, critic = make_inputs(campaign, rules, evidence_items=[instagram, tiktok])
        result = reconcile_campaign_rules(campaign, contract, brain, critic)
        self.assertEqual(len(result["rules"]), 2)
        self.assertEqual(result["conflicts"], [])
        self.assertEqual(result["status"], "resolved")

    def test_language_variants_are_preserved(self):
        campaign = {"id": "languages", "description": 'English CTA: "Follow now". Indonesian CTA: "Ikuti sekarang".'}
        en = evidence(campaign, "rules.cta_text", 'English CTA: "Follow now".')
        id_ = evidence(campaign, "rules.cta_text", 'Indonesian CTA: "Ikuti sekarang".')
        rules = [
            rule("rules.cta_text", "Follow now", en, scope={"languages": ["en"]}, rid="rule:en"),
            rule("rules.cta_text", "Ikuti sekarang", id_, scope={"languages": ["id"]}, rid="rule:id"),
        ]
        contract, brain, critic = make_inputs(campaign, rules, evidence_items=[en, id_])
        result = reconcile_campaign_rules(campaign, contract, brain, critic)
        self.assertEqual({tuple(item["scope"]["languages"]) for item in result["rules"]}, {("en",), ("id",)})
        self.assertFalse(result["conflicts"])

    def test_missing_brain_rule_is_reconstructed_from_verified_evidence(self):
        campaign = {
            "id": "missing",
            "requirements": [{"text": "Include a visible campaign logo.", "isMandatory": True}],
        }
        ev = evidence(campaign, "rules.material.logo", "Include a visible campaign logo.")
        missing = finding("MISSING_RULE", "rules.material.logo", [ev], severity="CRITICAL")
        contract, brain, critic = make_inputs(campaign, [], [missing], [ev])
        result = reconcile_campaign_rules(campaign, contract, brain, critic)
        rebuilt = result["rules"][0]
        self.assertEqual(rebuilt["value"], ev["quote"])
        self.assertEqual(rebuilt["requirement_level"], "mandatory")
        self.assertEqual(rebuilt["resolution"]["method"], "reconstructed_from_evidence")
        self.assertEqual(rebuilt["evidence_ids"], [ev["evidence_id"]])
        self.assertEqual(result["findings"][0]["status"], "resolved")

    def test_unsupported_inference_is_never_promoted_to_canonical_mandatory(self):
        campaign = {"id": "unsupported", "description": "No duration is specified."}
        unsupported = rule("rules.duration", "15 seconds", None, rid="rule:inference")
        cf = finding("UNSUPPORTED_INFERENCE", "rules.duration", [], severity="CRITICAL")
        contract, brain, critic = make_inputs(campaign, [unsupported], [cf], [])
        result = reconcile_campaign_rules(campaign, contract, brain, critic)
        self.assertEqual(result["rules"], [])
        self.assertEqual(result["findings"][0]["status"], "resolved")
        self.assertEqual(result["findings"][0]["method"], "rejected_unsupported_inference")
        self.assertEqual(result["status"], "resolved")

    def test_evidence_linked_inference_is_demoted_from_mandatory(self):
        campaign = {"id": "inference-demotion", "description": "Consider adding a 15 second duration."}
        ev = evidence(campaign, "rules.duration", "Consider adding a 15 second duration.")
        inferred = rule("rules.duration", "15 seconds", ev, requirement="mandatory")
        inferred["interpretation_type"] = "inferred"
        contract, brain, _ = make_inputs(campaign, [inferred], evidence_items=[ev])
        critic = critique_campaign(campaign, brain)
        result = reconcile_campaign_rules(campaign, contract, brain, critic)
        self.assertEqual(result["rules"][0]["requirement_level"], "unknown")
        self.assertEqual(result["rules"][0]["resolution"]["method"], "demoted_unsupported_mandatory_inference")
        finding_record = next(item for item in result["findings"] if item["code"] == "UNSUPPORTED_MANDATORY_INFERENCE")
        self.assertEqual(finding_record["status"], "resolved")

    def test_mandatory_optional_disagreement_is_not_silently_overwritten(self):
        campaign = {"id": "semantics", "description": "A subtitle is recommended; subtitles are required."}
        optional = evidence(campaign, "rules.subtitle", "A subtitle is recommended;")
        mandatory = evidence(campaign, "rules.subtitle", "subtitles are required.")
        optional["source_priority"] = mandatory["source_priority"] = 0
        rules = [rule("rules.subtitle", "subtitle", optional, requirement="optional", rid="rule:optional"), rule("rules.subtitle", "subtitle", mandatory, requirement="mandatory", rid="rule:mandatory")]
        cf = finding("CONTRADICTORY_RULE", "rules.subtitle", [optional, mandatory], severity="CRITICAL")
        contract, brain, critic = make_inputs(campaign, rules, [cf], [optional, mandatory])
        result = reconcile_campaign_rules(campaign, contract, brain, critic)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual({item["requirement_level"] for item in result["rules"]}, {"mandatory", "optional"})
        self.assertTrue(all(item["resolution"]["status"] == "unresolved" for item in result["rules"]))

    def test_every_reconciled_rule_has_live_evidence_provenance(self):
        campaign = {"id": "provenance", "description": "Use a 1:1 aspect ratio."}
        ev = evidence(campaign, "rules.aspect_ratio", "Use a 1:1 aspect ratio.")
        contract, brain, critic = make_inputs(campaign, [rule("rules.aspect_ratio", "1:1", ev)], evidence_items=[ev])
        result = reconcile_campaign_rules(campaign, contract, brain, critic)
        self.assertTrue(result["rules"])
        for item in result["rules"]:
            self.assertTrue(item["evidence_ids"])
            self.assertTrue(item["source_references"])
            self.assertTrue(item["brain_rule_ids"])

    def test_same_input_is_deterministic_and_inputs_are_not_mutated(self):
        campaign = {"id": "stable", "description": "Use a 1:1 aspect ratio."}
        ev = evidence(campaign, "rules.aspect_ratio", "Use a 1:1 aspect ratio.")
        contract, brain, critic = make_inputs(campaign, [rule("rules.aspect_ratio", "1:1", ev)], evidence_items=[ev])
        before = copy.deepcopy((campaign, contract, brain, critic))
        first = reconcile_campaign_rules(campaign, contract, brain, critic)
        second = reconcile_campaign_rules(campaign, contract, brain, critic)
        self.assertEqual(first, second)
        self.assertEqual(campaign, before[0])
        self.assertEqual(contract, before[1])
        self.assertEqual(brain, before[2])
        self.assertEqual(critic, before[3])
        self.assertEqual(first["reconciliation_id"], second["reconciliation_id"])

    def test_unresolved_critic_finding_is_retained_as_explicit_conflict(self):
        campaign = {"id": "unresolved-finding", "description": "Use a 1:1 aspect ratio."}
        ev = evidence(campaign, "rules.aspect_ratio", "Use a 1:1 aspect ratio.")
        cf = finding("LOST_VALUE", "rules.aspect_ratio", [ev], severity="WARNING")
        contract, brain, critic = make_inputs(campaign, [rule("rules.aspect_ratio", "16:9", ev)], [cf], [ev])
        result = reconcile_campaign_rules(campaign, contract, brain, critic)
        self.assertEqual(result["findings"][0]["status"], "unresolved")
        unresolved_conflict = next(item for item in result["conflicts"] if item.get("critic_finding_id") == cf["finding_id"])
        self.assertTrue(unresolved_conflict["rule_ids"])
        self.assertIn(unresolved_conflict["conflict_id"], result["rules"][0]["conflict_ids"])
        self.assertEqual(result["status"], "review")

    def test_identity_mismatch_blocks_reconciliation(self):
        campaign = {"id": "identity"}
        contract, brain, critic = make_inputs(campaign, [], [])
        critic["brain_id"] = "brain-v1:wrong"
        result = reconcile_campaign_rules(campaign, contract, brain, critic)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("critic_brain_id_mismatch", result["integrity_errors"])

    def test_brain_marked_semantic_ambiguity_remains_explicit(self):
        campaign = {"id": "brain-ambiguity", "description": "Use either a 1:1 or 9:16 crop."}
        ev = evidence(campaign, "rules.aspect_ratio", "Use either a 1:1 or 9:16 crop.")
        ambiguous_rule = rule("rules.aspect_ratio", "1:1 or 9:16", ev)
        ambiguous_rule["interpretation_type"] = "ambiguous"
        duplicate = copy.deepcopy(ambiguous_rule)
        duplicate["rule_id"] = "rule:ambiguous-duplicate"
        contract, brain, critic = make_inputs(campaign, [ambiguous_rule, duplicate], evidence_items=[ev])
        result = reconcile_campaign_rules(campaign, contract, brain, critic)
        self.assertEqual(result["status"], "review")
        self.assertEqual(result["rules"][0]["resolution"]["status"], "unresolved")
        self.assertEqual(result["rules"][0]["resolution"]["method"], "exact_agreement_with_ambiguity")
        self.assertTrue(any(item["kind"] == "brain_semantic_ambiguity" for item in result["conflicts"]))

    def test_real_critic_findings_are_all_accounted_for(self):
        campaign = {"id": "critic-chain", "description": "Duration must be 15 seconds."}
        ev = evidence(campaign, "rules.duration", "Duration must be 15 seconds.")
        contract, brain, critic = make_inputs(campaign, [], [], [ev])
        real_critic = critique_campaign(campaign, brain)
        result = reconcile_campaign_rules(campaign, contract, brain, real_critic)
        self.assertEqual(
            {item["finding_id"] for item in real_critic["findings"]},
            {item["finding_id"] for item in result["findings"]},
        )
        self.assertEqual(result["summary"]["critic_finding_count"], len(real_critic["findings"]))


if __name__ == "__main__":
    unittest.main()
