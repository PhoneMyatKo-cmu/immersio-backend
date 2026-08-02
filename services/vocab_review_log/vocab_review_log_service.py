
from datetime import datetime

from sqlalchemy.orm import Session

from models.user_vocab_library import UserSavedVocabulary
from models.vocab_review_log import VocabularyReviewLog


def save_vocabulary_review_log(user_saved_vocab: UserSavedVocabulary, grade: int, db: Session):
    today = datetime.now().date()

    if user_saved_vocab.last_review_date:
        elapsed_interval_days = (today - user_saved_vocab.last_review_date).days
    else:
        elapsed_interval_days = (today - user_saved_vocab.first_saved_date).days

    review_log = VocabularyReviewLog(
        user_saved_vocab_id=user_saved_vocab.id,
        grade=grade,
        review_date=today,
        scheduled_interval_days=user_saved_vocab.interval_days,
        elapsed_interval_days=elapsed_interval_days
    )
    db.add(review_log)
    db.commit()
    db.refresh(review_log)
    return review_log