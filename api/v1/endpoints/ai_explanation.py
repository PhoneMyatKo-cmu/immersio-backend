from fastapi import APIRouter, HTTPException, Depends
from db.base import get_db
from sqlalchemy.orm import Session
from utils.request_gemini import get_context_explanation_from_ai
from pydantic import BaseModel

from services.ai_explanation_cache_service import cache_explanation, check_cache


router = APIRouter(prefix="/context-explanation")


class ContextRequest(BaseModel):
    vocab_id: int
    sentence_id: int
    surface_form: str
    pos: list
    meanings: list
    context_sentence: str


class ContextResponse(BaseModel):
    explanation: str
    examples: list[dict]
    confidence: str
    dictionary_mismatche_detected: bool


@router.get("/")
def get_ai_explanation(contextRequest: ContextRequest, db: Session = Depends(get_db)):

    cached_explanation = check_cache(
        contextRequest.vocab_id, contextRequest.sentence_id, db
    )

    if cached_explanation:
        print("Cache hit")
        return ContextResponse(
            explanation=cached_explanation.explanation,
            examples=cached_explanation.examples,
            confidence=cached_explanation.confidence_level,
            dictionary_mismatche_detected=cached_explanation.dictionary_mismatch_detected,
        )

    print("Cache missed")

    explanation = get_context_explanation_from_ai(
        surface_form=contextRequest.surface_form,
        pos=contextRequest.pos,
        meanings=contextRequest.meanings,
        context_sentence=contextRequest.context_sentence,
    )

    cache_explanation(
        vocab_id=contextRequest.vocab_id,
        sentence_id=contextRequest.sentence_id,
        word_explanation=explanation,
        db=db,
    )

    return ContextResponse(
        explanation=explanation.explanation,
        examples=[ex.model_dump() for ex in explanation.examples],
        confidence=explanation.confidence,
        dictionary_mismatche_detected=explanation.dictionary_mismatch_detected,
    )
