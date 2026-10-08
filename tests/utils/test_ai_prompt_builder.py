import pytest

from utils.ai_prompt_builder import (
    build_explanation_prompt,
    build_pronunciation_feedback_prompt,
)

pytestmark = [pytest.mark.unit, pytest.mark.word_lookup]


def _explanation_prompt(**overrides):
    kwargs = {
        "surface_form": "食べる",
        "pos": ["verb", "ichidan"],
        "meanings": ["to eat", "to live on"],
        "context_sentence": "毎日ご飯を食べる。",
    }
    kwargs.update(overrides)
    return build_explanation_prompt(**kwargs)


def test_build_explanation_prompt_includes_word_data_and_context():
    prompt = _explanation_prompt()

    assert "You are a Japanese teacher" in prompt
    assert "- Word as seen: 食べる" in prompt
    assert "- Part of speech: verb, ichidan" in prompt
    assert (
        "- Dictionary meanings (or Google-translated meaning if POS = web-translate): "
        "to eat / to live on"
    ) in prompt
    assert "CONTEXT SENTENCE (from a Japanese YouTube video):\n毎日ご飯を食べる。" in prompt


def test_build_explanation_prompt_uses_unknown_for_missing_dictionary_data():
    prompt = _explanation_prompt(surface_form="かな", pos=[], meanings=[], context_sentence="本当かな。")

    assert "- Word as seen: かな" in prompt
    assert "- Part of speech: unknown" in prompt
    assert (
        "- Dictionary meanings (or Google-translated meaning if POS = web-translate): unknown"
    ) in prompt
    assert "本当かな。" in prompt


def test_build_explanation_prompt_asks_for_contextual_explanation_of_the_word():
    prompt = _explanation_prompt()

    assert (
        'In 2-3 short sentences, explain what "食べる" means and how it is being used '
        "in the context sentence above."
    ) in prompt
    assert "say what the word is doing in THIS sentence" in prompt


def test_build_explanation_prompt_targets_beginners_without_jargon():
    prompt = _explanation_prompt()

    assert "understandable by ANY learner, including a complete beginner" in prompt
    assert "Use plain, everyday English" in prompt
    assert "Avoid linguistic jargon" in prompt
    assert "add a 3-6 word plain explanation the first time" in prompt


def test_build_explanation_prompt_grounds_claims_in_the_input():
    prompt = _explanation_prompt()

    assert "Base every claim on the context sentence and the provided meanings" in prompt
    assert "Do NOT invent facts or usage settings" in prompt


def test_build_explanation_prompt_keeps_grammar_words_register_neutral():
    prompt = _explanation_prompt(surface_form="は", pos=["particle"], meanings=["topic marker"])

    assert (
        'If "は" is a particle, auxiliary, or other grammar word, it is register-neutral'
    ) in prompt
    assert "do NOT assign it a register or a setting" in prompt


def test_build_explanation_prompt_defines_mismatch_flag_and_confidence_levels():
    prompt = _explanation_prompt()

    # Field names must match the Pydantic response_schema used by the Gemini call.
    assert "set dictionary_mismatch_detected = true" in prompt
    assert '"high" if the dictionary matches the context' in prompt
    assert '"medium" if you inferred the meaning from context' in prompt
    assert '"low" if the tokenization looks wrong' in prompt


def test_build_explanation_prompt_requests_two_examples_in_new_situations():
    prompt = _explanation_prompt()

    assert (
        'Give exactly 2 natural Japanese example sentences using "食べる" in DIFFERENT '
        "situations from the context sentence."
    ) in prompt
    assert "kana-only reading (no kanji) and an English translation" in prompt


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
