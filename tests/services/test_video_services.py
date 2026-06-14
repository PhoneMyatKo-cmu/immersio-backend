"""
Tests for services/video/video_services.py
Covers: docs/test_plan.md §5.2 (DBS-01..04):
  save_video, check_video_exists, get_video_by_id / _by_youtube_video_id,
  change_shadowing_status.
[integration — uses the db_session fixture]
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.video import Video
from services.video.video_services import get_total_video_count, get_videos

pytestmark = [pytest.mark.integration, pytest.mark.video_submission]


@pytest.fixture()
def service_db():
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


@pytest.mark.skip(reason="TODO DBS-01: save_video persists row + parses ISO duration to seconds")
def test_dbs_01_save_video(db_session, fx_meta_ja):
    from services.video.video_services import save_video
    ...


@pytest.mark.skip(reason="TODO DBS-02/03/04 (exists lookup, get-by-id, shadowing status)")
def test_dbs_video_queries(db_session):
    ...
