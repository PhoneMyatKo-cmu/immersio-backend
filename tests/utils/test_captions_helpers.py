"""
Tests for utils/captions_helpers.py  (Video Submission — Utility layer)

Functions under test:
  get_line_level_captions   — json3 events -> normalized line-level snippets
  normalize_captions_fragments — overlap clipping + end/duration
  is_japanese               — kana/kanji detection
  is_content_word           — lookup-able? (True for Japanese non-punctuation)
  process_captions          — normalize then tokenize (fugashi)

The module instantiates a fugashi Tagger at import time, so the whole file is
skipped if fugashi (and its dictionary) is unavailable.
"""

import pytest

pytest.importorskip("fugashi", reason="fugashi tokenizer not installed")

from utils.captions_helpers import (  # noqa: E402  (import after importorskip)
    get_line_level_captions,
    is_content_word,
    is_japanese,
    normalize_captions_fragments,
    process_captions,
)

pytestmark = [
    pytest.mark.unit,
    pytest.mark.video_submission,
    pytest.mark.caption_helper,
]


# ---------------------------------------------------------------------------
# get_line_level_captions
# ---------------------------------------------------------------------------
def test_aggregates_sub_segments_into_one_line():
    data = {
        "events": [
            {
                "tStartMs": 0,
                "dDurationMs": 1500,
                "segs": [{"utf8": "今日は"}, {"utf8": "いい天気"}],
            },
        ]
    }
    lines = get_line_level_captions(data)
    assert len(lines) == 1
    assert lines[0]["text"] == "今日はいい天気"


def test_skips_events_without_segs():
    data = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "ある"}]},
            {"tStartMs": 1000, "dDurationMs": 1000},  # no "segs" key
        ]
    }
    lines = get_line_level_captions(data)
    assert [ln["text"] for ln in lines] == ["ある"]


def test_skips_blank_and_newline_only_events():
    data = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 500, "segs": [{"utf8": "\n"}]},
            {"tStartMs": 500, "dDurationMs": 500, "segs": [{"utf8": "   "}]},
            {"tStartMs": 1000, "dDurationMs": 500, "segs": [{"utf8": "ねこ"}]},
        ]
    }
    lines = get_line_level_captions(data)
    assert [ln["text"] for ln in lines] == ["ねこ"]


def test_unescapes_html_entities():
    data = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 500, "segs": [{"utf8": "A&amp;B"}]},
        ]
    }
    lines = get_line_level_captions(data)
    assert lines[0]["text"] == "A&B"


# Not In Test Plan
def test_collapses_internal_whitespace():
    data = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 500, "segs": [{"utf8": "今日は    いい"}]},
        ]
    }
    lines = get_line_level_captions(data)
    assert lines[0]["text"] == "今日は いい"


def test_converts_milliseconds_to_seconds():
    data = {
        "events": [
            {"tStartMs": 1500, "dDurationMs": 2000, "segs": [{"utf8": "テスト"}]},
        ]
    }
    line = get_line_level_captions(data)[0]
    assert line["start"] == 1.5
    assert line["duration"] == 2.0


# Not In test plan
def test_deduplicates_rolling_captions():
    # prefix-growth line replaces the previous; a contained line is skipped.
    data = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "これは"}]},
            {"tStartMs": 1000, "dDurationMs": 1000, "segs": [{"utf8": "これはテスト"}]},
            {"tStartMs": 2000, "dDurationMs": 1000, "segs": [{"utf8": "これは"}]},
        ]
    }
    lines = get_line_level_captions(data)
    assert len(lines) == 1
    assert lines[0]["text"] == "これはテスト"


# Not In Test Plan
def test_reindexes_contiguously_after_dedup():
    data = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "いち"}]},
            {"tStartMs": 1000, "dDurationMs": 1000, "segs": [{"utf8": "に"}]},
            {"tStartMs": 2000, "dDurationMs": 1000, "segs": [{"utf8": "さん"}]},
        ]
    }
    lines = get_line_level_captions(data)
    assert [ln["index"] for ln in lines] == [0, 1, 2]


# Not In Test Plan
def test_empty_events_returns_empty_list():
    assert get_line_level_captions({"events": []}) == []
    assert get_line_level_captions({}) == []


# ---------------------------------------------------------------------------
# normalize_captions_fragments
# ---------------------------------------------------------------------------
def test_clips_overlapping_timestamps_and_adds_end_duration():
    fragments = [
        {"text": "a", "start": 0.0, "duration": 2.0},  # ends at 2.0, overlaps next
        {"text": "b", "start": 1.5, "duration": 2.0},
    ]
    out = normalize_captions_fragments(fragments, min_gap=0.05)
    # first frag end clipped to next_start - min_gap = 1.45
    assert out[0]["end"] == 1.45
    assert out[0]["duration"] == 1.45
    # last frag keeps its full duration
    assert out[1]["start"] == 1.5
    assert out[1]["end"] == 3.5
    assert out[1]["duration"] == 2.0


# Not In Test Plan
def test_non_overlapping_fragments_unchanged():
    fragments = [
        {"text": "a", "start": 0.0, "duration": 1.0},
        {"text": "b", "start": 2.0, "duration": 1.0},
    ]
    out = normalize_captions_fragments(fragments)
    assert out[0]["end"] == 1.0
    assert out[0]["duration"] == 1.0


# Not In Test Plan
def test_normalize_does_not_mutate_input():
    fragments = [{"text": "a", "start": 0.0, "duration": 1.0}]
    normalize_captions_fragments(fragments)
    assert "end" not in fragments[0]  # original untouched (deepcopy)


# ---------------------------------------------------------------------------
# is_japanese
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text, expected",
    [
        ("猫", True),  # kanji
        ("ねこ", True),  # hiragana
        ("ネコ", True),  # katakana
        ("hello", False),
        ("12345", False),
        ("", False),
    ],
)
def test_is_japanese(text, expected):
    assert is_japanese(text) is expected


# ---------------------------------------------------------------------------
# is_content_word  (only reads .surface; a stub node is sufficient)
# ---------------------------------------------------------------------------
class _StubNode:
    def __init__(self, surface):
        self.surface = surface


def test_content_word_true_for_japanese():
    assert is_content_word(_StubNode("猫")) is True
    assert is_content_word(_StubNode("は")) is True  # particles are lookup-able now


def test_content_word_false_for_punctuation():
    for mark in ("。", "、", "！", "？", "…"):
        assert is_content_word(_StubNode(mark)) is False


def test_content_word_false_for_non_japanese():
    assert is_content_word(_StubNode("hello")) is False
    assert is_content_word(_StubNode("123")) is False


# ---------------------------------------------------------------------------
# process_captions  (normalize + tokenize via fugashi)
# ---------------------------------------------------------------------------
def test_process_captions_adds_tokens_and_normalizes():
    raw = [{"index": 0, "text": "猫が好き", "start": 0.0, "duration": 2.0}]
    out = process_captions(raw)
    cap = out[0]
    # normalization added end/duration
    assert cap["end"] == 2.0
    assert cap["duration"] == 2.0
    # tokenization added a non-empty tokens list with the expected fields
    assert cap["tokens"], "expected at least one token"
    for tok in cap["tokens"]:
        assert set(tok) == {
            "surface",
            "base_form",
            "pos",
            "pos_detail",
            "is_content_word",
        }


def test_process_captions_flags_punctuation_non_content():
    raw = [{"index": 0, "text": "猫。", "start": 0.0, "duration": 1.0}]
    tokens = process_captions(raw)[0]["tokens"]
    by_surface = {t["surface"]: t["is_content_word"] for t in tokens}
    assert by_surface.get("。") is False
    # the Japanese word token is content
    assert any(v is True for k, v in by_surface.items() if k != "。")
