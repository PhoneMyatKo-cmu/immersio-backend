"""
Tests for services/video/video_background_service.py  (Video Submission — Service)

process_video_vocab_background is a background worker: it opens its OWN database
session, delegates the vocabulary-profile build to save_video_vocab_profile, and
guarantees the session is rolled back on error and always closed. These tests
verify that session lifecycle + error handling.

Covers docs/test_plan.md §5.5:
  BG-01  success  -> delegates the build and closes the session (no rollback)
  BG-02  failure  -> rolls back, logs the failure, and never propagates

[unit] SessionLocal and save_video_vocab_profile are mocked, so no real DB is
used. The actual row persistence is covered by save_video_vocab_profile's own
test. The module skips if its import chain is unavailable.
"""

import logging
from unittest.mock import MagicMock

import pytest

try:
    from services.video import video_background_service as svc
    from services.video.video_background_service import process_video_vocab_background
except Exception as exc:
    pytest.skip(f"video_background_service unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.unit, pytest.mark.video_submission]

SURFACES = ["食べる", "食べる", "猫"]  # FX-VS-SURFACES (duplicates preserved)


# --- BG-01 ------------------------------------------------------------------
def test_builds_vocab_profile_and_closes_session(monkeypatch):
    session = MagicMock()
    monkeypatch.setattr(svc, "SessionLocal", MagicMock(return_value=session))
    build = MagicMock()
    monkeypatch.setattr(svc, "save_video_vocab_profile", build)

    process_video_vocab_background(1, SURFACES)

    # the worker delegates persistence on its own session with the given inputs
    build.assert_called_once_with(video_id=1, surface_forms=SURFACES, db=session)
    session.rollback.assert_not_called()
    session.close.assert_called_once()


# --- BG-02 ------------------------------------------------------------------
def test_rolls_back_and_logs_on_persistence_error(monkeypatch, caplog):
    session = MagicMock()
    monkeypatch.setattr(svc, "SessionLocal", MagicMock(return_value=session))
    monkeypatch.setattr(
        svc, "save_video_vocab_profile", MagicMock(side_effect=Exception("db error"))
    )

    with caplog.at_level(logging.ERROR):
        # the worker must swallow the error (background task: never propagates)
        process_video_vocab_background(1, SURFACES)

    session.rollback.assert_called_once()
    session.close.assert_called_once()  # session still closed on the error path
    assert any(
        "Failed video vocab background processing" in r.getMessage()
        for r in caplog.records
    )
