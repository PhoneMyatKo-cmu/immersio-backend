from fastapi import APIRouter,HTTPException,Depends
from pydantic import BaseModel
from db.base import get_db
from models.vocab import Vocabulary
from sqlalchemy.orm import Session
from services.vocab_services import get_vocab_by_surface_form
from services.context_sentence_services import find_context_sentence
router=APIRouter(prefix="/get-vocab")

class VocabRequest(BaseModel):
    vocab_surface_form:str
    video_id:int
    timestamp:float

class VocabResponse(BaseModel):
    surface_form:str
    pronunciation:str
    meanings:list[dict]
    context_sentence:dict | None


@router.get("/")
def get_vocabulary(vocabRequest:VocabRequest,db:Session=Depends(get_db))->VocabResponse:
    surface_form=vocabRequest.vocab_surface_form
    print(surface_form)
    
    

        
    if not surface_form:
        raise HTTPException(400,"Empty Request")
    
    vocab=get_vocab_by_surface_form(surface_form,db)
    
    if not vocab:
        raise HTTPException(404,"Meaning Not Found.")
    
    context_sentence=find_context_sentence(
            word=surface_form,
            video_id=vocabRequest.video_id,
            timestamp=vocabRequest.timestamp,
            db=db)
    
    return VocabResponse(
        surface_form=vocab.japanese_form,
        pronunciation=vocab.reading,
        meanings=vocab.meanings,
        context_sentence=context_sentence
    )
    
    