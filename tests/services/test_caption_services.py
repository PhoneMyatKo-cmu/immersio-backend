"""
Tests for services/caption/caption_services.py  (Video Submission + Word Look Up)

Covers docs/test_plan.md:
  §5.2 DBS-05  save_tokenized_captions                   [Video Submission]
  §5.2 DBS-06  get_captions_by_video_id                  [Video Submission]
  §5.2 DBS-07  save_tokenized_captions rollback is atomic [Video Submission]
  §7.2 GCT-01..04 get_caption_translation                [Word Look Up]

[integration] Real test DB via db_session; google_translate mocked at the service
path. Caption.video_id is a FK to videos.id, so a Video is seeded first. Module
skips if its import chain (Google-Translate client) is unavailable.
"""

from unittest.mock import MagicMock

import pytest

try:
    from sqlalchemy import select
    from models.video import Video
    from models.processed_caption import Caption
    from services.caption import caption_services as svc
    from services.caption.caption_services import (
        save_tokenized_captions,
        get_captions_by_video_id,
        get_caption_translation,
    )
except Exception as exc:
    pytest.skip(f"caption_services unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.integration]

PROCESSED = [
    {"index": 0, "text": "猫が好き", "start": 0.0, "duration": 2.0,
     "tokens": [{"surface": "猫", "base_form": "猫", "pos": "名詞",
                 "pos_detail": "普通名詞", "is_content_word": True}]},
    {"index": 1, "text": "また猫", "start": 2.0, "duration": 1.5,
     "tokens": [{"surface": "また", "base_form": "また", "pos": "副詞",
                 "pos_detail": "*", "is_content_word": True}]},
]


def _make_video(db, youtube_video_id="vid12345678"):
    v = Video(youtube_video_id=youtube_video_id, title="T", thumbnail_url="u",
              channel_name="C", duration_seconds=180)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _make_caption(db, video_id, translation=None):
    c = Caption(video_id=video_id, caption_index=0, text="毎日ご飯を食べる。",
                tokens=[], start_time=0.0, end_time=1.0, duration=1.0,
                translation=translation)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# --- DBS-05 -----------------------------------------------------------------
@pytest.mark.video_submission
def test_save_tokenized_captions_persists_and_computes_end_time(db_session):
    video = _make_video(db_session)
    count = save_tokenized_captions(PROCESSED, video.id, db_session)
    assert count == 2

    rows = db_session.scalars(
        select(Caption).where(Caption.video_id == video.id)
    ).all()
    assert len(rows) == 2
    first = next(r for r in rows if r.caption_index == 0)
    assert first.text == "猫が好き"
    assert first.end_time == 2.0  # start(0.0) + duration(2.0)


# --- DBS-06 -----------------------------------------------------------------
@pytest.mark.video_submission
def test_get_captions_by_video_id_returns_rows(db_session):
    video = _make_video(db_session)
    save_tokenized_captions(PROCESSED, video.id, db_session)
    rows = get_captions_by_video_id(video.id, db_session)
    assert {r.caption_index for r in rows} == {0, 1}


# --- DBS-07 -----------------------------------------------------------------
@pytest.mark.video_submission
def test_save_tokenized_captions_rolls_back_atomically_on_bad_row(db_session):
    # A batch where the second row is malformed (no "index" key). The good
    # first row must NOT survive: the whole batch is rolled back as a unit.
    video = _make_video(db_session)
    bad_batch = [
        {"index": 0, "text": "猫が好き", "start": 0.0, "duration": 2.0, "tokens": []},
        {"text": "また猫", "start": 2.0, "duration": 1.5, "tokens": []},  # missing "index"
    ]

    with pytest.raises(KeyError):
        save_tokenized_captions(bad_batch, video.id, db_session)

    rows = db_session.scalars(
        select(Caption).where(Caption.video_id == video.id)
    ).all()
    assert rows == []  # good row from the same batch was rolled back too


# --- GCT-01 -----------------------------------------------------------------
@pytest.mark.word_lookup
def test_caption_translation_cache_hit(monkeypatch, db_session):
    video = _make_video(db_session)
    caption = _make_caption(db_session, video.id, translation="I eat rice every day.")
    translate = MagicMock()
    monkeypatch.setattr(svc, "google_translate", translate)

    result = get_caption_translation({"id": caption.id, "text": caption.text}, db_session)
    assert result == "I eat rice every day."
    translate.assert_not_called()


# --- GCT-02 -----------------------------------------------------------------
@pytest.mark.word_lookup
def test_caption_translation_cache_miss_translates_and_caches(monkeypatch, db_session):
    video = _make_video(db_session)
    caption = _make_caption(db_session, video.id, translation=None)
    monkeypatch.setattr(svc, "google_translate", MagicMock(return_value=["I eat rice every day."]))

    result = get_caption_translation({"id": caption.id, "text": caption.text}, db_session)
    assert result == "I eat rice every day."
    refreshed = db_session.scalars(select(Caption).where(Caption.id == caption.id)).first()
    assert refreshed.translation == "I eat rice every day."


# --- GCT-03 -----------------------------------------------------------------
@pytest.mark.word_lookup
def test_caption_translation_unavailable_returns_fallback(monkeypatch, db_session):
    video = _make_video(db_session)
    caption = _make_caption(db_session, video.id, translation=None)
    monkeypatch.setattr(svc, "google_translate", MagicMock(side_effect=Exception("translate down")))

    result = get_caption_translation({"id": caption.id, "text": caption.text}, db_session)
    assert result == "Translation service currently unavailable!"


# --- GCT-04 -----------------------------------------------------------------
@pytest.mark.word_lookup
def test_caption_translation_malformed_dict_raises_keyerror(db_session):
    with pytest.raises(KeyError):
        get_caption_translation({"surface": "食べる"}, db_session)  # missing id/text
