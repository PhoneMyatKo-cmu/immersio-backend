from typing import Literal

from pydantic import BaseModel, Field


class ContextRequest(BaseModel):
    vocab_id: int
    caption_id: int
    surface_form: str
    pos: list
    meanings: list
    context_caption: str


class ContextResponse(BaseModel):
    explanation: str
    examples: list[dict]
    confidence: str
    dictionary_mismatche_detected: bool


class ExampleSentence(BaseModel):
    japanese: str = Field(description="The natural Japanese example sentence.")
    reading: str = Field(
        description="The pronunciation reading of the sentence in Hiragana/Katakana (no Kanji)."
    )
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


class VocabRequest(BaseModel):
    vocab_surface_form: str
    video_id: int
    caption: dict


class VocabResponse(BaseModel):
    vocab_id: int
    surface_form: str
    pronunciation: str
    meanings: list[dict]
    context_sentence: dict | None
    sentence_translation: str


class UserVocabSave(BaseModel):
    vocab_id: int
    video_id: int
    sentence_id: int
    timestamp: float
