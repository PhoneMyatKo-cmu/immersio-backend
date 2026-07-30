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
    from models.video import Video, VideoSource
    from services.video.video_services import (
        change_shadowing_status,
        check_video_exists,
        get_total_video_count,
        get_video_by_id,
        get_video_by_youtube_video_id,
        get_video_stats,
        get_videos,
        get_videos_admin,
        save_video,
        soft_delete_video,
    )
except Exception as exc:  # isodate / import-chain deps missing
    pytest.skip(f"video_services unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.integration, pytest.mark.video_submission]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_video(
    db, youtube_video_id="dQw4w9WgXcQ", title="日本語レッスン", is_ready=False
):
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

    videos, total_videos = get_videos(service_db, search="grammar", page=1, page_size=1)

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


# My Test
# def test_save_video_behave_how_on_duplicate_id(db_session):
#     meta = {
#         "video_id": "abc12345678",
#         "title": "テスト動画",
#         "thumbnail_url": "https://i.ytimg.com/vi/abc/hqdefault.jpg",
#         "channel_name": "Channel",
#         "duration": "PT3M",  # ISO-8601 -> 180 seconds
#     }
#     save_video(meta, suitability={}, db=db_session)
#     result2 = save_video(meta, suitability={}, db=db_session)

#     assert isinstance(result2["video_id"], int)


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
    refreshed = db_session.scalars(select(Video).where(Video.id == video.id)).first()
    assert refreshed.is_shadowing_ready is True


# ---------------------------------------------------------------------------
# get_videos_admin  (admin list / filter)
#
# Runs on the SQLite service_db fixture: title ILIKE is SQLite-safe and only the
# videos table is touched (FK enforcement is off, so added_by needs no users row).
# ---------------------------------------------------------------------------
def _admin_video(
    db,
    youtube_video_id,
    title="動画",
    created_at=None,
    source=VideoSource.user_submitted,
    is_active=True,
    added_by=None,
    is_shadowing_ready=False,
) -> Video:
    from datetime import datetime

    video = Video(
        youtube_video_id=youtube_video_id,
        title=title,
        thumbnail_url=f"https://example.com/{youtube_video_id}.jpg",
        channel_name="Immersio",
        duration_seconds=180,
        created_at=created_at or datetime(2026, 1, 1, 12, 0, 0),
        source=source,
        is_active=is_active,
        added_by=added_by,
        is_shadowing_ready=is_shadowing_ready,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


def _ids(rows) -> set[str]:
    return {v.youtube_video_id for v in rows}


def test_get_videos_admin_empty_db(service_db):
    rows, total = get_videos_admin(service_db)

    assert rows == []
    assert total == 0


def test_get_videos_admin_no_filters_orders_by_created_at_desc(service_db):
    from datetime import datetime

    _admin_video(service_db, "old", created_at=datetime(2026, 1, 1))
    _admin_video(service_db, "new", created_at=datetime(2026, 1, 3))
    _admin_video(service_db, "mid", created_at=datetime(2026, 1, 2))

    rows, total = get_videos_admin(service_db)

    assert [v.youtube_video_id for v in rows] == ["new", "mid", "old"]
    assert total == 3


def test_get_videos_admin_each_filter_narrows(service_db):
    _admin_video(
        service_db, "curated", title="日本語 Grammar",
        source=VideoSource.curated, is_active=True, added_by=1,
    )
    _admin_video(
        service_db, "user", title="English Lesson",
        source=VideoSource.user_submitted, is_active=True, added_by=2,
    )
    _admin_video(
        service_db, "inactive", title="Old Nihongo",
        source=VideoSource.user_submitted, is_active=False, added_by=1,
    )

    # source
    rows, total = get_videos_admin(service_db, source=VideoSource.curated)
    assert _ids(rows) == {"curated"} and total == 1

    # is_active — admin can see soft-deleted ones
    rows, total = get_videos_admin(service_db, is_active=False)
    assert _ids(rows) == {"inactive"} and total == 1
    rows, total = get_videos_admin(service_db, is_active=True)
    assert _ids(rows) == {"curated", "user"} and total == 2

    # default (is_active=None) returns both active and inactive
    rows, total = get_videos_admin(service_db)
    assert _ids(rows) == {"curated", "user", "inactive"} and total == 3

    # added_by
    rows, total = get_videos_admin(service_db, added_by=1)
    assert _ids(rows) == {"curated", "inactive"} and total == 2

    # search: title, partial + case-insensitive
    rows, total = get_videos_admin(service_db, search="grammar")
    assert _ids(rows) == {"curated"} and total == 1
    rows, total = get_videos_admin(service_db, search="zzz")
    assert rows == [] and total == 0


def test_get_videos_admin_combined_filters_use_and_semantics(service_db):
    _admin_video(
        service_db, "match", title="日本語 Match",
        source=VideoSource.curated, is_active=True,
    )
    # wrong source
    _admin_video(
        service_db, "decoy-source", title="日本語 Match",
        source=VideoSource.user_submitted, is_active=True,
    )
    # wrong active state
    _admin_video(
        service_db, "decoy-inactive", title="日本語 Match",
        source=VideoSource.curated, is_active=False,
    )

    rows, total = get_videos_admin(
        service_db, search="日本語", source=VideoSource.curated, is_active=True
    )

    assert _ids(rows) == {"match"}
    assert total == 1


def test_get_videos_admin_pagination(service_db):
    from datetime import datetime

    # newest = day 5; days 3-5 curated, days 1-2 user_submitted
    for day in range(1, 6):
        _admin_video(
            service_db,
            f"v{day}",
            created_at=datetime(2026, 1, day),
            source=VideoSource.curated if day >= 3 else VideoSource.user_submitted,
        )

    rows, total = get_videos_admin(service_db, page=1, page_size=2)
    assert [v.youtube_video_id for v in rows] == ["v5", "v4"]
    assert total == 5

    rows, total = get_videos_admin(service_db, page=3, page_size=2)
    assert [v.youtube_video_id for v in rows] == ["v1"]
    assert total == 5

    rows, total = get_videos_admin(service_db, page=99, page_size=2)
    assert rows == []
    assert total == 5

    # total reflects the filtered set (3 curated), not the page (2 rows)
    rows, total = get_videos_admin(
        service_db, source=VideoSource.curated, page=1, page_size=2
    )
    assert len(rows) == 2
    assert total == 3


# ---------------------------------------------------------------------------
# get_video_stats  (admin catalog stats)
# ---------------------------------------------------------------------------
def test_get_video_stats_empty_db(service_db):
    stats = get_video_stats(service_db)

    assert stats["total"] == 0
    assert stats["active"] == 0
    assert stats["inactive"] == 0
    assert stats["by_source"] == {"curated": 0, "user_submitted": 0}
    assert stats["shadowing_ready"] == 0
    assert stats["shadowing_not_ready"] == 0
    assert stats["added_last_7_days"] == 0
    assert stats["added_last_30_days"] == 0


def test_get_video_stats_counts_and_by_source(service_db):
    _admin_video(service_db, "c1", source=VideoSource.curated, is_active=True)
    _admin_video(service_db, "c2", source=VideoSource.curated, is_active=False)
    _admin_video(service_db, "u1", source=VideoSource.user_submitted, is_active=True)
    _admin_video(service_db, "u2", source=VideoSource.user_submitted, is_active=True)

    stats = get_video_stats(service_db)

    assert stats["total"] == 4
    assert stats["active"] == 3
    assert stats["inactive"] == 1
    # by_source counts all videos regardless of is_active
    assert stats["by_source"] == {"curated": 2, "user_submitted": 2}


def test_get_video_stats_shadowing_readiness(service_db):
    _admin_video(service_db, "r1", is_shadowing_ready=True)
    _admin_video(service_db, "r2", is_shadowing_ready=True)
    _admin_video(service_db, "nr1", is_shadowing_ready=False)

    stats = get_video_stats(service_db)

    assert stats["shadowing_ready"] == 2
    assert stats["shadowing_not_ready"] == 1  # total - ready


def test_get_video_stats_time_windows(service_db):
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    _admin_video(service_db, "d3", created_at=now - timedelta(days=3))
    _admin_video(service_db, "d10", created_at=now - timedelta(days=10))
    _admin_video(service_db, "d40", created_at=now - timedelta(days=40))

    stats = get_video_stats(service_db)

    assert stats["added_last_7_days"] == 1     # only d3
    assert stats["added_last_30_days"] == 2    # d3 + d10


# ---------------------------------------------------------------------------
# soft_delete_video
# ---------------------------------------------------------------------------
def test_soft_delete_video_returns_none_when_missing(service_db):
    assert soft_delete_video(999, service_db) is None


def test_soft_delete_video_deactivates_active_video(service_db):
    video = _admin_video(service_db, "active", is_active=True)

    result = soft_delete_video(video.id, service_db)

    assert result is video
    assert result.is_active is False
    # persisted, not just in-memory
    assert get_video_by_id(video.id, service_db).is_active is False


def test_soft_delete_video_is_idempotent_for_inactive_video(service_db):
    video = _admin_video(service_db, "inactive", is_active=False)

    result = soft_delete_video(video.id, service_db)

    assert result is video
    assert result.is_active is False
