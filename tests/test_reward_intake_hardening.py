import unittest

from modules.reward_campaign.intake import _resolve_symbolic_asset


class RewardIntakeHardeningTests(unittest.TestCase):
    def test_symbolic_asset_resolves_from_explicit_campaign_mapping(self):
        plan = {
            "production": {
                "asset_mappings": {
                    "brandAsset": {"url": "https://cdn.example.test/brand.mp4"}
                }
            }
        }
        url, meta = _resolve_symbolic_asset(plan, "brandAsset")
        self.assertEqual(url, "https://cdn.example.test/brand.mp4")
        self.assertEqual(meta["mapping_source"], "campaign_plan")

    def test_symbolic_asset_resolves_normalized_key(self):
        plan = {
            "production": {
                "asset_mappings": {
                    "brand_asset": "https://cdn.example.test/brand.mp4"
                }
            }
        }
        url, _ = _resolve_symbolic_asset(plan, "brandAsset")
        self.assertEqual(url, "https://cdn.example.test/brand.mp4")

    def test_unknown_symbolic_asset_is_unresolved_without_inventing_url(self):
        url, meta = _resolve_symbolic_asset({"production": {}}, "brandAsset")
        self.assertIsNone(url)
        self.assertEqual(meta["mapping_key"], "brandasset")


if __name__ == "__main__":
    unittest.main()
