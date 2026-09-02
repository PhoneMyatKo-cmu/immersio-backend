"""System tests for the recommendation feature — end-to-end through the HTTP
endpoint (GET /video/recommendation), full stack: auth -> router -> service -> DB.

Black-box level: seed a realistic world, hit the endpoint with a TestClient, and
assert on the HTTP response (status, contract, which videos come back). The
scoring math is covered by unit tests, the service wiring by integration tests;
here we verify the feature works as a whole through its real interface.

Needs a real Postgres test DB (db_session skips otherwise). Importing `main`
instantiates external SDK clients at import time, so it is deferred into the
fixtures and requires dummy credentials in the test env.
"""

import uuid
from datetime import datetime, timedelta

import pytest

from models.learning_session import LearningSession  # noqa: F401 (registers table)
from models.user import EstimatedLevel, User, UserRole
from models.user_vocab_profile import UserVocabularyExposure, VocabStatus
from models.video import Video, VideoSource
from models.vocab import EstimatedLevel as VocabLevel
from models.vocab import Vocabulary
from models.video_vocab_profile import VideoVocabulary

pytestmark = [pytest.mark.integration, pytest.mark.recommendation]


# --- seed helpers (self-contained; move to conftest if shared more widely) ---


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


def _item_ids(body):
    return {it["id"] for s in body["sections"] for it in s["items"]}


# --- fixtures ---


@pytest.fixture()
def rec_client(db_session):
    """TestClient wired to the test DB, authenticated as a seeded beginner user.

    Yields (client, user, db_session). No `with` block, so the app startup event
    (which runs create_all on the real engine) is skipped.
    """
    from fastapi.testclient import TestClient

    from db.base import get_db
    from main import app
    from services.auth.authentication_service import get_current_user

    user = _user(db_session)
    db_session.commit()

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)
    try:
        yield client, user, db_session
    finally:
        app.dependency_overrides.clear()


# --- system tests ---


def test_recommendation_endpoint_returns_valid_feed(rec_client):
    """ST-1: happy path — 200 and a well-formed RecommendationFeed contract."""
    client, user, db = rec_client
    v = _video(db)
    _add_word(db, v, _vocab(db, "あ"), freq=5)
    db.commit()

    resp = client.get("/video/recommendation")
    assert resp.status_code == 200

    body = resp.json()
    assert isinstance(body["is_cold_start"], bool)
    assert isinstance(body["sections"], list)
    for section in body["sections"]:
        assert {"key", "title", "total", "items"} <= section.keys()
        for item in section["items"]:
            assert {
                "id",
                "video",
                "understand_percent",
                "difficulty",
                "new_word_count",
                "review_word_count",
            } <= item.keys()


def test_recommendation_endpoint_requires_auth(db_session):
    """ST-2: no authenticated user -> 401 (get_current_user NOT overridden)."""
    from fastapi.testclient import TestClient

    from db.base import get_db
    from main import app

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db  # DB only, real auth left in place
    client = TestClient(app)
    try:
        assert client.get("/video/recommendation").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_recommendation_endpoint_excludes_recently_watched(rec_client):
    """ST-3: a video watched within the recency window is not returned."""
    client, user, db = rec_client
    watched, fresh = _video(db), _video(db)
    w = _vocab(db, "い")
    _add_word(db, watched, w, 5)
    _add_word(db, fresh, w, 5)
    _watch(db, user, watched, datetime.utcnow() - timedelta(hours=1))
    db.commit()

    ids = _item_ids(client.get("/video/recommendation").json())
    assert watched.id not in ids
    assert fresh.id in ids


def test_recommendation_endpoint_excludes_ineligible_videos(rec_client):
    """ST-4: inactive / not-shadowing-ready videos never appear."""
    client, user, db = rec_client
    ok = _video(db, ready=True, active=True)
    not_ready = _video(db, ready=False, active=True)
    inactive = _video(db, ready=True, active=False)
    w = _vocab(db, "う")
    for v in (ok, not_ready, inactive):
        _add_word(db, v, w, 5)
    db.commit()

    ids = _item_ids(client.get("/video/recommendation").json())
    assert ok.id in ids
    assert not_ready.id not in ids
    assert inactive.id not in ids


def test_recommendation_endpoint_cold_start_for_new_user(rec_client):
    """ST-5: a user with no vocabulary history is flagged as cold start."""
    client, user, db = rec_client  # seeded user has no known vocab
    _add_word(db, _video(db), _vocab(db, "え"), 5)
    db.commit()

    body = client.get("/video/recommendation").json()
    assert body["is_cold_start"] is True


def test_recommendation_endpoint_empty_catalog(rec_client):
    """ST-6: no eligible videos -> 200 with an empty section list."""
    client, user, db = rec_client
    resp = client.get("/video/recommendation")
    assert resp.status_code == 200
    assert resp.json()["sections"] == []
