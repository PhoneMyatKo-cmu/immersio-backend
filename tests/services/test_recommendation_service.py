import uuid
from datetime import datetime, timedelta

import pytest

from models.learning_session import LearningSession  # noqa: F401 (registers table)
from models.user import EstimatedLevel as UserLevel
from models.user import User, UserRole
from models.user_vocab_library import SRSState, UserSavedVocabulary
from models.user_vocab_profile import UserVocabularyExposure, VocabStatus
from models.video import Video, VideoSource
from models.video_vocab_profile import VideoVocabulary
from models.vocab import EstimatedLevel as VocabLevel
from models.vocab import Vocabulary
from services.recommendation.recommendation_service import (
    get_recommended_videos,
    get_vocab_weights,
    score_video,
)

pytestmark = [pytest.mark.integration, pytest.mark.recommendation]


# --- seed helpers ---


def _user(db, level=UserLevel.beginner):
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


def _video(db, title="v", ready=True, active=True):
    v = Video(
        youtube_video_id=uuid.uuid4().hex[:11],
        title=title,
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


def _vocab(db, form, level=VocabLevel.N5):
    w = Vocabulary(
        japanese_form=form, reading=form, meanings=[], lemma=form, estimated_level=level
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
    """Give the user enough known vocab to exceed any cold-start threshold."""
    for _ in range(n):
        _know(db, user, _vocab(db, f"filler_{uuid.uuid4().hex[:8]}"))


def _all_ids(feed):
    return {it.id for s in feed.sections for it in s.items}


# --- eligibility ---


def test_get_recommended_videos_only_active_and_shadowing_ready(db_session):
    user = _user(db_session)
    ready = _video(db_session, ready=True, active=True)
    not_ready = _video(db_session, ready=False, active=True)
    inactive = _video(db_session, ready=True, active=False)
    w = _vocab(db_session, "あ")
    for v in (ready, not_ready, inactive):
        _add_word(db_session, v, w, freq=5)
    db_session.commit()

    ids = _all_ids(get_recommended_videos(user, db_session))
    assert ready.id in ids
    assert not_ready.id not in ids
    assert inactive.id not in ids


# --- recency hard filter ---


def test_get_recommended_videos_excludes_recently_watched(db_session):
    user = _user(db_session)
    watched, fresh = _video(db_session), _video(db_session)
    w = _vocab(db_session, "い")
    _add_word(db_session, watched, w, 5)
    _add_word(db_session, fresh, w, 5)
    _watch(db_session, user, watched, datetime.utcnow() - timedelta(hours=1))  # < 24h
    db_session.commit()

    ids = _all_ids(get_recommended_videos(user, db_session))
    assert watched.id not in ids
    assert fresh.id in ids


def test_get_recommended_videos_keeps_old_watch(db_session):
    user = _user(db_session)
    v = _video(db_session)
    _add_word(db_session, v, _vocab(db_session, "う"), 5)
    _watch(db_session, user, v, datetime.utcnow() - timedelta(days=10))
    db_session.commit()

    assert v.id in _all_ids(get_recommended_videos(user, db_session))


# --- cold start flag ---


def test_get_recommended_videos_cold_start_true_when_empty_profile(db_session):
    user = _user(db_session)
    _add_word(db_session, _video(db_session), _vocab(db_session, "ね"), 5)
    db_session.commit()

    assert get_recommended_videos(user, db_session).is_cold_start is True


def test_get_recommended_videos_cold_start_false_with_rich_profile(db_session):
    user = _user(db_session)
    _make_established(db_session, user)
    _add_word(db_session, _video(db_session), _vocab(db_session, "の"), 5)
    db_session.commit()

    assert get_recommended_videos(user, db_session).is_cold_start is False


# --- difficulty bucketing ---


def test_get_recommended_videos_fully_known_video_is_comfortable(db_session):
    user = _user(db_session)
    _make_established(db_session, user)  # stay non-cold
    v = _video(db_session)
    for i in range(5):
        w = _vocab(db_session, f"e{i}")
        _add_word(db_session, v, w, 2)
        _know(db_session, user, w)  # user knows every word
    db_session.commit()

    feed = get_recommended_videos(user, db_session)
    item = next(it for s in feed.sections for it in s.items if it.id == v.id)
    assert item.difficulty == "comfortable"
    assert item.understand_percent == 100


# --- ranking ---


def test_get_recommended_videos_sweet_spot_outranks_too_easy(db_session):
    user = _user(db_session)
    _make_established(db_session, user)
    sweet, too_easy = _video(db_session), _video(db_session)
    shared = [_vocab(db_session, f"s{i}") for i in range(10)]
    for w in shared:
        _know(db_session, user, w)
    new_word = _vocab(
        db_session, "brandnew", level=VocabLevel.N4
    )  # at level for beginner
    for w in shared[:9]:
        _add_word(db_session, sweet, w, 1)
    _add_word(db_session, sweet, new_word, 1)  # sweet: 9/10 known -> 0.90
    for w in shared:
        _add_word(db_session, too_easy, w, 1)  # too_easy: 10/10 known -> 1.00
    db_session.commit()

    feed = get_recommended_videos(user, db_session)
    top = next(s for s in feed.sections if s.key == "top_picks")
    assert top.items[0].id == sweet.id


# --- empty ---


def test_get_recommended_videos_empty_feed_when_no_eligible(db_session):
    user = _user(db_session)
    db_session.commit()
    assert get_recommended_videos(user, db_session).sections[0].items == []


# =====================================================================
# get_vocab_weights
# =====================================================================


def _seen(db, user, vocab, count):
    db.add(
        UserVocabularyExposure(
            user_id=user.id,
            vocab_id=vocab.id,
            seen_count=count,
            status=VocabStatus.seen,
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )
    )
    db.flush()


def _saved(db, user, vocab, video, srs_state, interval_days=0):
    db.add(
        UserSavedVocabulary(
            user_id=user.id,
            vocab_id=vocab.id,
            video_id=video.id,
            srs_state=srs_state,
            interval_days=interval_days,
        )
    )
    db.flush()


def test_get_vocab_weights_known_exposure_is_full_weight(db_session):
    user = _user(db_session)
    w = _vocab(db_session, "か")
    _know(db_session, user, w)
    db_session.commit()

    assert get_vocab_weights(user.id, db_session) == {w.id: 1.0}


def test_get_vocab_weights_returns_int_keys(db_session):
    user = _user(db_session)
    w = _vocab(db_session, "き")
    _know(db_session, user, w)
    db_session.commit()

    weights = get_vocab_weights(user.id, db_session)
    assert all(isinstance(k, int) for k in weights)


def test_get_vocab_weights_empty_when_no_data(db_session):
    user = _user(db_session)
    db_session.commit()

    assert get_vocab_weights(user.id, db_session) == {}


def test_get_vocab_weights_seen_gives_partial_weight(db_session):
    user = _user(db_session)
    w = _vocab(db_session, "く")
    _seen(db_session, user, w, count=6)  # 0.3 + 0.05 * 6 = 0.6
    db_session.commit()

    assert get_vocab_weights(user.id, db_session)[w.id] == pytest.approx(0.6)


def test_get_vocab_weights_takes_max_across_sources(db_session):
    user = _user(db_session)
    video = _video(db_session)
    w = _vocab(db_session, "け")
    _seen(db_session, user, w, count=2)  # exposure -> 0.4
    _saved(db_session, user, w, video, SRSState.studying, interval_days=3)  # -> ~0.14
    db_session.commit()

    assert get_vocab_weights(user.id, db_session)[w.id] == pytest.approx(0.4)


def test_get_vocab_weights_drops_zero_weight(db_session):
    user = _user(db_session)
    video = _video(db_session)
    w = _vocab(db_session, "こ")
    _saved(db_session, user, w, video, SRSState.new)  # not studied -> weight 0
    db_session.commit()

    assert get_vocab_weights(user.id, db_session) == {}


# =====================================================================
# score_video
# =====================================================================


def test_score_video_known_word_registers_in_coverage(db_session):
    v = _video(db_session)
    w = _vocab(db_session, "さ")
    _add_word(db_session, v, w, freq=5)
    db_session.commit()

    result = score_video(
        video_id=v.id,
        known_map={w.id: 1.0},
        studying_rows=[],
        last_watched=None,
        user_level=UserLevel.beginner,
        now=datetime.utcnow(),
        db=db_session,
    )
    assert result["coverage"] == 1.0


def test_score_video_unknown_word_has_zero_coverage(db_session):
    v = _video(db_session)
    _add_word(db_session, v, _vocab(db_session, "し"), freq=5)
    db_session.commit()

    result = score_video(
        video_id=v.id,
        known_map={},
        studying_rows=[],
        last_watched=None,
        user_level=UserLevel.beginner,
        now=datetime.utcnow(),
        db=db_session,
    )
    assert result["coverage"] == 0.0


def test_score_video_returns_all_components(db_session):
    v = _video(db_session)
    _add_word(db_session, v, _vocab(db_session, "す"), freq=5)
    db_session.commit()

    result = score_video(
        video_id=v.id,
        known_map={},
        studying_rows=[],
        last_watched=None,
        user_level=UserLevel.beginner,
        now=datetime.utcnow(),
        db=db_session,
    )
    assert set(result) >= {
        "score",
        "coverage",
        "comprehension_fit",
        "learning_value",
        "srs_bonus",
        "recency_penalty",
        "new_word_count",
        "review_word_count",
    }


def test_score_video_counts_only_not_known_words_as_new(db_session):
    v = _video(db_session)
    known_w = _vocab(db_session, "せ")
    new_w = _vocab(db_session, "そ", level=VocabLevel.N4)
    _add_word(db_session, v, known_w, freq=3)
    _add_word(db_session, v, new_w, freq=3)
    db_session.commit()

    result = score_video(
        video_id=v.id,
        known_map={known_w.id: 1.0},
        studying_rows=[],
        last_watched=None,
        user_level=UserLevel.beginner,
        now=datetime.utcnow(),
        db=db_session,
    )
    assert result["new_word_count"] == 1


def test_score_video_recent_watch_lowers_score(db_session):
    now = datetime.utcnow()
    v = _video(db_session)
    _add_word(db_session, v, _vocab(db_session, "た"), freq=5)
    db_session.commit()

    fresh = score_video(
        video_id=v.id,
        known_map={},
        studying_rows=[],
        last_watched=None,
        user_level=UserLevel.beginner,
        now=now,
        db=db_session,
    )
    watched = score_video(
        video_id=v.id,
        known_map={},
        studying_rows=[],
        last_watched=now,
        user_level=UserLevel.beginner,
        now=now,
        db=db_session,
    )
    assert fresh["recency_penalty"] == 0.0
    assert watched["recency_penalty"] > 0.0
    assert watched["score"] < fresh["score"]
