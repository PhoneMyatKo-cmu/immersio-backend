from sqlalchemy import select
from sqlalchemy.orm import Session

from models.ai_explanation_cache import AI_Explanation_Cache
from schemas.vocab_context import (
    ContextRequest,
    ContextResponse,
    WordExplanationResponse,
)
from services.external.gemini_api_service import get_context_explanation_from_gemini


class ServiceUnavailableError(Exception):
    pass


def check_cache(vocab_id: int, caption_id: int, db: Session):
    stmt = select(AI_Explanation_Cache).where(
        AI_Explanation_Cache.vocab_id == vocab_id,
        AI_Explanation_Cache.caption_id == caption_id,
    )

    row = db.execute(stmt).scalars().first()
    return row


def cache_explanation_deprecated(
    vocab_id: int,
    caption_id: int,
    word_explanation: WordExplanationResponse,
    db: Session,
):

    saved_explanation = AI_Explanation_Cache(
        vocab_id=vocab_id,
        caption_id=caption_id,
        explanation=word_explanation.explanation,
        examples=word_explanation.examples,
        confidence_level=word_explanation.confidence,
        dictionary_mismatch_detected=word_explanation.dictionary_mismatch_detected,
    )
    db.add(saved_explanation)
    db.commit()
    return saved_explanation


def cache_explanation(
    vocab_id: int,
    caption_id: int,
    word_explanation: WordExplanationResponse,
    db: Session,
):
    saved_explanation = AI_Explanation_Cache(
        vocab_id=vocab_id,
        caption_id=caption_id,
        explanation=word_explanation.explanation,
        # Convert list of Pydantic models to list of dicts
        examples=[ex.model_dump() for ex in word_explanation.examples],
        confidence_level=word_explanation.confidence,
        dictionary_mismatch_detected=word_explanation.dictionary_mismatch_detected,
    )
    db.add(saved_explanation)
    db.commit()
    return saved_explanation


def get_context_explanation_from_ai(contextRequest: ContextRequest, db: Session):
    cached_explanation = check_cache(
        contextRequest.vocab_id, contextRequest.caption_id, db
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

    try:
        explanation = get_context_explanation_from_gemini(
            surface_form=contextRequest.surface_form,
            pos=contextRequest.pos,
            meanings=contextRequest.meanings,
            context_sentence=contextRequest.context_caption,
        )

    except Exception as e:
        print(f"GEMINI ERROR{e}")
        raise ServiceUnavailableError(
            "Service is currently not available. Please try again in a moment."
        )

    try:
        cache_explanation(
            vocab_id=contextRequest.vocab_id,
            caption_id=contextRequest.caption_id,
            word_explanation=explanation,
            db=db,
        )
    except Exception as e:
        print(f"DATABASE ERROR:{e}")
        raise e

    return ContextResponse(
        explanation=explanation.explanation,
        examples=[ex.model_dump() for ex in explanation.examples],
        confidence=explanation.confidence,
        dictionary_mismatche_detected=explanation.dictionary_mismatch_detected,
    )
