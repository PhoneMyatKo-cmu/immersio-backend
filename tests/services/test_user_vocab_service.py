"""
Tests for services/user_vocab/user_vocab_service.py  (Word Look Up)

Covers docs/test_plan.md §7.3:
  VDS-02  save_vocab_to_library inserts a row with default SRS values
  VDS-03  duplicate (user, vocab) violates uq_user_vocab -> raises
  VDS-04  check_duplicate_vocab is scoped per user

[integration] Real test DB via db_session. UserSavedVocabulary has FKs to users,
vocabulary, videos and captions, so those rows are seeded first. VDS-03 needs a
constraint-enforcing database (Postgres).
"""

import pytest

try:
    from models.user import User
    from models.video import Video
    from models.vocab import EstimatedLevel, Vocabulary
    from models.processed_caption import Caption
    import models.sentence  # noqa: F401  (Video.shadowingsentences relationship target)
    from models.user_vocab_library import UserSavedVocabulary
    from schemas.vocab_context import UserVocabSave
    from services.user_vocab.user_vocab_service import (
        save_vocab_to_library,
        check_duplicate_vocab,
        get_user_saved_vocab,
        get_review_vocab_by_user,
        get_user_vocab_by_user_and_vocab_id,
        delete_user_vocab,
    )
except Exception as exc:
    pytest.skip(f"user_vocab_service unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.integration, pytest.mark.word_lookup]


def _seed(db, email="a@example.com"):
    user = User(first_name="A", last_name="B", email=email, password_hash="x")
    vocab = Vocabulary(japanese_form="食べる", reading="taberu",
                       meanings=[{"pos": "verb", "meanings": ["to eat"]}],
                       estimated_level=EstimatedLevel.N5)
    video = Video(youtube_video_id="vid12345678", title="T", thumbnail_url="u",
                  channel_name="C", duration_seconds=10)
    db.add_all([user, vocab, video])
    db.commit()
    caption = Caption(video_id=video.id, caption_index=0, text="毎日ご飯を食べる。",
                      tokens=[], start_time=0.0, end_time=1.0, duration=1.0)
    db.add(caption)
    db.commit()
    db.refresh(user); db.refresh(vocab); db.refresh(video); db.refresh(caption)
    return user, vocab, video, caption


def _save(vocab, video, caption, timestamp=1.0):
    return UserVocabSave(vocab_id=vocab.id, video_id=video.id,
                         caption_id=caption.id, timestamp=timestamp)


# --- VDS-02 -----------------------------------------------------------------
def test_save_vocab_to_library_inserts_with_default_srs(db_session):
    user, vocab, video, caption = _seed(db_session)
    save_vocab_to_library(_save(vocab, video, caption, timestamp=12.5), user.id, db_session)

    row = check_duplicate_vocab(user.id, vocab.id, db_session)
    assert row is not None
    assert row.ease_factor == 2.5
    assert row.interval_days == 0


# --- VDS-03 -----------------------------------------------------------------
def test_duplicate_save_violates_unique_constraint(db_session):
    user, vocab, video, caption = _seed(db_session)
    save_vocab_to_library(_save(vocab, video, caption), user.id, db_session)
    with pytest.raises(Exception):  # IntegrityError from uq_user_vocab
        save_vocab_to_library(_save(vocab, video, caption), user.id, db_session)


# --- VDS-04 -----------------------------------------------------------------
def test_check_duplicate_vocab_scoped_per_user(db_session):
    user, vocab, video, caption = _seed(db_session)
    save_vocab_to_library(_save(vocab, video, caption), user.id, db_session)

    assert check_duplicate_vocab(user.id, vocab.id, db_session) is not None

    other = User(first_name="C", last_name="D", email="c@example.com", password_hash="x")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    assert check_duplicate_vocab(other.id, vocab.id, db_session) is None      # other user
    assert check_duplicate_vocab(user.id, vocab.id + 999, db_session) is None  # other vocab


# ==========================================================================
# docs/test_case_specification.pdf  MD-117 .. MD-120
#
#   MD-117  get_user_saved_vocab()              - active rows only
#   MD-118  get_review_vocab_by_user()          - due / not-mastered / not-deleted
#   MD-119  get_user_vocab_by_user_and_vocab_id() - active card for the pair
#   MD-120  delete_user_vocab()                 - soft delete
#
# Self-contained in-memory SQLite session (`saved_db`) — no test DB needed.
# ==========================================================================
from datetime import date, timedelta  # noqa: E402

from sqlalchemy import Date, create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

_seq = __import__("itertools").count(1)


def _use_date_semantics():
    """The SRS review-date columns are declared DateTime but only ever hold a
    calendar day; SQLite string-compares stored 'YYYY-MM-DD 00:00:00' against a
    bound 'YYYY-MM-DD', which breaks the inclusive `<= today` check. Treat them
    as Date for the in-memory test engine so comparisons match Postgres."""
    for name in ("next_review_date", "last_review_date"):
        col = UserSavedVocabulary.__table__.c[name]
        if not isinstance(col.type, Date):
            col.type = Date()


@pytest.fixture()
def saved_db():
    _use_date_semantics()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    for table in (User.__table__, Video.__table__, UserSavedVocabulary.__table__):
        table.create(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                           expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _user(db):
    u = User(first_name="A", last_name="B",
             email=f"u{next(_seq)}@example.com", password_hash="x")
    v = Video(youtube_video_id=f"vid{next(_seq):011d}", title="T", thumbnail_url="u",
              channel_name="C", duration_seconds=10)
    db.add_all([u, v])
    db.commit()
    return u, v


def _card(db, user, video, *, vocab_id=50, is_deleted=False, srs_state="studying",
          next_review_date=None):
    card = UserSavedVocabulary(
        user_id=user.id, vocab_id=vocab_id, video_id=video.id,
        is_deleted=is_deleted, srs_state=srs_state,
        next_review_date=next_review_date,
    )
    db.add(card)
    db.commit()
    return card


# --- MD-117 ---------------------------------------------------------------
def test_get_user_saved_vocab_returns_active_rows(saved_db):
    """All non-deleted rows for the user are returned."""
    user, video = _user(saved_db)
    for vid in (1, 2, 3):
        _card(saved_db, user, video, vocab_id=vid)

    assert len(get_user_saved_vocab(user.id, saved_db)) == 3


def test_get_user_saved_vocab_excludes_soft_deleted(saved_db):
    """Rows with is_deleted = True are filtered out."""
    user, video = _user(saved_db)
    for vid in (1, 2, 3):
        _card(saved_db, user, video, vocab_id=vid)
    for vid in (4, 5):
        _card(saved_db, user, video, vocab_id=vid, is_deleted=True)

    rows = get_user_saved_vocab(user.id, saved_db)
    assert len(rows) == 3
    assert all(r.is_deleted is False for r in rows)


# --- MD-118 --------------------------------------------------------------
def test_get_review_vocab_returns_cards_due_today_or_earlier(saved_db):
    """The next_review_date comparison is inclusive of today."""
    user, video = _user(saved_db)
    today = date.today()
    _card(saved_db, user, video, vocab_id=1, next_review_date=today - timedelta(days=2))
    _card(saved_db, user, video, vocab_id=2, next_review_date=today)

    assert len(get_review_vocab_by_user(user.id, saved_db)) == 2


def test_get_review_vocab_excludes_future_mastered_and_deleted(saved_db):
    """Future-scheduled, mastered and soft-deleted cards are all excluded."""
    user, video = _user(saved_db)
    today = date.today()
    _card(saved_db, user, video, vocab_id=1, next_review_date=today + timedelta(days=3))
    _card(saved_db, user, video, vocab_id=2, next_review_date=today, srs_state="mastered")
    _card(saved_db, user, video, vocab_id=3, next_review_date=today, is_deleted=True)

    assert get_review_vocab_by_user(user.id, saved_db) == []


def test_get_review_vocab_excludes_null_next_review_date(saved_db):
    """A legacy card with next_review_date = NULL is not returned."""
    user, video = _user(saved_db)
    _card(saved_db, user, video, vocab_id=1, next_review_date=None)

    assert get_review_vocab_by_user(user.id, saved_db) == []


# --- MD-119 -------------------------------------------------------------
def test_get_user_vocab_by_user_and_vocab_id_active(saved_db):
    """The active card for the user/vocab pair is returned."""
    user, video = _user(saved_db)
    card = _card(saved_db, user, video, vocab_id=50)

    found = get_user_vocab_by_user_and_vocab_id(user.id, 50, saved_db)
    assert found is not None and found.id == card.id


def test_get_user_vocab_by_user_and_vocab_id_misses(saved_db):
    """Deleted, wrong-user and missing lookups all return None."""
    user, video = _user(saved_db)
    other, _ = _user(saved_db)
    _card(saved_db, user, video, vocab_id=50, is_deleted=True)

    assert get_user_vocab_by_user_and_vocab_id(user.id, 50, saved_db) is None   # deleted
    assert get_user_vocab_by_user_and_vocab_id(other.id, 50, saved_db) is None  # other user
    assert get_user_vocab_by_user_and_vocab_id(user.id, 999, saved_db) is None  # missing


# --- MD-120 -------------------------------------------------------------
def test_delete_user_vocab_soft_deletes_active_card(saved_db):
    """The card is flagged deleted, the row survives, and it leaves the active list."""
    user, video = _user(saved_db)
    card = _card(saved_db, user, video, vocab_id=50)

    assert delete_user_vocab(user.id, 50, saved_db) is True
    assert saved_db.get(UserSavedVocabulary, card.id).is_deleted is True
    assert get_user_saved_vocab(user.id, saved_db) == []


def test_delete_user_vocab_returns_false_when_nothing_to_delete(saved_db):
    """An already-deleted or non-existent card yields False and writes nothing."""
    user, video = _user(saved_db)
    _card(saved_db, user, video, vocab_id=50, is_deleted=True)

    assert delete_user_vocab(user.id, 50, saved_db) is False   # already deleted
    assert delete_user_vocab(user.id, 999, saved_db) is False  # missing
