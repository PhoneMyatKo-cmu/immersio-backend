"""
Tests for services/session_vocab/session_vocab_service.py

Covers docs/test_case_specification.pdf MD-116:

  MD-116  get_session_vocab_batch()
    - Rows returned for multiple session ids
    - Empty or unmatched id list

[integration] Self-contained in-memory SQLite session (`sv_db`).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

try:
    import models.vocab  # noqa: F401
    import models.processed_caption  # noqa: F401
    import models.sentence  # noqa: F401
    from models.user import User
    from models.video import Video
    from models.learning_session import LearningSession
    from models.session_vocab import SessionVocabulary
    from services.session_vocab.session_vocab_service import get_session_vocab_batch
except Exception as exc:  # pragma: no cover - import guard
    pytest.skip(f"session_vocab_service unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.integration]


@pytest.fixture()
def sv_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    for table in (User.__table__, Video.__table__,
                  LearningSession.__table__, SessionVocabulary.__table__):
        table.create(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed(db):
    user = User(first_name="A", last_name="B", email="a@example.com", password_hash="x")
    video = Video(youtube_video_id="vid12345678", title="T", thumbnail_url="u",
                  channel_name="C", duration_seconds=10)
    db.add_all([user, video])
    db.commit()
    db.refresh(user)
    db.refresh(video)
    from datetime import datetime
    for sid in ("S1", "S2"):
        db.add(LearningSession(id=sid, user_id=user.id, video_id=video.id,
                               start_time=datetime(2026, 1, 10, 9, 0),
                               end_time=datetime(2026, 1, 10, 9, 30)))
    db.commit()
    return user, video


def test_rows_returned_for_multiple_session_ids(sv_db):
    """A single call returns every SessionVocabulary row across the given ids."""
    _seed(sv_db)
    for vid in (1, 2, 3):
        sv_db.add(SessionVocabulary(session_id="S1", vocab_id=vid))
    for vid in (1, 2):
        sv_db.add(SessionVocabulary(session_id="S2", vocab_id=vid))
    sv_db.commit()

    rows = get_session_vocab_batch(["S1", "S2"], sv_db)
    assert len(rows) == 5
    assert {r.session_id for r in rows} == {"S1", "S2"}


def test_empty_or_unmatched_id_list(sv_db):
    """[] and ids with no vocabulary rows both return [] without error."""
    _seed(sv_db)
    sv_db.add(SessionVocabulary(session_id="S1", vocab_id=1))
    sv_db.commit()

    assert get_session_vocab_batch([], sv_db) == []
    assert get_session_vocab_batch(["S2", "nope"], sv_db) == []
