from sqlalchemy import select
from sqlalchemy.orm import Session

from models.user_vocab_library import UserSavedVocabulary
from schemas.vocab_context import UserVocabSave


def check_duplicate_vocab(user_id: int, vocab_id: int, db: Session):
    result = db.scalars(
        select(UserSavedVocabulary).where(
            UserSavedVocabulary.user_id == user_id, UserSavedVocabulary.vocab_id == vocab_id
        )
    ).first()
    return result


def save_vocab_to_library(saveVocab: UserVocabSave, user_id: int, db: Session):
    new_vocab = UserSavedVocabulary(
        user_id=user_id,
        vocab_id=saveVocab.vocab_id,
        video_id=saveVocab.video_id,
        caption_id=saveVocab.caption_id,
        timestamp=saveVocab.timestamp,
    )

    try:
        db.add(new_vocab)
        db.commit()
    except Exception as e:
        print(e)
        raise e

def get_user_saved_vocab(user_id: int, db: Session):
    return db.query(UserSavedVocabulary).filter(
        UserSavedVocabulary.user_id == user_id
    ).all()