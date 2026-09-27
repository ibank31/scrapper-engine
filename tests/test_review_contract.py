#!/usr/bin/env python3
import copy
import unittest

from core.review_contract import compile_review_contract, review_contract_is_current


class ReviewContractTests(unittest.TestCase):
    def setUp(self):
        self.gate = {
            "schema_version": 1,
            "compliance_gate_id": "compliance-gate-v1:gate",
            "campaign_id": "campaign-1",
            "source_hash": "source-hash-1",
            "status": "review",
            "issues": [
                {
                    "issue_id": "issue-1",
                    "code": "upstream_review",
                    "severity": "warning",
                    "message": "One stage needs review",
                }
            ],
            "summary": {"check_count": 8, "critical_count": 0, "warning_count": 1, "issue_count": 1},
        }
        self.preview = {
            "id": "preview-1",
            "status": "pending_review",
            "candidate_id": "candidate-1",
            "source_asset_id": "asset-1",
            "artifact_hash": "artifact-1",
            "caption_draft": "Caption",
            "caption_revision_id": "caption-1",
            "validation": {"status": "pass"},
            "distinctness": {"distinct": True},
            "subtitle_delivery": {"mode": "burned_in"},
            "sound_tags": {"status": "verified"},
        }

    def test_human_summary_and_actions(self):
        contract = compile_review_contract(self.gate, self.preview)
        self.assertEqual(contract["decision_state"], "ready_for_review")
        self.assertEqual(contract["summary"]["label"], "Perlu diperiksa")
        self.assertTrue(contract["review_actions"]["approve"])
        self.assertTrue(contract["review_actions"]["reject"])
        self.assertTrue(contract["review_actions"]["request_changes"])
        self.assertEqual(contract["exceptions"][0]["label"], "Ada bagian aturan campaign yang perlu diperhatikan.")

    def test_blocked_compliance_cannot_be_approved(self):
        gate = copy.deepcopy(self.gate)
        gate["status"] = "blocked"
        contract = compile_review_contract(gate, self.preview)
        self.assertEqual(contract["decision_state"], "blocked")
        self.assertFalse(contract["review_actions"]["approve"])
        self.assertEqual(contract["summary"]["status"], "tidak_dapat_dilanjutkan")

    def test_missing_gate_blocks_review(self):
        contract = compile_review_contract(None, self.preview, campaign_id="campaign-1")
        self.assertEqual(contract["decision_state"], "blocked")
        self.assertFalse(contract["review_actions"]["approve"])

    def test_missing_caption_revision_blocks_approval(self):
        preview = copy.deepcopy(self.preview)
        preview["caption_revision_id"] = ""
        contract = compile_review_contract(self.gate, preview)
        self.assertEqual(contract["decision_state"], "blocked")
        self.assertFalse(contract["review_actions"]["approve"])

    def test_failed_video_validation_blocks_approval(self):
        preview = copy.deepcopy(self.preview)
        preview["validation"] = {"status": "fail"}
        contract = compile_review_contract(self.gate, preview)
        self.assertEqual(contract["decision_state"], "blocked")
        self.assertFalse(contract["review_actions"]["approve"])
        self.assertEqual(contract["summary"]["status"], "tidak_dapat_dilanjutkan")

    def test_deterministic_and_input_immutable(self):
        gate = copy.deepcopy(self.gate)
        preview = copy.deepcopy(self.preview)
        before = (copy.deepcopy(gate), copy.deepcopy(preview))
        first = compile_review_contract(gate, preview)
        second = compile_review_contract(gate, preview)
        self.assertEqual(first, second)
        self.assertEqual((gate, preview), before)

    def test_current_contract_identity(self):
        contract = compile_review_contract(self.gate, self.preview)
        self.assertTrue(review_contract_is_current(contract, self.gate, self.preview))
        changed = copy.deepcopy(self.preview)
        changed["artifact_hash"] = "artifact-2"
        self.assertFalse(review_contract_is_current(contract, self.gate, changed))


if __name__ == "__main__":
    unittest.main()
