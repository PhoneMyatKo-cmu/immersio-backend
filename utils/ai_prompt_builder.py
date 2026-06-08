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

    return f"""You are a Japanese language teacher helping a learner understand a word in context.

                WORD INFORMATION :
                - Word as seen: {surface_form}
                - Part of speech: {pos_text}
                - Provided dictionary meanings/ Google Tranlated Meaning if POS=web-translate: {meanings_text}

                CONTEXT SENTENCE (from a Japanese YouTube video):
                {context_sentence}

                TASK:
                1. Explain in 2-3 sentences how "{surface_form}" is used specifically in the context sentence above. Focus on nuance, register (casual/formal), and any grammatical patterns worth noting.

                2. Provide exactly 2 natural example sentences using "{surface_form}"  in different contexts. Each example must include an English translation.

                INSTRUCTIONS:
                1. Analyze how "{surface_form}" functions inside the Context Sentence. 
                2. Write a concise explanation (2-3 sentences max) in plain English. Focus on the situational nuance, register (casual, polite, anime/slang slang, etc.), and grammatical connections. Avoid heavy linguistic jargon.
                3. If the provided Dictionary Meanings do not fit how the word is actually being used in this specific context (e.g., due to an unusual tokenizer split or polysemy), prioritize the real context. Explain the actual contextual meaning clearly, and flags this as a dictionary mismatch.
                4. Generate exactly 2 distinct, natural Japanese example sentences demonstrating how to use "{surface_form}" in other situations.
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