import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
APP = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")


class UILanguageTests(unittest.TestCase):
    def test_backend_states_have_plain_language_mapping(self):
        for token in ("unknown", "scheduled", "failed", "approved_for_manual_post", "capacity_preflight_failed"):
            self.assertIn(token, APP)
        self.assertIn("friendlyError", APP)
        self.assertIn("friendlyOperation", APP)
        self.assertIn("Coba lagi", APP)
        self.assertIn("Cek status", APP)

    def test_main_flow_explains_user_actions(self):
        for phrase in ("Pilih campaign", "Proses berjalan", "Tinjau video", "ACC", "render ulang", "submit manual ke Whop"):
            self.assertIn(phrase, HTML + APP)
        self.assertIn("how-it-works", HTML)
        self.assertIn("review-guide", HTML)
        self.assertIn("buffer-safe-note", APP)

    def test_technical_status_is_not_primary_review_copy(self):
        self.assertIn("Pemeriksaan dasar lolos", APP)
        self.assertIn("Status pengiriman Buffer", APP)
        self.assertIn("slot antrean berikutnya", APP)
        self.assertNotIn("AI processing", APP)
        self.assertNotIn("Candidate terverifikasi", APP)


if __name__ == "__main__": unittest.main()
