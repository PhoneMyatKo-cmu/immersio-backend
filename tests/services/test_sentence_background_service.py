"""
Tests for services/sentence/sentence_background_service.py  (Video Submission)

build_shadowing_sentences_with_whisper_background_task is the auto-caption path's
background worker: open its own session, reconstruct sentences via Whisper
(youtube_to_sentences), persist them, mark the video shadowing-ready, and commit;
on failure roll back and never propagate.

Covers docs/test_plan.md §5.5 (the Whisper background worker):
  success      -> saves sentences, marks ready, commits (no rollback)
  no sentences -> skips save + status update (early return), session still closed
  error        -> rolls back, logs, never propagates

[unit] SessionLocal and all collaborators are mocked; no real DB or Whisper. The
module skips if its heavy import chain is unavailable.
"""

import logging
from unittest.mock import MagicMock

import pytest

try:
    from services.sentence import sentence_background_service as svc
    from services.sentence.sentence_background_service import (
        build_shadowing_sentences_with_whisper_background_task as build_task,
    )
except Exception as exc:
    pytest.skip(
        f"sentence_background_service unavailable: {exc}", allow_module_level=True
    )

pytestmark = [pytest.mark.unit, pytest.mark.video_submission]

SENTENCES = [
    {
        "sentence_index": 0,
        "text": "おはよう",
        "start": 0.0,
        "end": 1.2,
        "duration": 1.2,
    },
]


def _patch(monkeypatch, sentences=SENTENCES, to_sentences_error=None):
    session = MagicMock()
    monkeypatch.setattr(svc, "SessionLocal", MagicMock(return_value=session))
    if to_sentences_error is not None:
        monkeypatch.setattr(
            svc, "youtube_to_sentences", MagicMock(side_effect=to_sentences_error)
        )
    else:
        monkeypatch.setattr(
            svc, "youtube_to_sentences", MagicMock(return_value=sentences)
        )
    save = MagicMock()
    status = MagicMock()
    monkeypatch.setattr(svc, "save_sentence", save)
    monkeypatch.setattr(svc, "change_shadowing_status", status)
    return session, save, status


# --- success ----------------------------------------------------------------
def test_success_saves_sentences_marks_ready_and_commits(monkeypatch):
    session, save, status = _patch(monkeypatch)
    build_task("7-vM6_2GNDw", 1)

    save.assert_called_once_with(SENTENCES, 1, session)
    status.assert_called_once_with(1, session)
    session.commit.assert_called_once()
    session.rollback.assert_not_called()
    session.close.assert_called_once()


# --- no sentences generated -------------------------------------------------
def test_no_sentences_skips_save_and_status(monkeypatch):
    session, save, status = _patch(monkeypatch, sentences=[])
    build_task("qP_xWkXSS3I", 1)

    save.assert_not_called()
    status.assert_not_called()
    session.commit.assert_not_called()
    session.close.assert_called_once()  # finally still closes


# --- error ------------------------------------------------------------------
def test_error_rolls_back_and_does_not_propagate(monkeypatch, caplog):
    session, save, status = _patch(
        monkeypatch, to_sentences_error=RuntimeError("whisper error")
    )
    with caplog.at_level(logging.ERROR):
        build_task("qP_xWkXsdf3I", 22)

    session.rollback.assert_called_once()
    session.close.assert_called_once()
    save.assert_not_called()
    assert any("FAILED" in r.getMessage() for r in caplog.records)
