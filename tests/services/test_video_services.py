"""
Tests for services/video/video_services.py  (Video Submission — Service / DB)

Planned scope (docs/test_plan.md §5.2, DBS-01..04):
  save_video, check_video_exists, get_video_by_id,
  get_video_by_youtube_video_id, change_shadowing_status

Feed/listing methods (get_videos, get_total_video_count) are covered by the
SQLite-backed tests merged from origin/dev below. The remaining feed/difficulty
helpers (save_vocabulary_profile, save_difficulty_level, and the commented-out
difficulty helpers) stay with the feed/difficulty owner.

[integration] The DBS-* tests use the real Postgres test database via the
db_session fixture (models use PostgreSQL JSONB, so a Postgres test DB is
required; the fixture skips if it is unreachable). The get_videos /
get_total_video_count tests use a self-contained in-memory SQLite session
(service_db). The module skips if its import deps (isodate, etc.) are missing.
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

try:
    from models.video import Video
    from services.video.video_services import (
        save_video,
        check_video_exists,
        get_video_by_id,
        get_video_by_youtube_video_id,
        change_shadowing_status,
        get_videos,
        get_total_video_count,
    )
except Exception as exc:  # isodate / import-chain deps missing
    pytest.skip(f"video_services unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.integration, pytest.mark.video_submission]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_video(db, youtube_video_id="dQw4w9WgXcQ", title="日本語レッスン", is_ready=False):
    video = Video(
        youtube_video_id=youtube_video_id,
        title=title,
        thumbnail_url="https://i.ytimg.com/vi/x/hqdefault.jpg",
        channel_name="Nihongo Channel",
        duration_seconds=180,
        is_shadowing_ready=is_ready,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


@pytest.fixture()
def service_db():
    """In-memory SQLite session for the feed/listing tests (no Postgres needed)."""
    import models.processed_caption  # noqa: F401
    import models.sentence  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Video.__table__.create(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Video.__table__.drop(engine)
        engine.dispose()


def _video(
    youtube_video_id: str,
    title: str,
    created_at,
    channel_name: str = "Immersio",
) -> Video:
    return Video(
        youtube_video_id=youtube_video_id,
        title=title,
        thumbnail_url=f"https://example.com/{youtube_video_id}.jpg",
        channel_name=channel_name,
        created_at=created_at,
        duration_seconds=180,
    )


# ---------------------------------------------------------------------------
# get_videos / get_total_video_count  (feed/listing — from origin/dev)
# ---------------------------------------------------------------------------
def test_get_videos_returns_newest_videos_with_total_count(service_db):
    from datetime import datetime, timedelta

    now = datetime(2026, 1, 1, 12, 0, 0)
    oldest = _video("oldest", "Old Nihongo Lesson", now - timedelta(days=2))
    newest = _video("newest", "Newest Nihongo Lesson", now)
    middle = _video("middle", "Middle Nihongo Lesson", now - timedelta(days=1))
    service_db.add_all([oldest, newest, middle])
    service_db.commit()

    videos, total_videos = get_videos(service_db, page=1, page_size=2)

    assert [video.youtube_video_id for video in videos] == ["newest", "middle"]
    assert total_videos == 3


def test_get_videos_filters_by_search_before_paginating(service_db):
    from datetime import datetime, timedelta

    now = datetime(2026, 1, 1, 12, 0, 0)
    service_db.add_all(
        [
            _video("grammar-new", "Japanese Grammar Patterns", now),
            _video("listening", "Listening Practice", now - timedelta(minutes=1)),
            _video("grammar-old", "Beginner grammar drill", now - timedelta(minutes=2)),
        ]
    )
    service_db.commit()

    videos, total_videos = get_videos(
        service_db, search="grammar", page=1, page_size=1
    )

    assert [video.youtube_video_id for video in videos] == ["grammar-new"]
    assert total_videos == 2


def test_get_videos_returns_requested_page(service_db):
    from datetime import datetime, timedelta

    now = datetime(2026, 1, 1, 12, 0, 0)
    service_db.add_all(
        [
            _video("first", "First", now),
            _video("second", "Second", now - timedelta(minutes=1)),
            _video("third", "Third", now - timedelta(minutes=2)),
        ]
    )
    service_db.commit()

    videos, total_videos = get_videos(service_db, page=2, page_size=2)

    assert [video.youtube_video_id for video in videos] == ["third"]
    assert total_videos == 3


def test_get_total_video_count_counts_rows_from_statement(service_db):
    from datetime import datetime

    now = datetime(2026, 1, 1, 12, 0, 0)
    service_db.add_all(
        [
            _video("japanese-one", "Japanese Conversation", now),
            _video("japanese-two", "Japanese News", now),
            _video("spanish-one", "Spanish Conversation", now),
        ]
    )
    service_db.commit()

    stmt = select(Video).where(Video.title.ilike("%Japanese%"))

    assert get_total_video_count(service_db, stmt) == 2


# --- DBS-01 -----------------------------------------------------------------
def test_save_video_persists_row_and_parses_iso_duration(db_session):
    meta = {
        "video_id": "abc12345678",
        "title": "テスト動画",
        "thumbnail_url": "https://i.ytimg.com/vi/abc/hqdefault.jpg",
        "channel_name": "Channel",
        "duration": "PT3M",  # ISO-8601 -> 180 seconds
    }
    result = save_video(meta, suitability={}, db=db_session)

    assert result["title"] == "テスト動画"
    assert isinstance(result["video_id"], int)

    row = db_session.scalars(
        select(Video).where(Video.id == result["video_id"])
    ).first()
    assert row is not None
    assert row.youtube_video_id == "abc12345678"
    assert row.duration_seconds == 180
    assert row.is_shadowing_ready is False  # default


# --- DBS-02 -----------------------------------------------------------------
def test_check_video_exists_returns_row_then_none(db_session):
    _make_video(db_session, youtube_video_id="exists123456")
    assert check_video_exists("exists123456", db_session) is not None
    assert check_video_exists("missing00000", db_session) is None


# --- DBS-03 -----------------------------------------------------------------
def test_get_video_by_id_and_by_youtube_id(db_session):
    video = _make_video(db_session, youtube_video_id="vid123456789")
    assert get_video_by_id(video.id, db_session).youtube_video_id == "vid123456789"
    assert get_video_by_youtube_video_id("vid123456789", db_session).id == video.id
    assert get_video_by_id(999999, db_session) is None


# --- DBS-04 -----------------------------------------------------------------
def test_change_shadowing_status_sets_flag_true(db_session):
    video = _make_video(db_session, is_ready=False)
    change_shadowing_status(video.id, db_session)
    refreshed = db_session.scalars(
        select(Video).where(Video.id == video.id)
    ).first()
    assert refreshed.is_shadowing_ready is True
