from fastapi import APIRouter, Depends, HTTPException
from pytest import Session

from db.base import Base, get_db
from services.caption.caption_services import get_caption_by_id
from services.user_vocab.user_vocab_service import get_review_vocab_by_user, get_user_vocab_by_user_and_vocab_id
from services.video.video_services import get_youtube_video_id_by_video_id
from services.vocab.vocab_services import get_vocab_by_id
from services.vocab_review_log.vocab_review_log_service import save_vocabulary_review_log
from utils.spaced_repetition_review_helper import update_review_card


router = APIRouter(prefix="/review")

@router.get("/{user_id}")
def get_reviewable_vocab(user_id: int, db: Session = Depends(get_db)):
    """
    Fetches the user's vocabulary library that is due for review.
    """
    reviewable_vocab = get_review_vocab_by_user(user_id, db)
    vocab_ids = [vocab.vocab_id for vocab in reviewable_vocab]
    vocab_details = [get_vocab_by_id(vocab_id, db) for vocab_id in vocab_ids]

    response = []
    for vocab, card in zip(vocab_details, reviewable_vocab):
        if vocab:
            youtube_video_id = get_youtube_video_id_by_video_id(card.video_id, db)
            caption = get_caption_by_id(card.caption_id, db)
            response.append({
                "vocab_id": vocab.id,
                "user_vocab_id": card.id,
                "japanese_form": vocab.japanese_form,
                "reading": vocab.reading,
                "lemma": vocab.lemma,
                "meanings": vocab.meanings,
                "estimated_level": vocab.estimated_level,
                "srs_state": card.srs_state,
                "youtube_video_id": youtube_video_id,
                "caption": caption.text if caption else None,
                "caption_translation": caption.translation if caption else None,
                "start_time": caption.start_time if caption else None,
                "end_time": caption.end_time if caption else None,
            })
    return response

@router.post("/update/{user_id}/{vocab_id}")
def review_vocab(
    user_id: int,
    vocab_id: int,
    grade: int,
    db: Session = Depends(get_db)
):
    """
    Updates the vocabulary review data based on the user's review grade.
    """
    vocab_card = get_user_vocab_by_user_and_vocab_id(user_id, vocab_id, db)
    if not vocab_card or vocab_card.user_id != user_id:
        raise HTTPException(status_code=404, detail="Vocabulary card not found for this user.")

    update_review_card(vocab_card, grade)
    save_vocabulary_review_log(vocab_card, grade, db)
    db.commit()
    return {"message": "Review data updated successfully."}