import pytest

from utils.ai_prompt_builder import (
    build_explanation_prompt,
    build_pronunciation_feedback_prompt,
)

pytestmark = [pytest.mark.unit, pytest.mark.word_lookup]


def test_build_explanation_prompt_includes_word_data_and_context():
    prompt = build_explanation_prompt(
        surface_form="食べる",
        pos=["verb", "ichidan"],
        meanings=["to eat", "to live on"],
        context_sentence="毎日ご飯を食べる。",
    )

    assert "You are a Japanese language teacher" in prompt
    assert "- Word as seen: 食べる" in prompt
    assert "- Part of speech: verb, ichidan" in prompt
    assert (
        "- Provided dictionary meanings/ Google Tranlated Meaning if POS=web-translate: "
        "to eat / to live on"
    ) in prompt
    assert "毎日ご飯を食べる。" in prompt
    assert 'Explain in 2-3 sentences how "食べる" is used' in prompt
    assert 'Generate exactly 2 distinct, natural Japanese example sentences' in prompt


def test_build_explanation_prompt_uses_unknown_for_missing_dictionary_data():
    prompt = build_explanation_prompt(
        surface_form="かな",
        pos=[],
        meanings=[],
        context_sentence="本当かな。",
    )

    assert "- Word as seen: かな" in prompt
    assert "- Part of speech: unknown" in prompt
    assert (
        "- Provided dictionary meanings/ Google Tranlated Meaning if POS=web-translate: "
        "unknown"
    ) in prompt
    assert "本当かな。" in prompt


def test_build_pronunciation_feedback_prompt_includes_metrics_and_inputs():
    prompt = build_pronunciation_feedback_prompt(
        cer=0.12345,
        pitch_score=87.65,
        user_katakana="コンチハ",
        caption_katakana="コンニチハ",
        user_pitch=[0.1, 0.2],
        reference_pitch=[0.3, 0.4],
        caption="こんにちは",
    )

    assert "You are a Japanese pronunciation coach." in prompt
    assert "- Character Error Rate (CER): 0.123" in prompt
    assert "- Pitch Similarity Score: 87.7/100" in prompt
    assert "- Learner pronunciation (katakana): コンチハ" in prompt
    assert "- Target pronunciation (katakana): コンニチハ" in prompt
    assert "- Target sentence: こんにちは" in prompt
    assert "- Learner pitch contour: [0.1, 0.2]" in prompt
    assert "- Reference pitch contour: [0.3, 0.4]" in prompt


def test_build_pronunciation_feedback_prompt_requests_expected_json_schema():
    prompt = build_pronunciation_feedback_prompt(
        cer=0.05,
        pitch_score=91.0,
        user_katakana="コンニチハ",
        caption_katakana="コンニチハ",
        user_pitch=[],
        reference_pitch=[],
        caption="こんにちは",
    )

    assert "Output JSON only using this schema" in prompt
    assert '"summary": "short overall assessment"' in prompt
    assert '"pronunciation_feedback": [' in prompt
    assert '"pitch_feedback": [' in prompt
    assert '"strengths": [' in prompt
    assert '"improvements": [' in prompt
    assert "If CER is very low (< 0.1), praise pronunciation accuracy." in prompt
    assert "If pitch score is high (> 85), praise pitch accent accuracy." in prompt
