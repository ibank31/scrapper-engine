import unittest

from modules.clipping.review_queue import _caption, _checklist


class ReviewQueueTest(unittest.TestCase):
    def test_caption_and_checklist_follow_plan(self):
        plan = {
            "campaign": {"title": "Demo campaign"},
            "production": {
                "required_handles": ["@Demo"],
                "cta_urls": ["https://demo.example"],
                "watermark_required": True,
                "no_third_party_watermark": True,
                "official_audio_required": True,
                "prohibited": ["view_manipulation"],
            },
        }
        candidate = {"text": "A strong hook"}
        caption = _caption(plan, candidate)
        checklist = _checklist(plan, {"review": ["check the final frame"]})
        self.assertIn("Demo campaign", caption)
        self.assertIn("@Demo", caption)
        self.assertIn("A strong hook", caption)
        self.assertGreaterEqual(len(checklist), 5)
        self.assertIn("check the final frame", checklist)

    def test_mandatory_source_rule_is_visible(self):
        plan = {
            "source_of_truth": {
                "requirements": [{"text": "Include demographic information", "isMandatory": True}]
            },
            "production": {},
        }
        checklist = _checklist(plan, {"review": []})
        self.assertIn("MANDATORY campaign requirement: Include demographic information", checklist)


if __name__ == "__main__":
    unittest.main()
