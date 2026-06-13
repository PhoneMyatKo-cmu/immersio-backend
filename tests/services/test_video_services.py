"""
Tests for services/video/video_services.py  (Video Submission — Service / DB)

Planned scope (docs/test_plan.md §5.2, DBS-01..04):
  save_video, check_video_exists, get_video_by_id,
  get_video_by_youtube_video_id, change_shadowing_status

Out of scope here (left for the feed/difficulty owner):
  get_videos, get_total_video_count, save_vocabulary_profile,
  save_difficulty_level (and the commented-out difficulty/feed helpers).

[integration] Uses the real test database via the db_session fixture (models use
PostgreSQL JSONB, so a Postgres test DB is required; the fixture skips if it is
unreachable). The module skips if its import deps (isodate, etc.) are missing.
"""

import pytest

try:
    from sqlalchemy import select
    from models.video import Video
    from services.video.video_services import (
        save_video,
        check_video_exists,
        get_video_by_id,
        get_video_by_youtube_video_id,
        change_shadowing_status,
    )
except Exception as exc:  # isodate / import-chain deps missing
    pytest.skip(f"video_services unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.integration, pytest.mark.video_submission]


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
