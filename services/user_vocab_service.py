from sqlalchemy import select
from sqlalchemy.orm import Session

from models.user_vocab_library import UserVocabLibrary
from schemas.vocab_context import UserVocabSave


def check_duplicate_vocab(user_id: int, vocab_id: int, db: Session):
    result = db.scalars(
        select(UserVocabLibrary).where(
            UserVocabLibrary.user_id == user_id, UserVocabLibrary.vocab_id == vocab_id
        )
    ).first()
    return result


def save_vocab_to_library(saveVocab: UserVocabSave, user_id: int, db: Session):
    new_vocab = UserVocabLibrary(
        user_id=user_id,
        vocab_id=saveVocab.vocab_id,
        video_id=saveVocab.video_id,
        sentence_id=saveVocab.sentence_id,
        timestamp=saveVocab.timestamp,
    )

    try:
        db.add(new_vocab)
        db.commit()
    except Exception as e:
        print(e)
        raise e
