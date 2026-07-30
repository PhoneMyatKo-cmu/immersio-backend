from fastapi import APIRouter, Depends
from pytest import Session

from db.base import Base, get_db
from services.caption.caption_services import get_caption_by_id
from services.user_vocab.user_vocab_service import get_review_vocab_by_user
from services.video.video_services import get_youtube_video_id_by_video_id
from services.vocab.vocab_services import get_vocab_by_id


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