from sqlalchemy.orm import Session
from sqlalchemy import select
from models.ai_explanation_cache import AI_Explanation_Cache
from utils.request_gemini import WordExplanationResponse


def check_cache(vocab_id: int, sentence_id: int, db: Session):
    stmt = select(AI_Explanation_Cache).where(
        AI_Explanation_Cache.vocab_id == vocab_id,
        AI_Explanation_Cache.sentence_id == sentence_id,
    )

    row = db.execute(stmt).scalars().first()
    return row


def cache_explanation_deprecated(
    vocab_id: int,
    sentence_id: int,
    word_explanation: WordExplanationResponse,
    db: Session,
):

    saved_explanation = AI_Explanation_Cache(
        vocab_id=vocab_id,
        sentence_id=sentence_id,
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
    sentence_id: int,
    word_explanation: WordExplanationResponse,
    db: Session,
):
    saved_explanation = AI_Explanation_Cache(
        vocab_id=vocab_id,
        sentence_id=sentence_id,
        explanation=word_explanation.explanation,
        # Convert list of Pydantic models to list of dicts
        examples=[ex.model_dump() for ex in word_explanation.examples],
        confidence_level=word_explanation.confidence,
        dictionary_mismatch_detected=word_explanation.dictionary_mismatch_detected,
    )
    db.add(saved_explanation)
    db.commit()
    return saved_explanation
