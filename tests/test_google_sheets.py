import unittest
from unittest.mock import patch

from core.google_sheets import discover_sheet_assets, extract_sheet_id, fetch_sheet_rows, is_google_sheet_url


SHEET_URL = "https://docs.google.com/spreadsheets/d/1eX0vqF73N9x2gtkRbalnKMHRd3nbd-CEv0Rt4D2glM4/edit?usp=sharing"


class GoogleSheetsAssetResolverTest(unittest.TestCase):
    def test_detects_google_sheet_and_id(self):
        self.assertTrue(is_google_sheet_url(SHEET_URL))
        self.assertEqual(extract_sheet_id(SHEET_URL), "1eX0vqF73N9x2gtkRbalnKMHRd3nbd-CEv0Rt4D2glM4")

    @patch("core.google_sheets.google_drive_configured", return_value=False)
    @patch("core.google_sheets.fetch_bytes")
    def test_reads_public_csv_export(self, mock_fetch, _mock_configured):
        mock_fetch.return_value = (
            b"Clip Link,Hype Level,Suggested Hook\n"
            b"https://drive.google.com/file/d/abc123456789/view,HIGH,TOP HIT\n"
        )
        rows = fetch_sheet_rows(SHEET_URL)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Hype Level"], "HIGH")
        mock_fetch.assert_called_once()

    def test_discovers_media_urls_and_preserves_tracker_priority(self):
        rows = [
            {
                "Clip Link": "https://drive.google.com/file/d/low123456789/view",
                "Hype Level": "LOW",
                "Suggested Hook": "low",
            },
            {
                "Clip Link": "https://drive.google.com/file/d/high123456789/view",
                "Hype Level": "HIGH",
                "Suggested Hook": "high",
            },
            {
                "Clip Link": "https://www.instagram.com/p/not-a-source/",
                "Hype Level": "INSANE",
                "Suggested Hook": "ignore",
            },
        ]
        assets = discover_sheet_assets(rows)
        self.assertEqual(len(assets), 2)
        self.assertEqual(assets[0]["url"], "https://drive.google.com/file/d/high123456789/view")
        self.assertEqual(assets[0]["metadata"]["Suggested Hook"], "high")
        self.assertEqual(assets[0]["row_number"], 3)


if __name__ == "__main__":
    unittest.main()
