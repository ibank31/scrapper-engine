import copy
import unittest

from core.clip_strategy import clip_strategy_is_current, compile_clip_strategy
from core.material_intelligence import compile_material_plan


def material(value="official footage", required=True, evidence="e1", scope=None):
    return {"field": "asset_sources", "value": value, "required": required, "scope": scope or {}, "provenance": {"requirement_level": "mandatory" if required else "optional", "rule_id": "rule-1", "reconciliation_rule_id": "recon-1", "brain_rule_ids": ["brain-rule-1"], "evidence_ids": [evidence], "source_references": [{"source_type": "description", "location": "requirements"}], "source_hash": "source-1", "interpretation_type": "explicit"}}


def contract(requirements=None):
    return {"schema_version": 1, "contract_id": "production-contract-v1:1", "campaign_id": "campaign-1", "source_hash": "source-1", "brain_id": "brain-v1:1", "reconciliation_id": "reconciliation-v1:1", "clip": {"requirements": [{"field": "duration_seconds", "required": True, "constraint": {"min": 10, "max": 30}, "scope": {}, "provenance": {"rule_id": "duration-rule", "evidence_ids": ["duration-e1"]}}]}, "material": {"requirements": requirements or [], "asset_requirements": requirements or [], "fallback_assets": []}}


class ClipStrategyTests(unittest.TestCase):
    def test_missing_mandatory_is_blocked_and_preserved(self):
        production = contract([material()])
        plan = compile_material_plan(production)
        strategy = compile_clip_strategy(production, plan)
        self.assertEqual(strategy["status"], "blocked")
        self.assertEqual(strategy["summary"]["mandatory_segments"], 1)
        self.assertEqual(strategy["segments"][0]["status"], "blocked")
        self.assertEqual(strategy["segments"][0]["evidence_ids"], ["e1"])

    def test_verified_asset_selects_segment_without_fake_timestamp(self):
        production = contract([material(scope={"platforms": ["Instagram"]})])
        base = compile_material_plan(production)
        rid = base["requirements"][0]["material_requirement_id"]
        plan = compile_material_plan(production, [{"material_requirement_id": rid, "status": "verified", "fingerprint": "fp-1", "source_url": "https://example.test/a.mp4"}])
        strategy = compile_clip_strategy(production, plan)
        self.assertEqual(strategy["status"], "review")
        self.assertEqual(strategy["platforms"], ["instagram"])
        self.assertEqual(strategy["segments"][0]["status"], "selected")
        self.assertIsNone(strategy["segments"][0]["start_seconds"])
        self.assertEqual(strategy["segments"][0]["platforms"], ["instagram"])

    def test_explicit_timestamp_candidate_is_retained(self):
        production = contract([material()])
        base = compile_material_plan(production)
        rid = base["requirements"][0]["material_requirement_id"]
        plan = compile_material_plan(production, [{"material_requirement_id": rid, "status": "ready", "fingerprint": "fp-1", "source_url": "https://example.test/a.mp4"}])
        strategy = compile_clip_strategy(production, plan, [{"asset_fingerprint": "fp-1", "start_seconds": 4, "end_seconds": 12}])
        self.assertEqual(strategy["status"], "ready")
        self.assertEqual(strategy["segments"][0]["start_seconds"], 4)
        self.assertEqual(strategy["segments"][0]["end_seconds"], 12)

    def test_determinism_cache_and_immutability(self):
        production = contract([material()])
        before = copy.deepcopy(production)
        plan = compile_material_plan(production)
        first = compile_clip_strategy(production, plan)
        second = compile_clip_strategy(copy.deepcopy(production), copy.deepcopy(plan))
        self.assertEqual(first, second)
        self.assertEqual(production, before)
        self.assertTrue(clip_strategy_is_current(first, production, plan))
        changed = copy.deepcopy(plan)
        changed["source_hash"] = "source-2"
        self.assertFalse(clip_strategy_is_current(first, production, changed))

    def test_authorized_fallback_is_not_silently_activated(self):
        production = contract([material()])
        production["material"]["fallback_assets"] = ["approved alternate"]
        plan = compile_material_plan(production)
        strategy = compile_clip_strategy(production, plan)
        self.assertEqual(strategy["status"], "blocked")
        self.assertTrue(strategy["fallbacks"][0]["authorized"])
        self.assertTrue(any(item["type"] == "fallback_available_not_activated" for item in strategy["issues"]))


if __name__ == "__main__":
    unittest.main()
