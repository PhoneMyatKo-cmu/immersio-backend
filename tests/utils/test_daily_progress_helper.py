"""
Tests for utils/daily_progress_helper.py

Covers docs/test_case_specification.pdf MD-129 .. MD-137:

  MD-129  create_daily_progress()      - new record initialised to zero, not persisted
  MD-130  update_daily_progress()      - metrics recomputed (not accumulated); empty list
  MD-131  calculate_study_seconds()    - sums duration; empty list / fractional seconds
  MD-132  calculate_daily_videos_watched() - counts distinct videos; empty list
  MD-133  calculate_total_videos_watched() - distinct videos all-time; user with none
  MD-134  calculate_new_vocab_seen()   - first-time vocab counted once; no exposure
  MD-135  calculate_new_vocab_known()  - only vocab newly crossing the threshold counts
  MD-136  calculate_streak()           - increments from the previous day; no prior day
  MD-137  summarize_daily_progresses() - only requested metrics; latest-row / streak rules

[integration] Self-contained in-memory SQLite session (`helper_db`).
"""

from datetime import date, datetime, timedelta

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
    from models.daily_progress import DailyProgress
    from models.learning_session import LearningSession
    from models.session_vocab import SessionVocabulary
    from models.user_vocab_profile import UserVocabularyExposure
    from utils.daily_progress_helper import (
        create_daily_progress,
        update_daily_progress,
        calculate_study_seconds,
        calculate_daily_videos_watched,
        calculate_total_videos_watched,
        calculate_new_vocab_seen,
        calculate_new_vocab_known,
        calculate_streak,
        summarize_daily_progresses,
    )
except Exception as exc:  # pragma: no cover - import guard
    pytest.skip(f"daily_progress_helper unavailable: {exc}", allow_module_level=True)

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
def helper_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
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


def _add_session(db, sid, user_id, video_id, start, end):
    ls = LearningSession(id=sid, user_id=user_id, video_id=video_id,
                         start_time=start, end_time=end)
    db.add(ls)
    db.commit()
    db.refresh(ls)
    return ls


def _detached_session(user_id=1, video_id=1, minutes=5, end=None):
    """A LearningSession not attached to any DB, for the pure calculators."""
    end = end or datetime(2026, 1, 10, 9, minutes)
    return LearningSession(user_id=user_id, video_id=video_id,
                           start_time=end - timedelta(minutes=minutes), end_time=end)


# ---------------------------------------------------------------------------
# MD-129  create_daily_progress()
# ---------------------------------------------------------------------------
def test_new_record_is_zeroed_and_not_persisted(helper_db):
    """Every metric starts at 0 and no row is written without an explicit add."""
    dp = create_daily_progress(user_id=1, day=date(2026, 1, 10))

    assert dp.user_id == 1 and dp.day == date(2026, 1, 10)
    for field in ("study_seconds", "videos_watched", "total_videos_watched",
                  "new_vocab_seen", "new_vocab_known", "sessions_count", "streak"):
        assert getattr(dp, field) == 0
    assert helper_db.query(DailyProgress).count() == 0


# ---------------------------------------------------------------------------
# MD-130  update_daily_progress()
# ---------------------------------------------------------------------------
def test_metrics_are_recomputed_not_accumulated(helper_db):
    """The record's metrics reflect the day's sessions, not prior values plus new."""
    user = _seed_user(helper_db)
    v1 = _seed_video(helper_db, "vid00000001")
    v2 = _seed_video(helper_db, "vid00000002")
    day = date(2026, 1, 10)
    s1 = _add_session(helper_db, "s1", user.id, v1.id,
                      datetime(2026, 1, 10, 9, 0), datetime(2026, 1, 10, 9, 5))
    s2 = _add_session(helper_db, "s2", user.id, v1.id,
                      datetime(2026, 1, 10, 10, 0), datetime(2026, 1, 10, 10, 5))
    s3 = _add_session(helper_db, "s3", user.id, v2.id,
                      datetime(2026, 1, 10, 11, 0), datetime(2026, 1, 10, 11, 5))

    dp = DailyProgress(user_id=user.id, day=day, study_seconds=500)
    result = update_daily_progress([s1, s2, s3], dp, helper_db)

    assert result.videos_watched == 2
    assert result.sessions_count == 3
    assert result.study_seconds == 900          # 3 * 5 min, recomputed (not 500 + ...)


def test_empty_session_list_raises_index_error(helper_db):
    """update_daily_progress assumes at least one session."""
    dp = DailyProgress(user_id=1, day=date(2026, 1, 10))
    with pytest.raises(IndexError):
        update_daily_progress([], dp, helper_db)


# ---------------------------------------------------------------------------
# MD-131  calculate_study_seconds()
# ---------------------------------------------------------------------------
def test_sums_duration_across_sessions():
    """Durations are summed and returned as an int."""
    a = _detached_session(minutes=5, end=datetime(2026, 1, 10, 9, 5))   # 300s
    b = LearningSession(user_id=1, video_id=1,
                        start_time=datetime(2026, 1, 10, 10, 0),
                        end_time=datetime(2026, 1, 10, 10, 7, 30))        # 450s
    assert calculate_study_seconds([a, b]) == 750


def test_study_seconds_empty_list_and_fractional_truncation():
    """[] -> 0; fractional seconds are truncated, not rounded."""
    assert calculate_study_seconds([]) == 0
    frac = LearningSession(user_id=1, video_id=1,
                           start_time=datetime(2026, 1, 10, 9, 0, 0),
                           end_time=datetime(2026, 1, 10, 9, 5, 0, 900_000))  # 300.9s
    assert calculate_study_seconds([frac]) == 300


# ---------------------------------------------------------------------------
# MD-132  calculate_daily_videos_watched()
# ---------------------------------------------------------------------------
def test_counts_distinct_videos_only():
    """Distinct video ids are counted; repeats on one video count once."""
    distinct = [_detached_session(video_id=v) for v in (10, 11, 12)]
    assert calculate_daily_videos_watched(distinct) == 3

    same = [_detached_session(video_id=10) for _ in range(3)]
    assert calculate_daily_videos_watched(same) == 1


def test_daily_videos_watched_empty_list():
    assert calculate_daily_videos_watched([]) == 0


# ---------------------------------------------------------------------------
# MD-133  calculate_total_videos_watched()
# ---------------------------------------------------------------------------
def test_distinct_videos_across_all_time(helper_db):
    """Rewatching a video does not inflate the all-time distinct count."""
    user = _seed_user(helper_db)
    videos = [_seed_video(helper_db, f"vid0000000{i}") for i in range(4)]
    base = datetime(2026, 1, 10, 9, 0)
    plan = [0, 0, 0, 1, 1, 2, 3, 3, 3, 0]  # 10 sessions, 4 distinct videos
    for i, vi in enumerate(plan):
        _add_session(helper_db, f"s{i}", user.id, videos[vi].id,
                     base, base + timedelta(minutes=5))

    assert calculate_total_videos_watched(user.id, helper_db) == 4


def test_total_videos_watched_user_with_no_sessions(helper_db):
    user = _seed_user(helper_db)
    assert calculate_total_videos_watched(user.id, helper_db) == 0


# ---------------------------------------------------------------------------
# MD-134  calculate_new_vocab_seen()
# ---------------------------------------------------------------------------
def _expose(db, user_id, vocab_id, seen_count, status="SEEN"):
    row = UserVocabularyExposure(user_id=user_id, vocab_id=vocab_id,
                                 seen_count=seen_count, status=status,
                                 first_seen_at=datetime(2026, 1, 1),
                                 last_seen_at=datetime(2026, 1, 1))
    db.add(row)
    db.commit()
    return row


def _link_vocab(db, session_id, vocab_id):
    db.add(SessionVocabulary(session_id=session_id, vocab_id=vocab_id))
    db.commit()


def test_first_time_vocab_counted_prior_vocab_not(helper_db):
    """A vocab whose all-time count equals today's exposure is new; others are not."""
    user = _seed_user(helper_db)
    video = _seed_video(helper_db)
    s = _add_session(helper_db, "s1", user.id, video.id,
                     datetime(2026, 1, 10, 9, 0), datetime(2026, 1, 10, 9, 5))
    _link_vocab(helper_db, s.id, 50)
    _link_vocab(helper_db, s.id, 51)
    _expose(helper_db, user.id, 50, seen_count=1)
    _expose(helper_db, user.id, 51, seen_count=5)
    helper_db.refresh(s)

    assert calculate_new_vocab_seen([s], helper_db) == 1


def test_same_vocab_across_two_sessions_counts_once(helper_db):
    """One vocab seen in two of the day's sessions is counted a single time."""
    user = _seed_user(helper_db)
    video = _seed_video(helper_db)
    s1 = _add_session(helper_db, "s1", user.id, video.id,
                      datetime(2026, 1, 10, 9, 0), datetime(2026, 1, 10, 9, 5))
    s2 = _add_session(helper_db, "s2", user.id, video.id,
                      datetime(2026, 1, 10, 12, 0), datetime(2026, 1, 10, 12, 5))
    _link_vocab(helper_db, s1.id, 50)
    _link_vocab(helper_db, s2.id, 50)
    _expose(helper_db, user.id, 50, seen_count=2)
    helper_db.refresh(s1)
    helper_db.refresh(s2)

    assert calculate_new_vocab_seen([s1, s2], helper_db) == 1


def test_new_vocab_seen_without_any_exposure(helper_db):
    """Sessions with no SessionVocabulary rows yield 0."""
    user = _seed_user(helper_db)
    video = _seed_video(helper_db)
    s = _add_session(helper_db, "s1", user.id, video.id,
                     datetime(2026, 1, 10, 9, 0), datetime(2026, 1, 10, 9, 5))
    helper_db.refresh(s)

    assert calculate_new_vocab_seen([s], helper_db) == 0


# ---------------------------------------------------------------------------
# MD-135  calculate_new_vocab_known()
# ---------------------------------------------------------------------------
def test_only_newly_promoted_known_vocab_is_counted(helper_db):
    """A vocab that crossed the threshold today counts; one already far above does not."""
    user = _seed_user(helper_db)
    video = _seed_video(helper_db)
    s = _add_session(helper_db, "s1", user.id, video.id,
                     datetime(2026, 1, 10, 9, 0), datetime(2026, 1, 10, 9, 5))
    _link_vocab(helper_db, s.id, 50)
    _link_vocab(helper_db, s.id, 51)
    _expose(helper_db, user.id, 50, seen_count=11, status="KNOW")  # 11 - 1 today = 10 -> new
    _expose(helper_db, user.id, 51, seen_count=50, status="KNOW")  # 50 - 1 today = 49 -> old
    helper_db.refresh(s)

    assert calculate_new_vocab_known([s], helper_db) == 1


def test_new_vocab_known_ignores_non_known_and_empty_sessions(helper_db):
    """Only KNOW-status exposure is considered; no session vocab yields 0."""
    user = _seed_user(helper_db)
    video = _seed_video(helper_db)
    s = _add_session(helper_db, "s1", user.id, video.id,
                     datetime(2026, 1, 10, 9, 0), datetime(2026, 1, 10, 9, 5))
    _link_vocab(helper_db, s.id, 50)
    _expose(helper_db, user.id, 50, seen_count=4, status="SEEN")  # not KNOW -> excluded
    helper_db.refresh(s)
    assert calculate_new_vocab_known([s], helper_db) == 0

    bare = _add_session(helper_db, "s2", user.id, video.id,
                        datetime(2026, 1, 10, 10, 0), datetime(2026, 1, 10, 10, 5))
    helper_db.refresh(bare)
    assert calculate_new_vocab_known([bare], helper_db) == 0


# ---------------------------------------------------------------------------
# MD-136  calculate_streak()
# ---------------------------------------------------------------------------
def test_streak_increments_from_the_previous_day(helper_db):
    """A previous-day record with streak 6 yields 7."""
    user = _seed_user(helper_db)
    helper_db.add(DailyProgress(user_id=user.id, day=date(2026, 1, 9), streak=6))
    helper_db.commit()
    session = _detached_session(user_id=user.id, end=datetime(2026, 1, 10, 9, 0))

    assert calculate_streak(session, helper_db) == 7


def test_streak_without_previous_day_activity(helper_db):
    """No previous-day row, or one with streak 0, both give 1."""
    user = _seed_user(helper_db)
    session = _detached_session(user_id=user.id, end=datetime(2026, 1, 10, 9, 0))
    assert calculate_streak(session, helper_db) == 1

    helper_db.add(DailyProgress(user_id=user.id, day=date(2026, 1, 9), streak=0))
    helper_db.commit()
    assert calculate_streak(session, helper_db) == 1


# ---------------------------------------------------------------------------
# MD-137  summarize_daily_progresses()
# ---------------------------------------------------------------------------
def _progress(day, **metrics):
    return DailyProgress(user_id=1, day=day, **metrics)


def test_only_requested_metrics_are_computed():
    """Metrics not named in `types` come back as None."""
    rows = [_progress(date(2026, 1, d), study_seconds=100) for d in (1, 2, 3)]
    out = summarize_daily_progresses(rows, ["study_seconds"], None)

    assert out["study_seconds"] == 300
    assert out["total_videos_watched"] is None
    assert out["vocab_seen"] is None and out["vocab_known"] is None
    assert out["streak"] is None


def test_total_videos_watched_read_from_latest_record():
    """total_videos_watched is taken from the last row, not summed."""
    rows = [_progress(date(2026, 1, d), total_videos_watched=n)
            for d, n in ((1, 3), (2, 5), (3, 8))]
    out = summarize_daily_progresses(rows, ["total_videos_watched"], None)
    assert out["total_videos_watched"] == 8


def test_streak_resolution_and_fallback():
    """Streak survives from today or yesterday, but not from an older row."""
    today = date.today()
    a = summarize_daily_progresses([_progress(today, streak=9)], ["streak"], None)
    assert a["streak"] == 9

    b = summarize_daily_progresses(
        [_progress(today - timedelta(days=1), streak=9)], ["streak"], None)
    assert b["streak"] == 9

    c = summarize_daily_progresses(
        [_progress(today - timedelta(days=5), streak=9)], ["streak"], None)
    assert c["streak"] == 0


def test_empty_progress_list():
    """All requested metrics resolve to 0 with no IndexError."""
    out = summarize_daily_progresses(
        [], ["study_seconds", "total_videos_watched", "vocab_seen",
             "vocab_known", "streak"], None)
    assert out == {
        "study_seconds": 0, "total_videos_watched": 0,
        "vocab_seen": 0, "vocab_known": 0, "streak": 0,
    }
