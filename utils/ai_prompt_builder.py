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
