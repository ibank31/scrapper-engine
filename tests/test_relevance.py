import unittest

from core.relevance import check_candidate


class RelevanceTest(unittest.TestCase):
    def setUp(self):
        self.plan = {"campaign": {"title": "Boxabl Official Clipping"}, "source_of_truth": {"description": "Boxabl makes foldable homes and the Casita modular home."}}

    def test_boxabl_topic_passes(self):
        result = check_candidate(self.plan, {"text": "This foldable home is the Boxabl Casita."})
        self.assertEqual(result["status"], "pass")

    def test_starship_topic_is_blocked(self):
        result = check_candidate(self.plan, {"text": "Starbase and Starship are trying to reach orbit."})
        self.assertEqual(result["status"], "blocked")

    def test_forgegui_roblox_topic_passes(self):
        plan = {"campaign": {"title": "ForgeGUI Clipping", "brand": "BloxClips"}, "source_of_truth": {"description": "ForgeGUI is an AI tool for Roblox developers."}}
        result = check_candidate(plan, {"text": "I will sketch my idea in forge G-U-I for my Roblox game and convert it into 3D."})
        self.assertEqual(result["status"], "pass")


if __name__ == "__main__":
    unittest.main()
