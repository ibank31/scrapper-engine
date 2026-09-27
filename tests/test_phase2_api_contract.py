import unittest
from pathlib import Path


API = (Path(__file__).parents[1] / "cloudflare" / "api.js").read_text(encoding="utf-8")


class Phase2ApiContractTests(unittest.TestCase):
    def test_revision_endpoint_is_immutable_and_versioned(self):
        self.assertIn("caption-revisions", API)
        self.assertIn("INSERT INTO caption_revisions", API)
        self.assertIn("ON CONFLICT(id) DO NOTHING", API)
        self.assertIn("caption_revision_missing", API)

    def test_approval_and_buffer_use_compliance_before_provider_mutation(self):
        self.assertIn("caption_compliance_failed", API)
        buffer_block = API[API.index('parts[3] === "buffer"'):]
        compliance_position = buffer_block.index("const compliance = validateCaptionRevision")
        provider_position = buffer_block.index("const data = await bufferRequest")
        self.assertLess(compliance_position, provider_position)

    def test_preview_upserts_keep_source_hash_column_binding(self):
        marker = 'INSERT INTO previews (id,job_id,rank,status,tier,candidate_id,source_asset_id,source_hash,video_key'
        start = API.index(marker)
        end = API.index('\\").bind(preview.id', start)
        sql = API[start:end]
        columns = sql.split('VALUES', 1)[0].split('(', 1)[1].rstrip()
        columns_count = len(columns.split(','))
        values = sql.split('VALUES', 1)[1].split(')', 1)[0].strip().lstrip('(')
        values_count = len(values.split(','))
        self.assertEqual(columns_count, values_count)
        rerender = API.index('INSERT INTO previews (id,job_id,rank,status,tier,candidate_id,source_asset_id,source_hash,validation_json')
        rer_end = API.index('\\").bind(newId', rerender)
        rer_sql = API[rerender:rer_end]
        rer_columns = len(rer_sql.split('VALUES', 1)[0].split('(', 1)[1].rstrip().split(','))
        rer_values = len(rer_sql.split('VALUES', 1)[1].split(')', 1)[0].strip().lstrip('(').split(','))
        self.assertEqual(rer_columns, rer_values)
        self.assertIn('source_hash=excluded.source_hash', sql)

    def test_sound_verification_is_not_created_by_buffer_route(self):
        self.assertNotIn("status='verified'", API[API.index('parts[3] === "buffer"'):])
        self.assertIn("platform_profile_json", API)
        self.assertIn("subtitle_delivery_json", API)
        self.assertIn("sound_tags_json", API)


if __name__ == "__main__":
    unittest.main()
