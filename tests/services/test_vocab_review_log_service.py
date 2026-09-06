"""
Tests for services/vocab_review_log/vocab_review_log_service.py

Covers docs/test_case_specification.pdf MD-127:

  MD-127  save_vocabulary_review_log()
    - Elapsed interval measured from the last review
    - Falls back to first_saved_date when never reviewed
    - Same-day and overdue reviews

[integration] Self-contained in-memory SQLite session (`log_db`); dates are kept
as Python `date` objects (expire_on_commit=False) so the service's
`date - date` arithmetic runs as it does in production.
"""

from datetime import date, timedelta

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
    from models.user_vocab_library import UserSavedVocabulary
    from models.vocab_review_log import VocabularyReviewLog
    from services.vocab_review_log.vocab_review_log_service import save_vocabulary_review_log
except Exception as exc:  # pragma: no cover - import guard
    pytest.skip(f"vocab_review_log_service unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.integration]


@pytest.fixture()
def log_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    for table in (User.__table__, Video.__table__,
                  UserSavedVocabulary.__table__, VocabularyReviewLog.__table__):
        table.create(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                           expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


_seq = __import__("itertools").count(1)


def _card(db, *, interval_days=0, last_review_date=None, first_saved_date=None):
    n = next(_seq)
    user = User(first_name="A", last_name="B", email=f"u{n}@example.com", password_hash="x")
    video = Video(youtube_video_id=f"vid{n:011d}", title="T", thumbnail_url="u",
                  channel_name="C", duration_seconds=10)
    db.add_all([user, video])
    db.commit()
    card = UserSavedVocabulary(
        user_id=user.id, vocab_id=50, video_id=video.id,
        interval_days=interval_days,
        last_review_date=last_review_date,
        first_saved_date=first_saved_date or date.today(),
    )
    db.add(card)
    db.commit()
    return card


def test_elapsed_interval_measured_from_last_review(log_db):
    """elapsed_interval_days counts from last_review_date; scheduled comes from the card."""
    today = date.today()
    card = _card(log_db, interval_days=6, last_review_date=today - timedelta(days=7))

    log = save_vocabulary_review_log(card, 4, log_db)

    assert log.id is not None
    assert log.grade == 4
    assert log.scheduled_interval_days == 6
    assert log.elapsed_interval_days == 7


def test_falls_back_to_first_saved_date_when_never_reviewed(log_db):
    """With no last_review_date the elapsed interval is measured from first_saved_date."""
    today = date.today()
    card = _card(log_db, interval_days=0, last_review_date=None,
                 first_saved_date=today - timedelta(days=3))

    log = save_vocabulary_review_log(card, 3, log_db)
    assert log.elapsed_interval_days == 3


def test_same_day_and_overdue_reviews(log_db):
    """Same-day review -> 0 elapsed; an overdue review stores the real gap as-is."""
    today = date.today()

    same_day = _card(log_db, interval_days=1, last_review_date=today)
    assert save_vocabulary_review_log(same_day, 5, log_db).elapsed_interval_days == 0

    overdue = _card(log_db, interval_days=6, last_review_date=today - timedelta(days=30))
    log = save_vocabulary_review_log(overdue, 4, log_db)
    assert log.scheduled_interval_days == 6
    assert log.elapsed_interval_days == 30
