"""
Tests for the background workers:
  services/video/video_background_service.py        (MD-28)
  services/sentence/sentence_background_service.py  (MD-27)
Covers: docs/test_plan.md §5.5 (BG-01, BG-02).
[integration — own DB session; mock downstream Whisper/profile work]
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.video_submission]


# @pytest.mark.skip(reason="TODO BG-01: process_video_vocab_background builds profile + difficulty")
# def test_bg_01_vocab_background(db_session):
#     ...


# @pytest.mark.skip(reason="TODO BG-02: whisper background saves sentences + marks ready")
# def test_bg_02_whisper_background(db_session):
#     ...
