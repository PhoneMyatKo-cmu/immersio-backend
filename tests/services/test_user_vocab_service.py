"""
Tests for services/user_vocab/user_vocab_service.py  (Word Look Up)

Covers docs/test_plan.md §7.3:
  VDS-02  save_vocab_to_library inserts a row with default SRS values
  VDS-03  duplicate (user, vocab) violates uq_user_vocab -> raises
  VDS-04  check_duplicate_vocab is scoped per user

[integration] Real test DB via db_session. UserSavedVocabulary has FKs to users,
vocabulary, videos and captions, so those rows are seeded first. VDS-03 needs a
constraint-enforcing database (Postgres).
"""

import pytest

try:
    from models.user import User
    from models.video import Video
    from models.vocab import EstimatedLevel, Vocabulary
    from models.processed_caption import Caption
    from schemas.vocab_context import UserVocabSave
    from services.user_vocab.user_vocab_service import (
        save_vocab_to_library,
        check_duplicate_vocab,
    )
except Exception as exc:
    pytest.skip(f"user_vocab_service unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.integration, pytest.mark.word_lookup]


def _seed(db, email="a@example.com"):
    user = User(first_name="A", last_name="B", email=email, password_hash="x")
    vocab = Vocabulary(japanese_form="食べる", reading="taberu",
                       meanings=[{"pos": "verb", "meanings": ["to eat"]}],
                       estimated_level=EstimatedLevel.N5)
    video = Video(youtube_video_id="vid12345678", title="T", thumbnail_url="u",
                  channel_name="C", duration_seconds=10)
    db.add_all([user, vocab, video])
    db.commit()
    caption = Caption(video_id=video.id, caption_index=0, text="毎日ご飯を食べる。",
                      tokens=[], start_time=0.0, end_time=1.0, duration=1.0)
    db.add(caption)
    db.commit()
    db.refresh(user); db.refresh(vocab); db.refresh(video); db.refresh(caption)
    return user, vocab, video, caption


def _save(vocab, video, caption, timestamp=1.0):
    return UserVocabSave(vocab_id=vocab.id, video_id=video.id,
                         caption_id=caption.id, timestamp=timestamp)


# --- VDS-02 -----------------------------------------------------------------
def test_save_vocab_to_library_inserts_with_default_srs(db_session):
    user, vocab, video, caption = _seed(db_session)
    save_vocab_to_library(_save(vocab, video, caption, timestamp=12.5), user.id, db_session)

    row = check_duplicate_vocab(user.id, vocab.id, db_session)
    assert row is not None
    assert row.ease_factor == 2.5
    assert row.interval_days == 0


# --- VDS-03 -----------------------------------------------------------------
def test_duplicate_save_violates_unique_constraint(db_session):
    user, vocab, video, caption = _seed(db_session)
    save_vocab_to_library(_save(vocab, video, caption), user.id, db_session)
    with pytest.raises(Exception):  # IntegrityError from uq_user_vocab
        save_vocab_to_library(_save(vocab, video, caption), user.id, db_session)


# --- VDS-04 -----------------------------------------------------------------
def test_check_duplicate_vocab_scoped_per_user(db_session):
    user, vocab, video, caption = _seed(db_session)
    save_vocab_to_library(_save(vocab, video, caption), user.id, db_session)

    assert check_duplicate_vocab(user.id, vocab.id, db_session) is not None

    other = User(first_name="C", last_name="D", email="c@example.com", password_hash="x")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    assert check_duplicate_vocab(other.id, vocab.id, db_session) is None      # other user
    assert check_duplicate_vocab(user.id, vocab.id + 999, db_session) is None  # other vocab
