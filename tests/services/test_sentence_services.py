"""
Tests for services/sentence/sentence_services.py  (Video Submission — Service / DB)

Covers docs/test_plan.md §5.2:
  DBS-07  save_sentence            -> persists rows, returns {"number_of_sentences": n}
  DBS-08  get_sentence_by_video_id -> returns the video's sentences

[integration] Real test DB via db_session. ShadowingSentence.video_id is a FK to
videos.id, so each test seeds a Video first. Importing the service pulls in the
Google-Translate client, so the module skips if that chain is unavailable.
"""

import pytest
from sqlalchemy.exc import IntegrityError

try:
    from sqlalchemy import select

    from models.sentence import ShadowingSentence
    from models.video import Video
    from services.sentence.sentence_services import (
        get_sentence_by_video_id,
        save_sentence,
    )
except Exception as exc:
    pytest.skip(f"sentence_services unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.integration, pytest.mark.video_submission]

SENTENCES = [
    {
        "sentence_index": 0,
        "text": "おはよう",
        "start": 0.0,
        "end": 1.2,
        "duration": 1.2,
    },
    {
        "sentence_index": 1,
        "text": "元気ですか",
        "start": 1.2,
        "end": 3.0,
        "duration": 1.8,
    },
]


def _make_video(db, youtube_video_id="vid12345678"):
    video = Video(
        youtube_video_id=youtube_video_id,
        title="日本語レッスン",
        thumbnail_url="https://i.ytimg.com/vi/x/hqdefault.jpg",
        channel_name="Nihongo Channel",
        duration_seconds=180,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


# --- DBS-07 -----------------------------------------------------------------
def test_save_sentence_persists_rows_and_returns_count(db_session):
    video = _make_video(db_session)
    result = save_sentence(SENTENCES, video.id, db_session)
    assert result == {"number_of_sentences": 2}

    rows = db_session.scalars(
        select(ShadowingSentence).where(ShadowingSentence.video_id == video.id)
    ).all()
    assert len(rows) == 2
    first = next(r for r in rows if r.sentence_index == 0)
    assert first.text == "おはよう"
    assert first.start_time == 0.0
    assert first.end_time == 1.2
    assert first.duration == 1.2


# def test_save_sentence_with_invalid_video_id(db_session):
#     video = _make_video(db_session)
#     result = save_sentence(SENTENCES, 2, db_session)
#     with pytest.raises(IntegrityError):
#         db_session.commit()


# --- DBS-08 -----------------------------------------------------------------
def test_get_sentence_by_video_id_returns_rows(db_session):
    video = _make_video(db_session)
    save_sentence(SENTENCES, video.id, db_session)

    rows = get_sentence_by_video_id(video.id, db_session)
    assert {r.sentence_index for r in rows} == {0, 1}

    other = _make_video(db_session, youtube_video_id="other1234567")
    assert list(get_sentence_by_video_id(other.id, db_session)) == []

    invalid_video_id = 2
    assert list(get_sentence_by_video_id(invalid_video_id, db_session)) == []
