"""
Tests for utils/video_validation_helpers.py
Covers: docs/test_plan.md §4.1 (EVI), §4.2 (SUIT), §4.3 (DIFF).

These are pure functions (no I/O), so the module is unit-tested and runs anywhere.
Use it as the pattern for the other layers.

NOTE: compute_difficulty (MD-36) is currently commented out in
utils/video_validation_helpers.py, so the DIFF-* cases are kept but skipped.
Re-enable the import and the test when it is restored.
"""

import pytest

from utils.video_validation_helpers import (
    check_video_japanese_suitability,
    extract_video_id,
)

pytestmark = [pytest.mark.unit, pytest.mark.video_submission]


# ---------------------------------------------------------------------------
# extract_video_id (MD-34) — EVI
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "case_id, url, expected",
    [
        ("EVI-01", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("EVI-02", "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("EVI-03", "https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("EVI-04", "https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("EVI-05", "youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("EVI-06", "https://youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("EVI-07", "  https://youtu.be/dQw4w9WgXcQ  ", "dQw4w9WgXcQ"),
        ("EVI-08", "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s", "dQw4w9WgXcQ"),
        ("EVI-09", "https://youtu.be/a_b-c1D2E3F", "a_b-c1D2E3F"),
        ("EVI-10", "https://vimeo.com/123456789", None),
        ("EVI-11a", "", None),
        ("EVI-11b", "   ", None),
        ("EVI-12", "https://www.youtube.com/watch?v=abc", None),
        ("EVI-14", "https://youtu.be/dQw4w9WgXcQEXTRA", "dQw4w9WgXcQ"),
    ],
)
def test_extract_video_id(case_id, url, expected):
    assert extract_video_id(url) == expected


# ---------------------------------------------------------------------------
# check_video_japanese_suitability (MD-35) — SUIT
# ---------------------------------------------------------------------------
def _meta(default_language="ja", default_audio_language="ja"):
    return {
        "default_language": default_language,
        "default_audio_language": default_audio_language,
    }


def _track(language="ja", kind="standard"):
    return {"snippet": {"language": language, "trackKind": kind}}


def test_japanese_suitability_01_japanese_captions_and_audio():
    r = check_video_japanese_suitability(_meta(), [_track()])
    assert r["is_suitable"] is True
    assert r["reason"] is None


def test_japanese_suitability_03_no_japanese_captions():
    r = check_video_japanese_suitability(_meta(), [_track(language="en")])
    assert r["is_suitable"] is False
    assert r["reason"] == "No Japanese Captions for this video."
    assert r["has_japanese_captions"] is False


def test_japanese_suitability_04_non_japanese_audio():
    r = check_video_japanese_suitability(
        _meta(default_language="en", default_audio_language="en"), [_track()]
    )
    assert r["is_suitable"] is False
    assert r["reason"] == "Audio Language is not Japanese"


def test_suit_japanese_suitability_05_ja_jp_locale_counts_as_japanese():
    r = check_video_japanese_suitability(_meta(), [_track(language="ja-JP")])
    assert r["is_suitable"] is True


def test_japanese_suitability_suit_06_missing_language_metadata_does_not_crash():
    r = check_video_japanese_suitability(
        _meta(default_language=None, default_audio_language=None), [_track()]
    )
    assert r["is_suitable"] is False  # treated as non-Japanese
