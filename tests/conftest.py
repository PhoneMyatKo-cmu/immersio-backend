"""
Shared pytest fixtures for the Immersio backend test suite.

Layout: tests/ mirrors the source tree (tests/api, tests/services, tests/utils).
Unit vs integration is expressed with markers (see pyproject.toml), not folders.

Heavy application imports (FastAPI app, ORM models, external SDK clients) are done
*inside* fixtures so pure unit tests never trigger them.

The fx_* fixtures mirror "Appendix A — Fixtures & Mock Returns" in
docs/test_plan.md. Add more as you implement cases; keep names aligned with the
FX- ids there.
"""

import os
import pytest

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/immersio_test",
)


# ---------------------------------------------------------------------------
# Integration infrastructure: database session + FastAPI test client
# ---------------------------------------------------------------------------
@pytest.fixture()
def db_session():
    """Transactional Postgres session with all tables created then dropped.

    Skips (does not fail) if the test database is unreachable, so the unit
    suite still runs on machines without Postgres.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from db.base import Base

    # Import model modules so every table registers on Base.metadata.
    # (File names are unchanged; class names may differ after the renames.)
    import models.user            # noqa: F401
    import models.video           # noqa: F401
    import models.vocab           # noqa: F401
    import models.processed_caption  # noqa: F401
    import models.sentence        # noqa: F401
    import models.video_vocab_profile  # noqa: F401
    import models.user_vocab_profile   # noqa: F401
    import models.user_vocab_library   # noqa: F401
    import models.ai_explanation_cache # noqa: F401

    engine = create_engine(TEST_DATABASE_URL)
    try:
        engine.connect().close()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Test database not available: {exc}")

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient with get_db -> test session and a stubbed current user.

    NOTE: importing `main` currently instantiates external SDK clients at import
    time (Gemini, Google Translate). Provide dummy credentials in the test env,
    or refactor those clients to lazy-init (see SDD Phase-2 notes), otherwise
    importing the app here can fail or make network calls.
    """
    from fastapi.testclient import TestClient

    from main import app
    from db.base import get_db
    from services.auth.authentication_service import get_current_user

    def _override_get_db():
        yield db_session

    class _StubUser:
        id = 1
        email = "test@example.com"

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: _StubUser()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Video Submission fixtures (subset of Appendix A; extend as needed)
# ---------------------------------------------------------------------------
@pytest.fixture()
def fx_meta_ja():
    """FX-VS-META-JA — Japanese, suitable video metadata."""
    return {
        "video_id": "dQw4w9WgXcQ", "title": "日本語レッスン",
        "channel_name": "Nihongo Channel",
        "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        "duration": "PT3M", "duration_iso": "PT3M",
        "default_language": "ja", "default_audio_language": "ja",
        "tags": ["japanese", "study"],
    }


@pytest.fixture()
def fx_meta_en(fx_meta_ja):
    """FX-VS-META-EN — non-Japanese audio/default language."""
    return {**fx_meta_ja, "default_language": "en", "default_audio_language": "en"}


@pytest.fixture()
def fx_trk_std():
    """FX-VS-TRK-STD — one human ('standard') Japanese caption track."""
    return [{"snippet": {"language": "ja", "trackKind": "standard"}}]


@pytest.fixture()
def fx_trk_asr():
    """FX-VS-TRK-ASR — auto/ASR-only Japanese caption track."""
    return [{"snippet": {"language": "ja", "trackKind": "asr"}}]


@pytest.fixture()
def fx_trk_en():
    """FX-VS-TRK-EN — non-Japanese caption track."""
    return [{"snippet": {"language": "en", "trackKind": "standard"}}]


@pytest.fixture()
def fx_validation_manual(fx_meta_ja, fx_trk_std):
    """FX-VS-VALID-MANUAL — validate_video result for a human-captioned video."""
    return {
        "valid": True, "video_id": "dQw4w9WgXcQ", "meta_data": fx_meta_ja,
        "suitablity": {
            "is_suitable": True, "has_japanese_captions": True,
            "reason": None, "available_captions": fx_trk_std,
        },
        "error": None,
    }


@pytest.fixture()
def fx_validation_auto(fx_validation_manual, fx_trk_asr):
    """FX-VS-VALID-AUTO — as manual but ASR-only tracks (Whisper path)."""
    v = {**fx_validation_manual}
    v["suitablity"] = {**v["suitablity"], "available_captions": fx_trk_asr}
    return v


@pytest.fixture()
def fx_json3():
    """FX-VS-JSON3 — raw json3 captions (aggregation, entity, blank, seg-less)."""
    return {"events": [
        {"tStartMs": 0,    "dDurationMs": 1500, "segs": [{"utf8": "こんにちは"}]},
        {"tStartMs": 1500, "dDurationMs": 2000,
         "segs": [{"utf8": "今日は "}, {"utf8": "いい天気 &amp; 暑い"}]},
        {"tStartMs": 3500, "dDurationMs": 100,  "segs": [{"utf8": "\n"}]},   # blank
        {"tStartMs": 3600, "dDurationMs": 1000},                            # no segs
    ]}


@pytest.fixture()
def fx_tiers_beg():
    """FX-VS-TIERS-BEG — beginner-weighted JLPT tier list."""
    return [{"jlpt_tier": "N5", "frequency": 7},
            {"jlpt_tier": "N4", "frequency": 2},
            {"jlpt_tier": "N2", "frequency": 1}]


# ---------------------------------------------------------------------------
# Word Look Up fixtures (subset of Appendix A; extend as needed)
# ---------------------------------------------------------------------------
@pytest.fixture()
def fx_context_request():
    """FX-WL-CONTEXTREQ — a context-explanation request payload (as a dict)."""
    return {
        "vocab_id": 1, "caption_id": 1, "surface_form": "食べる",
        "pos": ["verb"], "meanings": ["to eat"],
        "context_caption": "毎日ご飯を食べる。",
    }


@pytest.fixture()
def fx_user_save():
    """FX-WL-USERSAVE — a save-to-library request payload (as a dict)."""
    return {"vocab_id": 1, "video_id": 1, "caption_id": 1, "timestamp": 12.5}
