"""
Tests for services/daily_progress/daily_progress_service.py

Covers docs/test_case_specification.pdf MD-107 .. MD-110:

  MD-107   save_daily_progress()
    - First session of a day creates a progress record
    - Later session on the same day updates the existing record
    - Streak resets after a gap

  MD-108  get_all_time_progress()
    - Returns only the requested user's rows
    - User with no recorded progress

  MD-109  get_daily_progress()
    - Record exists for the requested day
    - No matching user/day pair

  MD-110  get_daily_progress_by_date_range()
    - Both bounds supplied are inclusive
    - Open bounds are honoured
    - Range containing no data

[integration] Self-contained in-memory SQLite session (`progress_db`) — none of
the tables involved use PostgreSQL-only column types, so no test DB is needed.
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

try:
    import models.vocab  # noqa: F401  (lets session_vocabulary/exposure FKs resolve their type)
    import models.processed_caption  # noqa: F401  (Video.captions relationship target)
    import models.sentence  # noqa: F401  (Video.shadowingsentences relationship target)
    from models.user import User
    from models.video import Video
    from models.daily_progress import DailyProgress
    from models.learning_session import LearningSession
    from models.session_vocab import SessionVocabulary
    from models.user_vocab_profile import UserVocabularyExposure
    from services.daily_progress.daily_progress_service import (
        save_daily_progress,
        get_all_time_progress,
        get_daily_progress,
        get_daily_progress_by_date_range,
    )
except Exception as exc:  # pragma: no cover - import guard
    pytest.skip(f"daily_progress_service unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.integration]

_TABLES = [
    User.__table__,
    Video.__table__,
    LearningSession.__table__,
    DailyProgress.__table__,
    SessionVocabulary.__table__,
    UserVocabularyExposure.__table__,
]


@pytest.fixture()
def progress_db():
    """In-memory SQLite session with just the tables these methods touch."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for table in _TABLES:
        table.create(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
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
    db.refresh(user)
    return user


def _seed_video(db, youtube_id="vid12345678"):
    video = Video(youtube_video_id=youtube_id, title="T", thumbnail_url="u",
                  channel_name="C", duration_seconds=10)
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


def _add_session(db, user, video, day, session_id, start="09:00", end="09:10"):
    """Persist a LearningSession that starts/ends on `day`."""
    sh, sm = (int(x) for x in start.split(":"))
    eh, em = (int(x) for x in end.split(":"))
    ls = LearningSession(
        id=session_id,
        user_id=user.id,
        video_id=video.id,
        start_time=datetime(day.year, day.month, day.day, sh, sm),
        end_time=datetime(day.year, day.month, day.day, eh, em),
    )
    db.add(ls)
    db.commit()
    db.refresh(ls)
    return ls


def _add_progress(db, user, day, streak=0):
    dp = DailyProgress(user_id=user.id, day=day, streak=streak)
    db.add(dp)
    db.commit()
    db.refresh(dp)
    return dp


# ---------------------------------------------------------------------------
# MD-107  save_daily_progress()
# ---------------------------------------------------------------------------
def test_first_session_of_day_creates_record(progress_db):
    """First session of a day creates a committed progress record."""
    user = _seed_user(progress_db)
    video = _seed_video(progress_db)
    day = date(2026, 1, 10)
    session = _add_session(progress_db, user, video, day, "s1", "09:00", "09:10")

    save_daily_progress(session, progress_db)

    rows = (progress_db.query(DailyProgress)
            .filter(DailyProgress.user_id == user.id, DailyProgress.day == day)
            .all())
    assert len(rows) == 1
    dp = rows[0]
    assert dp.sessions_count == 1
    assert dp.streak == 1               # no day-1 record -> streak starts at 1
    assert dp.study_seconds == 600      # 09:00 -> 09:10
    assert dp.id is not None            # committed / flushed


def test_later_session_same_day_updates_in_place(progress_db):
    """A second session on the same day updates the row in place; streak -> 5."""
    user = _seed_user(progress_db)
    video = _seed_video(progress_db)
    day = date(2026, 1, 10)

    # Yesterday's progress with streak = 4.
    _add_progress(progress_db, user, day - timedelta(days=1), streak=4)

    first = _add_session(progress_db, user, video, day, "s1", "09:00", "09:10")
    save_daily_progress(first, progress_db)

    created = get_daily_progress(user.id, day, progress_db)
    original_id = created.id
    assert created.streak == 5
    assert created.sessions_count == 1

    second = _add_session(progress_db, user, video, day, "s2", "12:00", "12:20")
    save_daily_progress(second, progress_db)

    rows = (progress_db.query(DailyProgress)
            .filter(DailyProgress.user_id == user.id, DailyProgress.day == day)
            .all())
    assert len(rows) == 1                  # no duplicate row
    assert rows[0].id == original_id       # updated in place
    assert rows[0].streak == 5
    assert rows[0].sessions_count == 2


def test_streak_resets_after_a_gap(progress_db):
    """With no day-1 record, the saved streak is 1."""
    user = _seed_user(progress_db)
    video = _seed_video(progress_db)
    day = date(2026, 1, 10)                # nothing exists for Jan 9
    session = _add_session(progress_db, user, video, day, "s1")

    save_daily_progress(session, progress_db)

    dp = get_daily_progress(user.id, day, progress_db)
    assert dp is not None
    assert dp.streak == 1


# ---------------------------------------------------------------------------
# MD-108  get_all_time_progress()
# ---------------------------------------------------------------------------
def test_returns_only_requested_users_rows(progress_db):
    """User 1 has 3 rows, user 2 has 5; only user 1's 3 come back."""
    user1 = _seed_user(progress_db, email="u1@example.com")
    user2 = _seed_user(progress_db, email="u2@example.com")
    for i in range(3):
        _add_progress(progress_db, user1, date(2026, 1, 1) + timedelta(days=i))
    for i in range(5):
        _add_progress(progress_db, user2, date(2026, 1, 1) + timedelta(days=i))

    rows = get_all_time_progress(user1.id, progress_db)
    assert len(rows) == 3
    assert all(r.user_id == user1.id for r in rows)


def test_user_with_no_progress_returns_empty_list(progress_db):
    """A user with no rows gets [] and no exception."""
    _seed_user(progress_db, email="u1@example.com")
    user2 = _seed_user(progress_db, email="u2@example.com")

    rows = get_all_time_progress(user2.id, progress_db)
    assert rows == []


# ---------------------------------------------------------------------------
# MD-109  get_daily_progress()
# ---------------------------------------------------------------------------
def test_record_exists_for_requested_day(progress_db):
    """The matching DailyProgress object is returned."""
    user = _seed_user(progress_db)
    day = date(2026, 1, 10)
    dp = _add_progress(progress_db, user, day, streak=2)

    found = get_daily_progress(user.id, day, progress_db)
    assert found is not None
    assert found.id == dp.id
    assert found.day == day


def test_no_matching_user_day_pair_returns_none(progress_db):
    """Wrong day, or right day but wrong user, both return None."""
    user1 = _seed_user(progress_db, email="u1@example.com")
    user2 = _seed_user(progress_db, email="u2@example.com")
    day = date(2026, 1, 10)
    _add_progress(progress_db, user1, day)

    assert get_daily_progress(user1.id, date(2026, 1, 11), progress_db) is None  # other day
    assert get_daily_progress(user2.id, day, progress_db) is None               # other user


# ---------------------------------------------------------------------------
# MD-110  get_daily_progress_by_date_range()
# ---------------------------------------------------------------------------
def _seed_range(db):
    user = _seed_user(db)
    for d in (date(2026, 1, 1), date(2026, 1, 5), date(2026, 1, 10)):
        _add_progress(db, user, d)
    return user


def test_both_bounds_are_inclusive(progress_db):
    """start=Jan 1, end=Jan 10 returns all 3 rows incl. boundaries."""
    user = _seed_range(progress_db)

    rows = get_daily_progress_by_date_range(
        user.id, date(2026, 1, 1), date(2026, 1, 10), progress_db)
    assert sorted(r.day for r in rows) == [
        date(2026, 1, 1), date(2026, 1, 5), date(2026, 1, 10)]


def test_open_bounds_are_honoured(progress_db):
    """start=None/end=Jan 5 -> {Jan 1, Jan 5}; both None -> all rows."""
    user = _seed_range(progress_db)

    upto_jan5 = get_daily_progress_by_date_range(
        user.id, None, date(2026, 1, 5), progress_db)
    assert sorted(r.day for r in upto_jan5) == [date(2026, 1, 1), date(2026, 1, 5)]

    everything = get_daily_progress_by_date_range(user.id, None, None, progress_db)
    assert sorted(r.day for r in everything) == [
        date(2026, 1, 1), date(2026, 1, 5), date(2026, 1, 10)]


def test_range_containing_no_data_returns_empty_list(progress_db):
    """A Feb 2026 range over Jan-only data returns []."""
    user = _seed_range(progress_db)

    rows = get_daily_progress_by_date_range(
        user.id, date(2026, 2, 1), date(2026, 2, 28), progress_db)
    assert rows == []
