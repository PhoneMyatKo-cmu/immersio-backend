"""
Tests for utils/dictionary_lookup_helpers.py  (Video Submission — Utility layer)

Functions under test:
  lookup_word_full  — public entry: surface/base lookup against the real JMdict
                      index, with a Google-Translate fallback when no meaning is
                      found; attaches a romaji reading and a JLPT tier.
  get_jlpt_tier     — JLPT tier lookup function.

INTEGRATION: loads the real JMdict index (lru-cached) and uses cutlet + fugashi.
google_translate is mocked so no network/credentials are needed and the fallback
path is deterministic. The module skips if those deps (or the data file) are
unavailable, so it never breaks collection elsewhere.
"""

import pytest

pytest.importorskip("fugashi", reason="fugashi not installed")
pytest.importorskip("cutlet", reason="cutlet not installed")

try:
    from utils.dictionary_lookup_helpers import get_jlpt_tier, lookup_word_full
except Exception as exc:  # missing JMdict data file, GCT key at import, etc.
    pytest.skip(
        f"dictionary_lookup_helpers unavailable: {exc}", allow_module_level=True
    )

pytestmark = [pytest.mark.integration, pytest.mark.video_submission, pytest.mark.lookup]

VALID_TIERS = {"N1", "N2", "N3", "N4", "N5", "UNKNOWN"}


# ---------------------------------------------------------------------------
# lookup_word_full
# ---------------------------------------------------------------------------
def test_surface_form_hit_returns_full_enrichment():
    result = lookup_word_full(("猫", "猫"))
    assert result["found"] is True
    assert isinstance(result["meanings"], list) and result["meanings"]
    for group in result["meanings"]:
        assert set(group) == {"pos", "meanings"}
    assert isinstance(result["romanji_reading"], str) and result["romanji_reading"]
    assert result["jlpt_tier"] in VALID_TIERS


def test_conjugated_form_resolves_via_base_form():
    # surface "食べ" is a conjugated stem (usually not an index entry);
    # the dictionary base form "食べる" should drive the lookup.
    result = lookup_word_full(("食べ", "食べる"))
    assert result["found"] is True
    assert any(g["meanings"] for g in result["meanings"])


def test_missing_word_falls_back_to_translation(monkeypatch):
    monkeypatch.setattr(
        "utils.dictionary_lookup_helpers.google_translate",
        lambda surface: ["coinage"],
    )
    # Japanese (katakana) but not a real JMdict entry -> triggers the fallback.
    result = lookup_word_full(("ガギグゲゴ", "ガギグゲゴ"))
    assert result["found"] is True
    assert result["meanings"] == [{"pos": "web_translate", "meanings": ["coinage"]}]


def test_non_japanese_surface_short_circuits_to_not_found():
    result = lookup_word_full(("hello", "hello"))
    assert result["found"] is False
    assert result["meanings"] == [{"pos": None, "meanings": None}]
    assert result["romanji_reading"] is None
    assert result["jlpt_tier"] == "UNKNOWN"


def test_hit_produces_romaji_reading():
    result = lookup_word_full(("猫", "猫"))
    assert isinstance(result["romanji_reading"], str)
    assert result["romanji_reading"].strip() != ""


# ---------------------------------------------------------------------------
# get_jlpt_tier
# ---------------------------------------------------------------------------
def test_jlpt_tier_returns_valid_label_for_known_word():
    assert get_jlpt_tier("猫") in VALID_TIERS


def test_jlpt_tier_unknown_for_unlisted_word():
    assert get_jlpt_tier("ガギグゲゴ") == "UNKNOWN"


# def test_jlpt_tier_uses_lemma_normalize_fallback(monkeypatch):
#     # No need in test plan
#     # Use a controlled index so the test exercises the LEMMA_NORMALIZE branch
#     # deterministically, independent of the real JMdict contents:
#     #   - the normalized form する has a tier
#     #   - the un-normalized kanji form 為る is absent
#     # so get_jlpt_tier("為る") must fall back through LEMMA_NORMALIZE to する.
#     fake_index = ({}, {"する": "N5"})
#     monkeypatch.setattr(
#         "utils.dictionary_lookup_helpers._load_index", lambda: fake_index
#     )
#     assert get_jlpt_tier("為る") == "N5"  # normalized 為る -> する -> N5
#     assert get_jlpt_tier("存在しない語") == "UNKNOWN"  # not present, not normalizable
