import unittest

from core.delivery_operations import build_operation, can_transition, operation_key, payload_hash, transition
from core.schedule_semantics import PRODUCT_CONTRACT, build_schedule_intent, local_to_utc


class Phase3OperationTests(unittest.TestCase):
    def test_product_contract_is_next_queue_slot_and_does_not_claim_exact_time(self):
        intent = build_schedule_intent(provider="buffer", timezone="Asia/Jakarta", requested_local="2026-09-24T23:30:00")
        self.assertEqual(intent["contract"], PRODUCT_CONTRACT)
        self.assertEqual(intent["provider_mode"], "automatic/addToQueue")
        self.assertIsNone(intent["provider_due_at"])
        self.assertEqual(intent["requested_utc"], "2026-09-24T16:30:00Z")

    def test_dst_conversion_is_iana_and_canonical(self):
        self.assertEqual(local_to_utc("2026-03-08T01:30:00", "America/New_York"), "2026-03-08T06:30:00Z")
        self.assertEqual(local_to_utc("2026-11-01T01:30:00", "America/New_York"), "2026-11-01T05:30:00Z")
        with self.assertRaises(ValueError): local_to_utc("2026-01-01T00:00:00", "Not/AZone")

    def test_operation_key_is_stable_and_payload_hash_changes(self):
        self.assertEqual(operation_key("p", "c", "s", "r"), operation_key("p", "c", "s", "r"))
        self.assertNotEqual(payload_hash({"text": "a"}), payload_hash({"text": "b"}))
        operation = build_operation(preview_id="p", channel_id="c", schedule_intent=build_schedule_intent(), caption_revision_id="r", payload={"text": "a"})
        self.assertEqual(operation["provider_state"], "pending")
        self.assertTrue(operation["operation_key"].startswith("delivery-"))

    def test_state_machine_rejects_unsafe_transition(self):
        self.assertTrue(can_transition("pending", "attempting"))
        self.assertFalse(can_transition("published", "attempting"))
        self.assertEqual(transition("attempting", "unknown")["to"], "unknown")
        with self.assertRaises(ValueError): transition("pending", "scheduled")


if __name__ == "__main__": unittest.main()
