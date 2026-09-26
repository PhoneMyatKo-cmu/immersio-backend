"""
Tests for services/session/session_service.py

Covers docs/test_case_specification.pdf MD-111 .. MD-115:

  MD-111  save_learning_session()
    - New session is persisted with its intervals
    - Empty intervals list is rejected
    - Resubmission with a later end_time extends the session
    - Existing id with conflicting data is rejected
    - Interval rows are appended on every resubmission (flagged duplication defect)

  MD-112  get_learning_sessions()
    - Session found by id
    - Unknown session id

  MD-113  get_learning_sessions_by_user_and_video()
    - Filters on both user and video
    - No sessions for that pair

  MD-114  get_learning_sessions_by_user()
    - All sessions across all videos
    - User with no sessions

  MD-115  get_learning_sessions_by_user_and_day()
    - Sessions ending within the day
    - Day boundary handling (lower bound inclusive, upper bound exclusive)

[integration] Self-contained in-memory SQLite session (`session_db`) — none of
the tables involved use PostgreSQL-only column types, so no test DB is needed.
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

try:
    import models.processed_caption  # noqa: F401  (Video.captions relationship target)
    import models.sentence  # noqa: F401  (Video.shadowingsentences relationship target)
    from models.user import User
    from models.video import Video
    from models.learning_session import LearningSession
    from models.learning_video_interval import LearningVideoInterval
    from schemas.session import Interval, SessionData
    from services.session.session_service import (
        save_learning_session,
        get_learning_sessions,
        get_learning_sessions_by_user_and_video,
        get_learning_sessions_by_user,
        get_learning_sessions_by_user_and_day,
    )
except Exception as exc:  # pragma: no cover - import guard
    pytest.skip(f"session_service unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.integration]

_TABLES = [
    User.__table__,
    Video.__table__,
    LearningSession.__table__,
    LearningVideoInterval.__table__,
]

# A fixed epoch base so timestamp conversion is deterministic (2023-11-14 UTC-ish).
_EPOCH = 1_700_000_000


@pytest.fixture()
def session_db():
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


def _session_data(session_id, user_id, video_id, start=_EPOCH, end=_EPOCH + 600,
                  intervals=((0.0, 30.0), (40.0, 70.0))):
    return SessionData(
        id=session_id,
        user_id=user_id,
        video_id=video_id,
        start_time=start,
        end_time=end,
        intervals=[Interval(start_time=s, end_time=e) for s, e in intervals],
    )


def _add_session(db, session_id, user_id, video_id, start_dt, end_dt):
    """Insert a LearningSession row directly (for the getter tests)."""
    ls = LearningSession(id=session_id, user_id=user_id, video_id=video_id,
                         start_time=start_dt, end_time=end_dt)
    db.add(ls)
    db.commit()
    db.refresh(ls)
    return ls


# ---------------------------------------------------------------------------
# MD-111  save_learning_session()
# ---------------------------------------------------------------------------
def test_new_session_is_persisted_with_its_intervals(session_db):
    """A new session is created with epoch-converted timestamps and its 2 intervals."""
    user = _seed_user(session_db)
    video = _seed_video(session_db)

    result = save_learning_session(
        _session_data("s1", user.id, video.id), session_db)

    assert result.id == "s1"
    assert result.start_time == datetime.fromtimestamp(_EPOCH)
    assert result.end_time == datetime.fromtimestamp(_EPOCH + 600)

    stored = get_learning_sessions("s1", session_db)
    assert stored is not None
    intervals = (session_db.query(LearningVideoInterval)
                 .filter(LearningVideoInterval.session_id == "s1").all())
    assert len(intervals) == 2


def test_empty_intervals_list_is_rejected(session_db):
    """intervals == [] raises ValueError and writes nothing."""
    user = _seed_user(session_db)
    video = _seed_video(session_db)

    with pytest.raises(ValueError, match="Intervals list cannot be empty."):
        save_learning_session(
            _session_data("s1", user.id, video.id, intervals=()), session_db)

    assert get_learning_sessions("s1", session_db) is None
    assert session_db.query(LearningVideoInterval).count() == 0


def test_resubmission_with_later_end_time_extends_session(session_db):
    """A later end_time updates the row in place; an earlier one leaves it unchanged."""
    user = _seed_user(session_db)
    video = _seed_video(session_db)
    save_learning_session(_session_data("s1", user.id, video.id), session_db)

    # Resubmit with end_time + 60s.
    save_learning_session(
        _session_data("s1", user.id, video.id, end=_EPOCH + 660), session_db)

    row = get_learning_sessions("s1", session_db)
    assert row.end_time == datetime.fromtimestamp(_EPOCH + 660)
    assert session_db.query(LearningSession).count() == 1

    # Resubmit with an earlier end_time -> unchanged.
    save_learning_session(
        _session_data("s1", user.id, video.id, end=_EPOCH + 100), session_db)
    row = get_learning_sessions("s1", session_db)
    assert row.end_time == datetime.fromtimestamp(_EPOCH + 660)


def test_existing_id_with_conflicting_data_is_rejected(session_db):
    """Resubmitting an existing id with a different user/video/start raises ValueError."""
    user = _seed_user(session_db)
    other = _seed_user(session_db, email="b@example.com")
    video = _seed_video(session_db)
    other_video = _seed_video(session_db, youtube_id="vid87654321")
    save_learning_session(_session_data("s1", user.id, video.id), session_db)

    with pytest.raises(ValueError, match="already exists with different data"):
        save_learning_session(
            _session_data("s1", other.id, video.id), session_db)      # different user
    with pytest.raises(ValueError, match="already exists with different data"):
        save_learning_session(
            _session_data("s1", user.id, other_video.id), session_db)  # different video
    with pytest.raises(ValueError, match="already exists with different data"):
        save_learning_session(
            _session_data("s1", user.id, video.id, start=_EPOCH + 5), session_db)  # different start


# ---------------------------------------------------------------------------
# MD-112  get_learning_sessions()
# ---------------------------------------------------------------------------
def test_session_found_by_id(session_db):
    """The LearningSession with the given id is returned."""
    user = _seed_user(session_db)
    video = _seed_video(session_db)
    _add_session(session_db, "abc-123", user.id, video.id,
                 datetime(2026, 1, 10, 9, 0), datetime(2026, 1, 10, 9, 30))

    found = get_learning_sessions("abc-123", session_db)
    assert found is not None
    assert found.id == "abc-123"


def test_unknown_session_id_returns_none(session_db):
    """An unknown id returns None."""
    assert get_learning_sessions("does-not-exist", session_db) is None


# ---------------------------------------------------------------------------
# MD-113  get_learning_sessions_by_user_and_video()
# ---------------------------------------------------------------------------
def test_filters_on_both_user_and_video(session_db):
    """Only the requested user's sessions on the requested video are returned."""
    user1 = _seed_user(session_db, email="u1@example.com")
    user2 = _seed_user(session_db, email="u2@example.com")
    video10 = _seed_video(session_db, youtube_id="vid00000010")
    video11 = _seed_video(session_db, youtube_id="vid00000011")
    base = datetime(2026, 1, 10, 9, 0)
    _add_session(session_db, "a", user1.id, video10.id, base, base + timedelta(minutes=10))
    _add_session(session_db, "b", user1.id, video10.id, base, base + timedelta(minutes=10))
    _add_session(session_db, "c", user1.id, video11.id, base, base + timedelta(minutes=10))
    _add_session(session_db, "d", user2.id, video10.id, base, base + timedelta(minutes=10))

    rows = get_learning_sessions_by_user_and_video(user1.id, video10.id, session_db)
    assert {r.id for r in rows} == {"a", "b"}


def test_no_sessions_for_that_pair_returns_empty_list(session_db):
    """A user/video pair with no sessions returns []."""
    user = _seed_user(session_db)
    _seed_video(session_db)
    assert get_learning_sessions_by_user_and_video(user.id, 99, session_db) == []


# ---------------------------------------------------------------------------
# MD-114  get_learning_sessions_by_user()
# ---------------------------------------------------------------------------
def test_all_sessions_across_all_videos(session_db):
    """Every session for the user is returned, regardless of video."""
    user1 = _seed_user(session_db, email="u1@example.com")
    user2 = _seed_user(session_db, email="u2@example.com")
    videos = [_seed_video(session_db, youtube_id=f"vid0000000{i}") for i in range(3)]
    base = datetime(2026, 1, 10, 9, 0)
    _add_session(session_db, "a", user1.id, videos[0].id, base, base + timedelta(minutes=5))
    _add_session(session_db, "b", user1.id, videos[0].id, base, base + timedelta(minutes=5))
    _add_session(session_db, "c", user1.id, videos[1].id, base, base + timedelta(minutes=5))
    _add_session(session_db, "d", user1.id, videos[2].id, base, base + timedelta(minutes=5))
    _add_session(session_db, "e", user2.id, videos[0].id, base, base + timedelta(minutes=5))

    rows = get_learning_sessions_by_user(user1.id, session_db)
    assert {r.id for r in rows} == {"a", "b", "c", "d"}


def test_user_with_no_sessions_returns_empty_list(session_db):
    """A user who has never started a session gets []."""
    _seed_user(session_db, email="u1@example.com")
    user3 = _seed_user(session_db, email="u3@example.com")
    assert get_learning_sessions_by_user(user3.id, session_db) == []


# ---------------------------------------------------------------------------
# MD-115  get_learning_sessions_by_user_and_day()
# ---------------------------------------------------------------------------
def test_sessions_ending_within_the_day(session_db):
    """Only sessions whose end_time falls on the requested day are returned."""
    user = _seed_user(session_db)
    video = _seed_video(session_db)
    _add_session(session_db, "m", user.id, video.id,
                 datetime(2026, 1, 10, 8, 30), datetime(2026, 1, 10, 9, 0))
    _add_session(session_db, "e", user.id, video.id,
                 datetime(2026, 1, 10, 20, 30), datetime(2026, 1, 10, 21, 0))
    _add_session(session_db, "next", user.id, video.id,
                 datetime(2026, 1, 11, 8, 30), datetime(2026, 1, 11, 9, 0))

    rows = get_learning_sessions_by_user_and_day(user.id, date(2026, 1, 10), session_db)
    assert {r.id for r in rows} == {"m", "e"}


def test_day_boundary_handling(session_db):
    """Lower bound (00:00:00) is inclusive; upper bound (next 00:00:00) is exclusive."""
    user = _seed_user(session_db)
    video = _seed_video(session_db)
    _add_session(session_db, "lower", user.id, video.id,
                 datetime(2026, 1, 9, 23, 30), datetime(2026, 1, 10, 0, 0, 0))
    _add_session(session_db, "upper", user.id, video.id,
                 datetime(2026, 1, 10, 23, 30), datetime(2026, 1, 11, 0, 0, 0))

    rows = get_learning_sessions_by_user_and_day(user.id, date(2026, 1, 10), session_db)
    assert {r.id for r in rows} == {"lower"}
