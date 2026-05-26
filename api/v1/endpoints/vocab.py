from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.base import get_db
from schemas.vocab_context import VocabRequest, VocabResponse
from services.context_sentence_services import (
    find_context_sentence,
    get_sentence_translation,
)
from services.vocab_services import get_vocab_by_surface_form

router = APIRouter(prefix="/get-vocab")


@router.post("/")
def get_vocabulary(
    vocabRequest: VocabRequest, db: Session = Depends(get_db)
) -> VocabResponse:
    surface_form = vocabRequest.vocab_surface_form
    print(surface_form)

    if not surface_form:
        raise HTTPException(400, "Empty Request")

    vocab = get_vocab_by_surface_form(surface_form, db)

    if not vocab:
        raise HTTPException(404, "Meaning Not Found.")

    context_sentence = find_context_sentence(
        word=surface_form,
        video_id=vocabRequest.video_id,
        timestamp=vocabRequest.timestamp,
        db=db,
    )

    context_sentence_translation = get_sentence_translation(context_sentence, db)

    return VocabResponse(
        vocab_id=vocab.id,
        surface_form=vocab.japanese_form,
        pronunciation=vocab.reading,
        meanings=vocab.meanings,
        context_sentence=context_sentence,
        sentence_translation=context_sentence_translation,
    )


@router.post("/save")
def save_vocab_for_user():
    pass


def temp_get_user_id():
    return 1
