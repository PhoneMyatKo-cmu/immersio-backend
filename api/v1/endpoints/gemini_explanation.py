from fastapi import APIRouter,HTTPException,Depends
from db.base import get_db
from sqlalchemy.orm import Session
import os
from dotenv import load_dotenv
from utils.request_gemini import build_explanation_prompt
from typing import Literal
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from services.ai_explanation_cache_service import cache_explanation,check_cache


load_dotenv()
GEMINI_API_KEY=os.getenv("GEMINI_API_KEY")
router=APIRouter(prefix="/context-explanation")

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
    
class ContextRequest(BaseModel):
    vocab_id:int
    sentence_id:int
    surface_form:str
    pos:list
    meanings:list
    context_sentence:str

    

client = genai.Client()

@router.get("/")
def get_gemini_explanation(contextRequest:ContextRequest,db:Session=Depends(get_db)):
     
    cached_explanation=check_cache(contextRequest.vocab_id,contextRequest.sentence_id,db)
    
    if cached_explanation:
        print("Cache hit")
        return {
            "explanation":cached_explanation.explanation,
            "examples":cached_explanation.examples,
            "confidence":cached_explanation.confidence_level,
            "dictionary_mismatch_detected":cached_explanation.dictionary_mismatch_detected
        }
    
    else:
        print("Cache missed")
        
        prompt_text = build_explanation_prompt(
            surface_form=contextRequest.surface_form,
            pos=contextRequest.pos,
            meanings=contextRequest.meanings,
            context_sentence=contextRequest.context_sentence
        )
        
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt_text,
            config=types.GenerateContentConfig(
                # Enforces JSON output matching your schema structure
                response_mime_type="application/json",
                response_schema=WordExplanationResponse,
                temperature=0.2, # Low temperature ensures stricter instruction following
            ),
        )
        
        explanation=response.parsed
        cache_explanation(
            vocab_id=contextRequest.vocab_id,
            sentence_id=contextRequest.sentence_id,
            word_explanation=explanation,
            db=db
            )
        
        return explanation

