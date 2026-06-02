import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from schemas.vocab_context import WordExplanationResponse
from schemas.shadowing import PronunciationExplanationResponse
from utils.ai_prompt_builder import build_pronunciation_feedback_prompt
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

def get_pronunciation_feedback_from_gemini(
    cer: float,
    pitch_score: float,
    user_katakana: str,
    caption_katakana: str,
    user_pitch: list[float],
    reference_pitch: list[float],
    caption: str,
) -> str:
    prompt_text = build_pronunciation_feedback_prompt(
        cer=cer,
        pitch_score=pitch_score,
        user_katakana=user_katakana,
        caption_katakana=caption_katakana,
        user_pitch=user_pitch,
        reference_pitch=reference_pitch,
        caption=caption,
    )
    print("Generating pronunciation feedback with Gemini using prompt:...")
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt_text,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PronunciationExplanationResponse,
            temperature=0.2,),
    )
    print(f"Gemini response: {response.text}")
    return response.parsed