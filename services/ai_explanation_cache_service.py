from sqlalchemy.orm import Session
from sqlalchemy import select
from models.ai_explanation_cache import AI_Explanation_Cache

def check_cache(vocab_id:int, sentence_id:int , db:Session):
    stmt=select(AI_Explanation_Cache).where(
        AI_Explanation_Cache.vocab_id==vocab_id,
        AI_Explanation_Cache.sentence_id==sentence_id
    )
    
    row=db.execute(stmt).scalars().first()
    return row

from typing import Literal
from pydantic import BaseModel, Field


class ExampleSentence(BaseModel):
    japanese: str = Field(description="The natural Japanese example sentence.")
    reading: str = Field(description="The pronunciation reading of the sentence in Hiragana/Katakana (no Kanji).")
    english: str = Field(description="The English translation of the example sentence.")



class WordExplanationResponse(BaseModel):
    explanation: str = Field(
        description="2-3 sentences explaining how the word is used specifically in the context sentence, focusing on nuance and register."
    )
    examples: list[ExampleSentence] = Field(
        description="Exactly 2 natural example sentences using the word in different contexts."
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="Confidence level. Use 'high' if dictionary matches context, 'medium' if inferred from context, 'low' if tokenization looks incorrect."
    )
    dictionary_mismatch_detected: bool = Field(
        description="True if the provided dictionary meanings did not fit the context sentence, forcing a contextual definition override."
    )

def cache_explanation_deprecated(vocab_id:int,sentence_id:int,word_explanation:WordExplanationResponse,db:Session):
    
    saved_explanation=AI_Explanation_Cache(
        vocab_id=vocab_id,
        sentence_id=sentence_id,
        explanation=word_explanation.explanation,
        examples=word_explanation.examples,
        confidence_level=word_explanation.confidence,
        dictionary_mismatch_detected=word_explanation.dictionary_mismatch_detected
    )
    db.add(saved_explanation)
    db.commit()
    return saved_explanation

def cache_explanation(
    vocab_id:         int,
    sentence_id:      int,
    word_explanation: WordExplanationResponse,
    db:               Session
):
    saved_explanation = AI_Explanation_Cache(
        vocab_id=vocab_id,
        sentence_id=sentence_id,
        explanation=word_explanation.explanation,
        # Convert list of Pydantic models to list of dicts
        examples=[ex.model_dump() for ex in word_explanation.examples],
        confidence_level=word_explanation.confidence,
        dictionary_mismatch_detected=word_explanation.dictionary_mismatch_detected
    )
    db.add(saved_explanation)
    db.commit()
    return saved_explanation