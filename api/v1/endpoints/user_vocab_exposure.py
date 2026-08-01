from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.base import get_db
from services.user_vocab_exposure.user_vocab_exposure_service import get_user_vocab_exposure
from services.vocab.vocab_services import get_vocab_by_id

router = APIRouter(prefix="/user-vocab")

@router.get("/{user_id}")
def get_user_vocab(user_id: int, db: Session = Depends(get_db)):
    """
    Fetches the user's vocabulary library.
    """
    user_vocab = get_user_vocab_exposure(user_id, db)
    vocab_ids = [vocab.vocab_id for vocab in user_vocab]
    vocab_details = [get_vocab_by_id(vocab_id, db) for vocab_id in vocab_ids]

    response = []
    for vocab in vocab_details:
        if vocab:
            response.append({
                "japanese_form": vocab.japanese_form,
                "reading": vocab.reading,
                "lemma": vocab.lemma,
                "meanings": vocab.meanings,
                "estimated_level": vocab.estimated_level,
                "status": user_vocab[vocab_ids.index(vocab.id)].status
            })
    return response