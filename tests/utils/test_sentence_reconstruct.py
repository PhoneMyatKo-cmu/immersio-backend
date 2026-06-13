"""
Tests for utils/sentence_reconstruct.py
Covers: docs/test_plan.md
  §4.6 RSM   reconstruct_sentence_for_manual            [unit]
  §4.7 SBP   score_break_point                          [unit]
       SAFE  is_safe_to_break_after                     [unit]
       PP    post_process                               [unit]
       RO    resolve_overlaps                           [unit]
       ASP   apply_shadow_padding                       [unit]
       BCT   build_char_timeline                        [unit]
  §4.9 RSW   reconstruct_sentences_from_whisper / segment_into_units [integration]

RSM and the pure post-processors are unit-testable directly. The fugashi-backed
helpers (SBP/SAFE) and the full pipeline (RSW) run the tokenizer; RSW is verified
end-to-end (segment_into_units has no clean unit seam).
"""

import pytest

pytestmark = [pytest.mark.video_submission]


@pytest.mark.unit
def test_rsm_03_empty_input():
    from utils.sentence_reconstruct import reconstruct_sentence_for_manual
    assert reconstruct_sentence_for_manual([]) == []


@pytest.mark.unit
@pytest.mark.skip(reason="TODO RSM-01/02: 1:1 mapping + index order (FX-VS-MANUAL-CAPS)")
def test_rsm_mapping():
    ...


@pytest.mark.unit
@pytest.mark.skip(reason="TODO BCT-01/02: build_char_timeline (FX-VS-WORDS)")
def test_bct_build_char_timeline():
    from utils.sentence_reconstruct import build_char_timeline, WhisperWord
    words = [WhisperWord("これ", 0.0, 0.3), WhisperWord("は", 0.3, 0.4),
             WhisperWord("テスト", 0.4, 0.9)]
    text, idx = build_char_timeline(words)
    assert text == "これはテスト"
    assert idx == [0, 0, 1, 2, 2, 2]


@pytest.mark.unit
@pytest.mark.skip(reason="TODO PP / RO / ASP: pure post-processors (FX-VS-UNITS-*)")
def test_post_processors():
    ...


@pytest.mark.unit
@pytest.mark.skip(reason="TODO SBP / SAFE: break scoring + guards (fugashi tokens)")
def test_break_scoring():
    ...


@pytest.mark.integration
@pytest.mark.skip(reason="TODO RSW-01..04: full pipeline on FX-VS-WHISPER-SEG / GOLDEN")
def test_rsw_pipeline():
    ...
