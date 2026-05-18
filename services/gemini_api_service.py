import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from schemas.vocab_context import WordExplanationResponse
from utils.ai_prompt_builder import build_explanation_prompt

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client()


def get_context_explanation_from_gemini(
    surface_form: str, pos: list, meanings: list, context_sentence: str
) -> WordExplanationResponse:
    prompt_text = build_explanation_prompt(
        surface_form=surface_form,
        pos=pos,
        meanings=meanings,
        context_sentence=context_sentence,
    )

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt_text,
        config=types.GenerateContentConfig(
            # Enforces JSON output matching your schema structure
            response_mime_type="application/json",
            response_schema=WordExplanationResponse,
            temperature=0.2,  # Low temperature ensures stricter instruction following
        ),
    )

    return response.parsed
