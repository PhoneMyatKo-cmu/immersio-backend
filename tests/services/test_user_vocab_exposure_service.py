"""
Tests for services/user_vocab_exposure/user_vocab_exposure_service.py

Covers docs/test_case_specification.pdf MD-121 .. MD-124:

  MD-121  get_user_vocab_exposure()
    - Returns only the requested user's exposure
    - User with no exposure history

  MD-122  save_user_vocab_exposure()
    - First exposure creates a new record
    - Repeat exposure increments and promotes at the threshold
    - Vocab already recorded for the session is skipped
    - Interval not covering the caption records nothing
    - Vocab in multiple captions counts once per session
    - Missing video or caption
    - Malformed caption_indices

  MD-123  get_vocab_seen_by_user()
    - All exposed vocabulary regardless of status
    - User with no exposure

  MD-124  get_vocab_known_by_user()
    - Only KNOW-status rows are returned
    - Exposure exists but nothing known yet

[integration] Self-contained in-memory SQLite session (`exposure_db`).
"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

try:
    import models.vocab  # noqa: F401
    import models.processed_caption  # noqa: F401
    import models.sentence  # noqa: F401
    import models.video_vocab_profile  # noqa: F401  (Video.vocabulary_entries backref)
    from models.user import User
    from models.video import Video
    from models.processed_caption import Caption
    from models.video_vocab_profile import VideoVocabulary
    from models.learning_session import LearningSession
    from models.learning_video_interval import LearningVideoInterval
    from models.session_vocab import SessionVocabulary
    from models.user_vocab_profile import UserVocabularyExposure
    from services.user_vocab_exposure.user_vocab_exposure_service import (
        get_user_vocab_exposure,
        save_user_vocab_exposure,
        get_vocab_seen_by_user,
        get_vocab_known_by_user,
    )
except Exception as exc:  # pragma: no cover - import guard
    pytest.skip(f"user_vocab_exposure_service unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.integration]

_TABLES = [
    User.__table__,
    Video.__table__,
    Caption.__table__,
    VideoVocabulary.__table__,
    LearningSession.__table__,
    LearningVideoInterval.__table__,
    SessionVocabulary.__table__,
    UserVocabularyExposure.__table__,
]

_NOW = datetime(2026, 1, 10, 12, 0)


def _status(row):
    """Exposure.status reads back as the VocabStatus enum; normalise to its value."""
    return getattr(row.status, "value", row.status)


@pytest.fixture()
def exposure_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    for table in _TABLES:
        table.create(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                           expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------
def _seed_user(db, email="a@example.com"):
    user = User(first_name="A", last_name="B", email=email, password_hash="x")
    db.add(user)
    db.commit()
    return user


def _seed_video(db, youtube_id="vid12345678"):
    video = Video(youtube_video_id=youtube_id, title="T", thumbnail_url="u",
                  channel_name="C", duration_seconds=60)
    db.add(video)
    db.commit()
    return video


def _add_captions(db, video_id, count):
    """count captions with indices 0..count-1, each spanning [i*3, i*3+2]s."""
    for i in range(count):
        db.add(Caption(video_id=video_id, caption_index=i, text=f"c{i}", tokens=[],
                       start_time=float(i * 3), end_time=float(i * 3 + 2),
                       duration=2.0))
    db.commit()


def _set_caption_window(db, video_id, caption_index, start, end):
    cap = (db.query(Caption)
           .filter(Caption.video_id == video_id, Caption.caption_index == caption_index)
           .one())
    cap.start_time, cap.end_time = start, end
    db.commit()


def _add_profile(db, video_id, vocab_id, caption_indices):
    prof = VideoVocabulary(video_id=video_id, vocab_id=vocab_id,
                           caption_indices=caption_indices)
    db.add(prof)
    db.commit()
    return prof


def _add_session(db, sid, user_id, video_id, intervals=((4.0, 10.0),)):
    ls = LearningSession(id=sid, user_id=user_id, video_id=video_id,
                         start_time=_NOW.replace(hour=11), end_time=_NOW)
    db.add(ls)
    db.commit()
    for s, e in intervals:
        db.add(LearningVideoInterval(session_id=sid, start_time=s, end_time=e))
    db.commit()
    db.refresh(ls)
    return ls


def _expose(db, user_id, vocab_id, seen_count, status="SEEN"):
    row = UserVocabularyExposure(user_id=user_id, vocab_id=vocab_id,
                                 seen_count=seen_count, status=status,
                                 first_seen_at=datetime(2026, 1, 1),
                                 last_seen_at=datetime(2026, 1, 1))
    db.add(row)
    db.commit()
    return row


# ---------------------------------------------------------------------------
# MD-121  get_user_vocab_exposure()
# ---------------------------------------------------------------------------
def test_returns_only_requested_users_exposure(exposure_db):
    """Only the queried user's exposure rows come back."""
    u1 = _seed_user(exposure_db, "u1@example.com")
    u2 = _seed_user(exposure_db, "u2@example.com")
    for i in range(12):
        _expose(exposure_db, u1.id, 100 + i, seen_count=1)
    for i in range(8):
        _expose(exposure_db, u2.id, 200 + i, seen_count=1)

    rows = get_user_vocab_exposure(u1.id, exposure_db)
    assert len(rows) == 12
    assert all(r.user_id == u1.id for r in rows)


def test_user_with_no_exposure_history(exposure_db):
    """A user who never completed a session gets []."""
    user = _seed_user(exposure_db)
    assert get_user_vocab_exposure(user.id, exposure_db) == []


# ---------------------------------------------------------------------------
# MD-122  save_user_vocab_exposure()
# ---------------------------------------------------------------------------
def test_first_exposure_creates_a_new_record(exposure_db):
    """A covered caption with no prior exposure writes an exposure + session-vocab row."""
    user = _seed_user(exposure_db)
    video = _seed_video(exposure_db)
    _add_captions(exposure_db, video.id, 4)
    _set_caption_window(exposure_db, video.id, 3, 5.0, 8.0)
    prof = _add_profile(exposure_db, video.id, vocab_id=50, caption_indices="3")
    session = _add_session(exposure_db, "s1", user.id, video.id, intervals=((4.0, 10.0),))

    save_user_vocab_exposure(session, exposure_db)

    exp = (exposure_db.query(UserVocabularyExposure)
           .filter(UserVocabularyExposure.user_id == user.id).all())
    assert len(exp) == 1
    assert exp[0].vocab_id == 50
    assert exp[0].seen_count == 1
    assert _status(exp[0]) == "SEEN"
    assert exp[0].first_seen_at == _NOW and exp[0].last_seen_at == _NOW

    sv = exposure_db.query(SessionVocabulary).all()
    assert len(sv) == 1 and sv[0].vocab_id == prof.id


def test_repeat_exposure_increments_and_promotes_at_threshold(exposure_db):
    """seen_count 3 -> 4 stays SEEN; seen_count 10 -> 11 flips to KNOW (strictly > 10)."""
    user = _seed_user(exposure_db)
    video = _seed_video(exposure_db)
    _add_captions(exposure_db, video.id, 4)
    _set_caption_window(exposure_db, video.id, 3, 5.0, 8.0)
    _add_profile(exposure_db, video.id, vocab_id=50, caption_indices="3")
    _add_profile(exposure_db, video.id, vocab_id=51, caption_indices="3")
    _expose(exposure_db, user.id, 50, seen_count=3)
    _expose(exposure_db, user.id, 51, seen_count=10)
    session = _add_session(exposure_db, "s1", user.id, video.id, intervals=((4.0, 10.0),))

    save_user_vocab_exposure(session, exposure_db)

    by_vocab = {r.vocab_id: r for r in get_user_vocab_exposure(user.id, exposure_db)}
    assert by_vocab[50].seen_count == 4 and _status(by_vocab[50]) == "SEEN"
    assert by_vocab[51].seen_count == 11 and _status(by_vocab[51]) == "KNOW"


def test_vocab_already_recorded_for_the_session_is_skipped(exposure_db):
    """An existing SessionVocabulary link for the vocab suppresses a second count."""
    user = _seed_user(exposure_db)
    video = _seed_video(exposure_db)
    _add_captions(exposure_db, video.id, 4)
    _set_caption_window(exposure_db, video.id, 3, 5.0, 8.0)
    prof = _add_profile(exposure_db, video.id, vocab_id=50, caption_indices="3")
    _expose(exposure_db, user.id, 50, seen_count=3)
    old = _add_session(exposure_db, "s_old", user.id, video.id)
    exposure_db.add(SessionVocabulary(session_id=old.id, vocab_id=prof.id))
    exposure_db.commit()
    new = _add_session(exposure_db, "s_new", user.id, video.id, intervals=((4.0, 10.0),))

    save_user_vocab_exposure(new, exposure_db)

    exp = get_user_vocab_exposure(user.id, exposure_db)
    assert exp[0].seen_count == 3                       # untouched
    assert exposure_db.query(SessionVocabulary).count() == 1  # no duplicate


def test_interval_not_covering_the_caption_records_nothing(exposure_db):
    """When no watched interval covers the caption, no row is created or updated."""
    user = _seed_user(exposure_db)
    video = _seed_video(exposure_db)
    _add_captions(exposure_db, video.id, 4)
    _set_caption_window(exposure_db, video.id, 3, 5.0, 8.0)
    _add_profile(exposure_db, video.id, vocab_id=50, caption_indices="3")
    session = _add_session(exposure_db, "s1", user.id, video.id, intervals=((20.0, 30.0),))

    save_user_vocab_exposure(session, exposure_db)

    assert get_user_vocab_exposure(user.id, exposure_db) == []
    assert exposure_db.query(SessionVocabulary).count() == 0


def test_vocab_in_multiple_captions_counts_once_per_session(exposure_db):
    """A vocab mapped to several covered captions is still counted a single time."""
    user = _seed_user(exposure_db)
    video = _seed_video(exposure_db)
    _add_captions(exposure_db, video.id, 6)
    for idx in (2, 3, 4):
        _set_caption_window(exposure_db, video.id, idx, 5.0, 8.0)
    _add_profile(exposure_db, video.id, vocab_id=50, caption_indices="2,3,4")
    session = _add_session(exposure_db, "s1", user.id, video.id, intervals=((4.0, 10.0),))

    save_user_vocab_exposure(session, exposure_db)

    exp = get_user_vocab_exposure(user.id, exposure_db)
    assert len(exp) == 1 and exp[0].seen_count == 1
    assert exposure_db.query(SessionVocabulary).count() == 1


def test_missing_video_raises(exposure_db):
    """A session pointing at an unknown video raises."""
    user = _seed_user(exposure_db)
    session = _add_session(exposure_db, "s1", user.id, 999, intervals=((4.0, 10.0),))
    with pytest.raises(ValueError, match="Video with id 999 not found."):
        save_user_vocab_exposure(session, exposure_db)


def test_missing_caption_raises(exposure_db):
    """A caption_indices entry that is in range but has no matching caption raises."""
    user = _seed_user(exposure_db)
    video = _seed_video(exposure_db)
    # captions 0, 2, 3 exist (index 1 is missing) -> len == 3, so index 1 is "in range".
    for i in (0, 2, 3):
        exposure_db.add(Caption(video_id=video.id, caption_index=i, text="c", tokens=[],
                                start_time=5.0, end_time=8.0, duration=3.0))
    exposure_db.commit()
    _add_profile(exposure_db, video.id, vocab_id=50, caption_indices="1")
    session = _add_session(exposure_db, "s1", user.id, video.id, intervals=((4.0, 10.0),))

    with pytest.raises(ValueError, match="Caption with index 1 not found"):
        save_user_vocab_exposure(session, exposure_db)


def test_malformed_caption_indices_are_skipped(exposure_db):
    """An empty string and a non-numeric entry are ignored without error."""
    user = _seed_user(exposure_db)
    video = _seed_video(exposure_db)
    _add_captions(exposure_db, video.id, 4)
    _set_caption_window(exposure_db, video.id, 3, 5.0, 8.0)
    _add_profile(exposure_db, video.id, vocab_id=50, caption_indices="")
    _add_profile(exposure_db, video.id, vocab_id=51, caption_indices="abc")
    session = _add_session(exposure_db, "s1", user.id, video.id, intervals=((4.0, 10.0),))

    save_user_vocab_exposure(session, exposure_db)  # no raise
    assert get_user_vocab_exposure(user.id, exposure_db) == []


# ---------------------------------------------------------------------------
# MD-123  get_vocab_seen_by_user()
# ---------------------------------------------------------------------------
def test_all_exposed_vocab_regardless_of_status(exposure_db):
    """Both SEEN and KNOW rows are returned."""
    user = _seed_user(exposure_db)
    for i in range(4):
        _expose(exposure_db, user.id, 10 + i, seen_count=2, status="SEEN")
    for i in range(2):
        _expose(exposure_db, user.id, 20 + i, seen_count=15, status="KNOW")

    assert len(get_vocab_seen_by_user(user.id, exposure_db)) == 6


def test_vocab_seen_user_with_no_exposure(exposure_db):
    user = _seed_user(exposure_db)
    assert get_vocab_seen_by_user(user.id, exposure_db) == []


# ---------------------------------------------------------------------------
# MD-124  get_vocab_known_by_user()
# ---------------------------------------------------------------------------
def test_only_know_status_rows_are_returned(exposure_db):
    """Exactly the KNOW rows come back, not the SEEN ones."""
    user = _seed_user(exposure_db)
    for i in range(4):
        _expose(exposure_db, user.id, 10 + i, seen_count=15, status="KNOW")
    for i in range(7):
        _expose(exposure_db, user.id, 20 + i, seen_count=2, status="SEEN")

    rows = get_vocab_known_by_user(user.id, exposure_db)
    assert len(rows) == 4
    assert all(_status(r) == "KNOW" for r in rows)


def test_exposure_exists_but_nothing_known_yet(exposure_db):
    """All-SEEN exposure yields an empty known list."""
    user = _seed_user(exposure_db)
    for i in range(3):
        _expose(exposure_db, user.id, 10 + i, seen_count=2, status="SEEN")
    assert get_vocab_known_by_user(user.id, exposure_db) == []
