"""
Tests for utils/sentence_reconstruct.py  (Video Submission — Utility layer)

The reconstruction algorithm: turn Whisper word-timed segments into app-format
shadowing sentences, plus the manual-caption 1:1 path.

Split:
  [unit]        pure helpers — build_char_timeline, words_from_whisper,
                post_process, resolve_overlaps, apply_shadow_padding,
                reconstruct_sentence_for_manual
  [integration] reconstruct_sentences_from_whisper / segment_into_units run the
                fugashi tagger end-to-end (no clean unit seam), so they are
                exercised on fixed fake Whisper segments.

The module builds a fugashi Tagger at import, so the whole file skips if fugashi
(or its dictionary) is unavailable.
"""

import pytest

pytest.importorskip("fugashi", reason="fugashi not installed")

try:
    from utils.sentence_reconstruct import (
        MeaningUnit,
        WhisperWord,
        apply_shadow_padding,
        build_char_timeline,
        post_process,
        reconstruct_sentence_for_manual,
        reconstruct_sentences_from_whisper,
        resolve_overlaps,
        words_from_whisper,
    )
except Exception as exc:  # fugashi dictionary missing, etc.
    pytest.skip(f"sentence_reconstruct unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.video_submission, pytest.mark.sentence_algo]

SENTENCE_DICT_KEYS = {"text", "start", "end", "duration", "sentence_index"}


# --- fake faster-whisper objects (attribute access only; no library needed) ---
class _W:
    def __init__(self, word, start, end):
        self.word, self.start, self.end = word, start, end


class _Seg:
    def __init__(self, words, text="", start=0.0, end=0.0):
        self.words, self.text, self.start, self.end = words, text, start, end


# ===========================================================================
# build_char_timeline  [unit]
# ===========================================================================
@pytest.mark.unit
def test_build_char_timeline_maps_each_char_to_its_word():
    words = [
        WhisperWord("これ", 0.0, 0.3),
        WhisperWord("は", 0.3, 0.4),
        WhisperWord("テスト", 0.4, 0.9),
    ]
    full_text, char_word_idx = build_char_timeline(words)
    assert full_text == "これはテスト"
    assert char_word_idx == [0, 0, 1, 2, 2, 2]
    assert len(char_word_idx) == len(full_text)


# ===========================================================================
# words_from_whisper  [unit]
# ===========================================================================
@pytest.mark.unit
def test_words_from_whisper_flattens_and_marks_segment_end():
    segs = [_Seg(words=[_W("これは", 0.0, 0.5), _W("テスト", 0.5, 0.9)])]
    words = words_from_whisper(segs)
    assert [w.text for w in words] == ["これは", "テスト"]
    assert words[0].is_segment_end is False
    assert words[-1].is_segment_end is True  # last word of the segment


# ===========================================================================
# post_process  [unit]
# ===========================================================================
@pytest.mark.unit
def test_post_process_merges_too_short_unit():
    units = [
        MeaningUnit("これはテストの文", 0.0, 2.0),
        MeaningUnit("ね", 2.0, 2.2),
    ]  # length 1 < MIN_UNIT_LEN
    out = post_process(units)
    assert len(out) == 1
    assert out[0].text == "これはテストの文ね"
    assert out[0].start == 0.0 and out[0].end == 2.2


@pytest.mark.unit
def test_post_process_merges_unit_starting_with_forbidden_particle():
    units = [
        MeaningUnit("今日は学校に行く", 0.0, 2.0),
        MeaningUnit("のために勉強する", 2.0, 4.0),
    ]  # starts with の (NEVER_START)
    out = post_process(units)
    assert len(out) == 1
    assert out[0].end == 4.0


@pytest.mark.unit
def test_post_process_skips_merge_when_exceeding_hard_max():
    units = [
        MeaningUnit("あ" * 65, 0.0, 2.0),
        MeaningUnit("の" + "い" * 9, 2.0, 4.0),
    ]  # would merge, but 75 > HARD_MAX_LEN
    out = post_process(units)
    assert len(out) == 2


# ===========================================================================
# resolve_overlaps  [unit]
# ===========================================================================
@pytest.mark.unit
def test_resolve_overlaps_splits_at_midpoint():
    units = [MeaningUnit("A", 0.0, 2.0), MeaningUnit("B", 1.8, 3.0)]
    out = resolve_overlaps(units)
    assert out[0].end == pytest.approx(1.9)
    assert out[1].start == pytest.approx(1.9)


@pytest.mark.unit
def test_resolve_overlaps_fixes_degenerate_span():
    units = [MeaningUnit("A", 1.0, 1.0)]  # end <= start
    out = resolve_overlaps(units)
    assert out[0].end == pytest.approx(1.3)


# ===========================================================================
# apply_shadow_padding  [unit]
# ===========================================================================
@pytest.mark.unit
def test_apply_shadow_padding_adjusts_start_and_end():
    units = [MeaningUnit("A", 0.6, 1.0), MeaningUnit("B", 1.5, 2.0)]
    out = apply_shadow_padding(units, lead_in=0.25, lead_out=-0.09)
    assert out[0].start == pytest.approx(0.35)  # 0.6 - 0.25
    assert out[0].end == pytest.approx(0.91)  # 1.0 - 0.09
    assert out[1].start == pytest.approx(1.25)  # 1.5 - 0.25


@pytest.mark.unit
def test_apply_shadow_padding_start_clamped_at_zero_and_end_clamped_to_next():
    units = [MeaningUnit("A", 0.0, 2.0), MeaningUnit("B", 1.5, 3.0)]
    out = apply_shadow_padding(units, lead_in=0.25, lead_out=-0.09)
    assert out[0].start == pytest.approx(0.0)  # max(0, -0.25)
    assert out[0].end == pytest.approx(1.5)  # clamped to next unit's start


# ===========================================================================
# reconstruct_sentence_for_manual  [unit]
# ===========================================================================
@pytest.mark.unit
def test_reconstruct_manual_maps_and_rounds():
    captions = [
        {"index": 0, "text": "おはよう", "start": 0.0, "end": 1.2, "duration": 1.2},
        {"index": 1, "text": "元気ですか", "start": 1.2, "end": 3.0, "duration": 1.8},
    ]
    out = reconstruct_sentence_for_manual(captions)
    assert [s["sentence_index"] for s in out] == [0, 1]
    assert out[0] == {
        "text": "おはよう",
        "start": 0.0,
        "end": 1.2,
        "duration": 1.2,
        "sentence_index": 0,
    }


@pytest.mark.unit
def test_reconstruct_manual_empty_input():
    assert reconstruct_sentence_for_manual([]) == []


# ===========================================================================
# reconstruct_sentences_from_whisper / segment_into_units  [integration: fugashi]
# ===========================================================================
def _sample_segments(start=0.0):
    # "これはテストです。" <pause> "でも寒いです。"
    return [
        _Seg(
            words=[
                _W("これは", start + 0.0, start + 0.5),
                _W("テストです。", start + 0.5, start + 1.4),
            ]
        ),
        _Seg(
            words=[
                _W("でも", start + 1.9, start + 2.2),
                _W("寒いです。", start + 2.2, start + 2.9),
            ]
        ),
    ]


@pytest.mark.integration
def test_reconstruct_from_whisper_produces_wellformed_sentences():
    out = reconstruct_sentences_from_whisper(_sample_segments())
    assert out, "expected at least one sentence"
    for i, s in enumerate(out):
        assert set(s) == SENTENCE_DICT_KEYS
        assert s["sentence_index"] == i
        assert s["duration"] >= 0
    for a, b in zip(out, out[1:]):
        assert a["start"] <= b["start"]
        assert a["end"] <= b["start"] + 1e-6


@pytest.mark.integration
def test_reconstruct_from_whisper_empty_segments():
    assert reconstruct_sentences_from_whisper([]) == []


@pytest.mark.integration
def test_shadow_padding_pulls_first_start_earlier():
    plain = reconstruct_sentences_from_whisper(
        _sample_segments(start=0.6), shadow=False
    )
    padded = reconstruct_sentences_from_whisper(
        _sample_segments(start=0.6), shadow=True
    )
    assert padded[0]["start"] <= plain[0]["start"]
