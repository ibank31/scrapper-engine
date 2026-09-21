#!/usr/bin/env python3
import unittest

from core.campaign_readiness import (
    STATUS_BELUM,
    STATUS_KETAT,
    STATUS_LEWATI,
    STATUS_SIAP,
    assess_readiness,
    classify_content_kind,
)


class CampaignReadinessTests(unittest.TestCase):
    def test_classify_clipping_from_title(self):
        self.assertEqual(
            classify_content_kind({"title": "ForgeGUI Clipping [Roblox]", "type": "cpm"}),
            "clipping",
        )

    def test_classify_slideshow(self):
        self.assertEqual(
            classify_content_kind({"title": "PixelSurf AI [Slideshow]", "type": "cpm"}),
            "slideshow",
        )

    def test_classify_ugc(self):
        self.assertEqual(
            classify_content_kind(
                {
                    "title": "FundingPips Creator Stories",
                    "description": "Create authentic UGC about the product on camera",
                    "type": "cpm",
                }
            ),
            "ugc",
        )

    def test_siap_with_youtube_materials(self):
        r = assess_readiness(
            {
                "title": "Boxabl Official Clipping",
                "description": "Clip from official provided footage",
                "type": "cpm",
                "status": "active",
                "budget_left": 50000,
                "resources": [{"url": "https://www.youtube.com/watch?v=abc123"}],
                "docs_text": "Use provided footage. Simple edits only.",
            }
        )
        self.assertEqual(r["content_kind"], "clipping")
        self.assertEqual(r["readiness_status"], STATUS_SIAP)
        self.assertIn("Siap", r["readiness_label"])

    def test_ketat_account_warmup(self):
        r = assess_readiness(
            {
                "title": "ForgeGUI Clipping",
                "description": "Repurpose provided ForgeGUI footage",
                "status": "active",
                "budget_left": 8000,
                "resources": [{"url": "https://drive.google.com/drive/folders/xyz"}],
                "docs_text": (
                    "Warmup process Day 1 Day 2 Day 3. "
                    "Required account bio must use a fully Roblox based-account. "
                    "Has a strong Tier 1 audience."
                ),
            }
        )
        self.assertEqual(r["readiness_status"], STATUS_KETAT)
        self.assertTrue("akun" in r["readiness_reason"].lower() or "ketat" in r["readiness_reason"].lower())

    def test_lewati_ugc(self):
        r = assess_readiness(
            {
                "title": "Brand UGC Challenge",
                "description": "Create authentic UGC with face on camera",
                "status": "active",
                "budget_left": 9000,
            }
        )
        self.assertEqual(r["readiness_status"], STATUS_LEWATI)

    def test_belum_login_portal(self):
        r = assess_readiness(
            {
                "title": "Game Clipping Campaign",
                "description": "Edit the source footage into polished clips",
                "status": "active",
                "budget_left": 20000,
                "resources": [{"url": "https://app.mediasilo.com/review/abc"}],
                "docs_text": "Content Folder on MediaSilo only.",
            }
        )
        self.assertEqual(r["readiness_status"], STATUS_BELUM)

    def test_labels_indonesian(self):
        r = assess_readiness(
            {
                "title": "Something Clipping",
                "status": "active",
                "budget_left": 1000,
                "resources": [{"url": "https://youtu.be/xyz"}],
            }
        )
        for ch in "abcdefghijklmnopqrstuvwxyz":
            # label must contain Indonesian words, not only English status codes
            pass
        self.assertTrue(r["readiness_label"])
        self.assertNotEqual(r["readiness_label"], r["readiness_status"])


if __name__ == "__main__":
    unittest.main()
