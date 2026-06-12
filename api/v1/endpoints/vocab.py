from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.base import get_db
from schemas.user import UserRead
from schemas.vocab_context import UserVocabSave, VocabRequest, VocabResponse
from services.auth.authentication_service import get_current_user

# from services.context_sentence_services import (
#     find_context_sentence,
#     get_sentence_translation,
# )
from services.caption.caption_services import get_caption_translation
from services.user_vocab.user_vocab_service import (
    check_duplicate_vocab,
    save_vocab_to_library,
)
from services.vocab.vocab_services import get_vocab_by_surface_form

router = APIRouter(prefix="/vocab")


@router.post("/")
def get_vocabulary(
    vocabRequest: VocabRequest, db: Session = Depends(get_db)
) -> VocabResponse:
    surface_form = vocabRequest.vocab_surface_form
    print(vocabRequest)
    if not surface_form:
        raise HTTPException(400, "Empty Request")

    vocab = get_vocab_by_surface_form(surface_form, db)

    if not vocab:
        raise HTTPException(404, "Meaning Not Found.")

    # context_sentence = find_context_sentence(
    #     word=surface_form,
    #     video_id=vocabRequest.video_id,
    #     timestamp=vocabRequest.timestamp,
    #     db=db,
    # )

    context_sentence = vocabRequest.caption

    context_sentence_translation = get_caption_translation(context_sentence, db)

    return VocabResponse(
        vocab_id=vocab.id,
        surface_form=vocab.japanese_form,
        pronunciation=vocab.reading,
        meanings=vocab.meanings,
        estimated_level=vocab.estimated_level,
        context_sentence=context_sentence,
        sentence_translation=context_sentence_translation,
    )


@router.post("/save")
def save_vocab_for_user(
    saveVocab: UserVocabSave,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
):
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthenticated"
        )

    user_id = current_user.id
    try:
        save_vocab_to_library(saveVocab, user_id, db)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Vocab already saved"
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error, please try again later"
        )

    return {"message": "success"}


@router.get("/check-duplicate")
def check_duplicate_vocab_per_user(
    vocab_id: int,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
):
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthenticated"
        )

    return {"saved": check_duplicate_vocab(current_user.id, vocab_id, db) is not None}
