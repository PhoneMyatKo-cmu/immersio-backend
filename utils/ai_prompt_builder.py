def build_explanation_prompt(
    surface_form: str,
    pos: list[str],
    meanings: list[str],
    context_sentence: str,
) -> str:
    """
    Build a structured prompt that:
    - Grounds Gemini in provided dictionary data (reduces hallucination)
    - Asks for contextual usage explanation
    - Requests exactly 2 example sentences
    - Handles edge cases where MeCab output is unusual
    """

    meanings_text = " / ".join(meanings) if meanings else "unknown"
    pos_text = ", ".join(pos) if pos else "unknown"

    return f"""You are a Japanese teacher explaining one word as it is used in a specific sentence. Your explanation must be understandable by ANY learner, including a complete beginner.

WORD INFORMATION:
- Word as seen: {surface_form}
- Part of speech: {pos_text}
- Dictionary meanings (or Google-translated meaning if POS = web-translate): {meanings_text}

CONTEXT SENTENCE (from a Japanese YouTube video):
{context_sentence}

TASK
In 2-3 short sentences, explain what "{surface_form}" means and how it is being used in the context sentence above.

HOW TO WRITE IT (important)
1. Use plain, everyday English. Assume the reader knows almost no grammar terms.
2. Avoid linguistic jargon. If you must use a term like "particle", "topic marker", or "plain form", add a 3-6 word plain explanation the first time (e.g. "the topic marker は, which points out what the sentence is about").
3. Do not just repeat the dictionary meaning - say what the word is doing in THIS sentence.
4. Base every claim on the context sentence and the provided meanings. Do NOT invent facts or usage settings (e.g. "used in vlogs") you cannot support from the input.
5. Register (casual / polite / slang) matters mainly for content words. If "{surface_form}" is a particle, auxiliary, or other grammar word, it is register-neutral - explain its role and do NOT assign it a register or a setting.
6. If the dictionary meanings do not fit how the word is actually used here (e.g. an odd tokenizer split, or homographs like は = topic marker vs 歯 = "tooth"), go with the real context, explain the actual meaning, and set dictionary_mismatch_detected = true.
7. Set confidence to "high" if the dictionary matches the context, "medium" if you inferred the meaning from context, "low" if the tokenization looks wrong.

EXAMPLES
Give exactly 2 natural Japanese example sentences using "{surface_form}" in DIFFERENT situations from the context sentence. Each needs a kana-only reading (no kanji) and an English translation.
"""


def build_pronunciation_feedback_prompt(
    cer: float,
    pitch_score: float,
    user_katakana: str,
    caption_katakana: str,
    user_pitch: list[float],
    reference_pitch: list[float],
    caption: str,
) -> str:
    return f"""
        You are a Japanese pronunciation coach.

        Analyze the learner's pronunciation and provide concise, encouraging feedback.

        Metrics:
        - Character Error Rate (CER): {cer:.3f}
        - Lower is better.
        - 0 means the recognized pronunciation perfectly matched the target.
        - Pitch Similarity Score: {pitch_score:.1f}/100
        - Higher is better.
        - Measures similarity between the learner's pitch contour and the reference.

        Pronunciation Comparison:
        - Learner pronunciation (katakana): {user_katakana}
        - Target pronunciation (katakana): {caption_katakana}
        - Target sentence: {caption}

        Pitch Data:
        - Learner pitch contour: {user_pitch}
        - Reference pitch contour: {reference_pitch}

        Instructions:
        1. Briefly explain what the CER indicates about pronunciation clarity.
        2. Briefly explain what the pitch similarity score indicates.
        3. Compare the learner's katakana pronunciation with the target and identify likely pronunciation mistakes with original Japanese words (not just katakana).
        4. Compare the learner's pitch contour with the reference and identify major pitch accent differences.
        5. Highlight 1-3 strengths.
        6. Provide 2-4 actionable suggestions for improvement.
        7. Keep the tone supportive and educational.
        8. Do not mention raw pitch arrays directly.
        9. If CER is very low (< 0.1), praise pronunciation accuracy.
        10. If pitch score is high (> 85), praise pitch accent accuracy.
        11. Output JSON only using this schema:

        {{
        "summary": "short overall assessment",
        "pronunciation_feedback": [
            "feedback item"
        ],
        "pitch_feedback": [
            "feedback item"
        ],
        "strengths": [
            "strength"
        ],
        "improvements": [
            "improvement suggestion"
        ]
        }}
        """