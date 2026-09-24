export function validateCaptionRevision(revision, profile, expectedRulesHash = null) {
  const text = String(revision?.text || "");
  const failures = [];
  const contains = (value) => text.toLocaleLowerCase().includes(String(value || "").toLocaleLowerCase());
  const fail = (field, code, expected, actual = null) => failures.push({ field, code, expected, actual });
  for (const value of profile?.required_handles || []) if (!contains(value)) fail("handles", "required_handle_missing", value);
  for (const value of profile?.required_hashtags || []) if (!contains(value)) fail("hashtags", "required_hashtag_missing", value);
  for (const value of profile?.required_disclosures || []) if (!contains(value)) fail("disclosures", "required_disclosure_missing", value);
  for (const value of profile?.required_phrases || []) if (!contains(value)) fail("phrases", "required_phrase_missing", value);
  for (const value of profile?.cta || []) if (!contains(value)) fail("cta", "cta_missing", value);
  for (const value of profile?.prohibited_terms || []) if (contains(value)) fail("prohibited_terms", "prohibited_term_present", value);
  const limit = Number(profile?.caption_limit || 0);
  if (limit && text.length > limit) fail("text", "caption_too_long", limit, text.length);
  if (expectedRulesHash !== null && revision?.rules_hash !== expectedRulesHash) fail("rules_hash", "rules_hash_mismatch", expectedRulesHash, revision?.rules_hash);
  return { ok: failures.length === 0, status: failures.length ? "fail" : "pass", platform: profile?.platform, profile_version: profile?.version, failures };
}
