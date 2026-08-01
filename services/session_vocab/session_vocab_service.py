

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.session_vocab import SessionVocabulary

def get_session_vocab_batch(session_ids: list[int], db: Session):
    stmt = select(SessionVocabulary).where(SessionVocabulary.session_id.in_(session_ids))

    rows = db.execute(stmt).scalars().all()
    return rows