import unittest

from core.caption_compliance import validate_caption_revision
from core.caption_revisions import create_caption_revision, is_current_revision


PROFILE = {
    "platform": "instagram", "version": "platform-profile-v1", "caption_limit": 100,
    "required_handles": ["@brand"], "required_hashtags": ["#Campaign"],
    "required_disclosures": ["#ad"], "required_phrases": ["approved phrase"],
    "cta": ["https://example.com"], "prohibited_terms": ["guaranteed"],
}


class CaptionContractsTests(unittest.TestCase):
    def revision(self, text="approved phrase @brand #Campaign #ad https://example.com"):
        return create_caption_revision(text=text, fields={"hashtags": ["#Campaign", "#ad"]}, platform="instagram", revision_number=1, editor="tester", rules_hash="rules-1", platform_profile_version="platform-profile-v1")

    def test_revision_is_immutable_and_hashable(self):
        revision = self.revision()
        self.assertEqual(revision["character_count_method"], "unicode-codepoints-v1")
        self.assertTrue(revision["revision_id"].startswith("caption-"))
        self.assertTrue(is_current_revision(revision, revision_id=revision["revision_id"], caption_hash=revision["caption_hash"], rules_hash="rules-1"))
        self.assertFalse(is_current_revision(revision, revision_id="old", caption_hash=revision["caption_hash"], rules_hash="rules-1"))

    def test_valid_revision_passes(self):
        self.assertTrue(validate_caption_revision(self.revision(), PROFILE, expected_rules_hash="rules-1")["ok"])

    def test_deleting_each_mandatory_field_is_reported(self):
        base = self.revision()
        for needle, code in [("@brand", "required_handle_missing"), ("#Campaign", "required_hashtag_missing"), ("#ad", "required_disclosure_missing"), ("approved phrase", "required_phrase_missing"), ("https://example.com", "cta_missing")]:
            changed = dict(base, text=base["text"].replace(needle, ""))
            result = validate_caption_revision(changed, PROFILE, expected_rules_hash="rules-1")
            self.assertFalse(result["ok"], needle)
            self.assertIn(code, {item["code"] for item in result["failures"]})

    def test_prohibited_and_rules_hash_fail_without_provider_request(self):
        revision = self.revision("approved phrase @brand #Campaign #ad https://example.com guaranteed")
        result = validate_caption_revision(revision, PROFILE, expected_rules_hash="rules-2")
        codes = {item["code"] for item in result["failures"]}
        self.assertIn("prohibited_term_present", codes)
        self.assertIn("rules_hash_mismatch", codes)


if __name__ == "__main__":
    unittest.main()
