"""Functional evaluation scenarios for the recommendation feature.

Unlike the unit / integration / system tests (which verify the math, the service
wiring, and the HTTP contract), these scenarios evaluate *ranking quality*: does
the recommender behave the way the design intends for representative learner
situations? Each scenario builds a learner + a small catalog and asserts the
expected ordering / difficulty outcome, mapped to a design goal.

Serves as the functional-evaluation evidence for the recommendation feature.
Requires a Postgres test DB (db_session skips otherwise).

Assumptions:
- Learners are made "established" (>= 60 known words) so the feed is in normal
  (non-cold-start) mode and difficulty sections are populated.
- `too_advanced` videos are excluded from the surfaced sections.
- The SRS study-deck query is fixed (so EVAL-05 is meaningful).
"""

import uuid
from datetime import datetime, timedelta

import pytest

from models.learning_session import LearningSession  # noqa: F401 (registers table)
from models.user import EstimatedLevel, User, UserRole
from models.user_vocab_library import SRSState, UserSavedVocabulary
from models.user_vocab_profile import UserVocabularyExposure, VocabStatus
from models.video import Video, VideoSource
from models.video_vocab_profile import VideoVocabulary
from models.vocab import EstimatedLevel as VocabLevel
from models.vocab import Vocabulary
from services.recommendation.recommendation_service import get_recommended_videos

pytestmark = [pytest.mark.integration, pytest.mark.recommendation]


# --- seed helpers ---


def _user(db, level=EstimatedLevel.beginner):
    u = User(
        first_name="T",
        last_name="U",
        email=f"{uuid.uuid4()}@e.com",
        password_hash="x",
        estimated_level=level,
        role=UserRole.LEARNER,
    )
    db.add(u)
    db.flush()
    return u


def _video(db, ready=True, active=True):
    v = Video(
        youtube_video_id=uuid.uuid4().hex[:11],
        title="v",
        thumbnail_url="http://x",
        channel_name="c",
        duration_seconds=300,
        is_shadowing_ready=ready,
        is_active=active,
        source=VideoSource.curated,
    )
    db.add(v)
    db.flush()
    return v


def _vocab(db, level=VocabLevel.N5):
    w = Vocabulary(
        japanese_form=uuid.uuid4().hex[:10],
        reading="r",
        meanings=[],
        lemma="l",
        estimated_level=level,
    )
    db.add(w)
    db.flush()
    return w


def _add_word(db, video, vocab, freq=1):
    db.add(VideoVocabulary(video_id=video.id, vocab_id=vocab.id, frequency=freq))
    db.flush()


def _know(db, user, vocab):
    db.add(
        UserVocabularyExposure(
            user_id=user.id,
            vocab_id=vocab.id,
            seen_count=50,
            status=VocabStatus.know,
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )
    )
    db.flush()


def _saved_due(db, user, vocab, video, lapses=0):
    # studying + past review date = due; interval 0 -> known-weight 0 (no coverage effect)
    db.add(
        UserSavedVocabulary(
            user_id=user.id,
            vocab_id=vocab.id,
            video_id=video.id,
            srs_state=SRSState.studying,
            interval_days=0,
            next_review_date=datetime.utcnow() - timedelta(days=2),
            lapses=lapses,
        )
    )
    db.flush()


def _watch(db, user, video, when):
    db.add(
        LearningSession(
            id=uuid.uuid4().hex,
            user_id=user.id,
            video_id=video.id,
            start_time=when - timedelta(minutes=5),
            end_time=when,
        )
    )
    db.flush()


def _make_established(db, user, n=60):
    """Give the learner enough known words to leave cold-start mode."""
    for _ in range(n):
        _know(db, user, _vocab(db))


def _find(feed, video_id):
    for section in feed.sections:
        for item in section.items:
            if item.id == video_id:
                return item
    return None


def _ranked_ids(feed):
    top = next((s for s in feed.sections if s.key == "top_picks"), None)
    return [it.id for it in top.items] if top else []


# --- EVAL-01: level-appropriateness ---


def test_eval01_beginner_prefers_level_appropriate_over_too_hard(db_session):
    db = db_session
    user = _user(db, EstimatedLevel.beginner)
    _make_established(db, user)

    easy = _video(db)
    base = [_vocab(db, VocabLevel.N5) for _ in range(9)]
    for w in base:
        _add_word(db, easy, w)
        _know(db, user, w)
    _add_word(db, easy, _vocab(db, VocabLevel.N5))  # 9 known + 1 new -> coverage 0.9

    hard = _video(db)
    for _ in range(5):
        _add_word(db, hard, _vocab(db, VocabLevel.N1))  # all unknown N1
    db.commit()

    feed = get_recommended_videos(user, db)
    # easy_item = _find(feed, easy.id)

    assert easy.id == feed.sections[0].items[0].id
    assert hard.id == feed.sections[0].items[1].id


# --- EVAL-02: comprehensible-input band (too-easy demoted) ---


def test_eval02_sweet_spot_beats_too_easy(db_session):
    db = db_session
    user = _user(db, EstimatedLevel.beginner)
    _make_established(db, user)
    base = [_vocab(db, VocabLevel.N5) for _ in range(9)]
    for w in base:
        _know(db, user, w)

    sweet, easy = _video(db), _video(db)
    for w in base:
        _add_word(db, sweet, w)
        _add_word(db, easy, w)
    _add_word(db, sweet, _vocab(db, VocabLevel.N4))  # sweet: 9 known + 1 new -> 0.90
    tenth = _vocab(db, VocabLevel.N5)
    _know(db, user, tenth)
    _add_word(db, easy, tenth)  # easy: 10 known -> 1.00
    db.commit()

    ids = _ranked_ids(get_recommended_videos(user, db))
    assert ids.index(sweet.id) < ids.index(easy.id)


# --- EVAL-03: comprehensible-input band (too-hard excluded) ---


def test_eval03_sweet_spot_beats_too_hard(db_session):
    db = db_session
    user = _user(db, EstimatedLevel.beginner)
    _make_established(db, user)
    base = [_vocab(db, VocabLevel.N5) for _ in range(9)]
    for w in base:
        _know(db, user, w)

    sweet = _video(db)
    for w in base:
        _add_word(db, sweet, w)
    _add_word(db, sweet, _vocab(db, VocabLevel.N4))  # 0.90

    hard = _video(db)
    hk = [_vocab(db, VocabLevel.N5) for _ in range(4)]
    for w in hk:
        _add_word(db, hard, w)
        _know(db, user, w)
    for _ in range(6):
        _add_word(db, hard, _vocab(db, VocabLevel.N2))  # 4 / 10 -> 0.40
    db.commit()

    feed = get_recommended_videos(user, db)

    ids = _ranked_ids(get_recommended_videos(user, db))
    assert ids.index(sweet.id) < ids.index(hard.id)


# --- EVAL-04: learning value differentiates equal-coverage videos ---


def test_eval04_learning_value_differentiates_equal_coverage(db_session):
    db = db_session
    user = _user(db, EstimatedLevel.beginner)
    _make_established(db, user)
    base = [_vocab(db, VocabLevel.N5) for _ in range(9)]
    for w in base:
        _know(db, user, w)

    good, junk = _video(db), _video(db)
    for w in base:
        _add_word(db, good, w)
        _add_word(db, junk, w)
    _add_word(db, good, _vocab(db, VocabLevel.N4))  # new word at level
    _add_word(db, junk, _vocab(db, VocabLevel.N1))  # new word far above level
    db.commit()

    ids = _ranked_ids(get_recommended_videos(user, db))
    assert ids.index(good.id) < ids.index(junk.id)


# --- EVAL-05: due study word lifts a video (SRS) ---


def test_eval05_due_review_word_lifts_video(db_session):
    db = db_session
    user = _user(db, EstimatedLevel.beginner)
    _make_established(db, user)
    base = [_vocab(db, VocabLevel.N5) for _ in range(9)]
    for w in base:
        _know(db, user, w)

    with_due, without = _video(db), _video(db)
    for w in base:
        _add_word(db, with_due, w)
        _add_word(db, without, w)
    due_word = _vocab(db, VocabLevel.N4)
    _saved_due(db, user, due_word, with_due)
    _add_word(db, with_due, due_word)  # A: base + due study word (weight 0, so 0.90)
    _add_word(db, without, _vocab(db, VocabLevel.N4))  # B: base + plain new word (0.90)
    db.commit()

    ids = _ranked_ids(get_recommended_videos(user, db))
    assert ids.index(with_due.id) < ids.index(without.id)


# --- EVAL-06: recently watched is demoted (recency) ---


def test_eval06_recently_watched_is_demoted(db_session):
    """When user has recently watched the video , that video is not in recommended fedd"""
    db = db_session
    user = _user(db, EstimatedLevel.beginner)
    _make_established(db, user)
    base = [_vocab(db, VocabLevel.N5) for _ in range(9)]
    for w in base:
        _know(db, user, w)

    watched, fresh = _video(db), _video(db)
    for w in base:
        _add_word(db, watched, w)
        _add_word(db, fresh, w)
    _add_word(db, watched, _vocab(db, VocabLevel.N4))
    _add_word(db, fresh, _vocab(db, VocabLevel.N4))
    _watch(db, user, watched, datetime.utcnow() - timedelta(hours=1))
    db.commit()

    feed = get_recommended_videos(user, db)
    assert _find(feed, watched.id) is None
    assert _find(feed, fresh.id) is not None


# --- EVAL-07: personalization by knowledge ---


def test_eval07_same_video_personalized_by_knowledge(db_session):
    db = db_session
    knower = _user(db, EstimatedLevel.beginner)
    stranger = _user(db, EstimatedLevel.beginner)
    _make_established(db, knower)
    _make_established(db, stranger)

    video = _video(db)
    words = [_vocab(db, VocabLevel.N3) for _ in range(5)]
    for w in words:
        _add_word(db, video, w)
        _know(db, knower, w)  # knower knows all; stranger knows none
    db.commit()

    knower_item = _find(get_recommended_videos(knower, db), video.id)
    stranger_item = _find(get_recommended_videos(stranger, db), video.id)
    assert knower_item is not None and knower_item.difficulty == "comfortable"
    assert (
        stranger_item is not None and stranger_item.difficulty == "too_advanced"
    )  # coverage 0 -> too_advanced
